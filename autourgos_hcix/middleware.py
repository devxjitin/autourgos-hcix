"""
middleware.py - HCIx middleware for Autourgos agents.
"""
from __future__ import annotations

import logging
import weakref
from typing import Any, List, Optional

from autourgos_agent import inject_prompt_block, remove_prompt_block
from autourgos_core import PerAgentRegistry, warn_once_per_agent

from .base import CallbackHandler
from .hcix import CognitiveInterruptManager

_logger = logging.getLogger(__name__)


def format_human_override(instruction: str) -> str:
    """Format a high-priority human instruction for agent context."""
    return (
        "!!! [SYSTEM OVERRIDE - HUMAN INTERVENTION] !!!\n"
        "--- HUMAN COGNITIVE INTERRUPT ---\n"
        f"{instruction.strip()}\n"
        "---------------------------------\n"
        "CRITICAL: The human user has provided new authoritative instructions "
        "that override previous goals. Immediately address this instruction "
        "before continuing any earlier plan."
    )


class HcixInterruptMiddleware(CallbackHandler):
    """
    Human Cognitive Interrupt middleware.

    Starts a global shortcut listener, polls for committed human instructions,
    and injects override text into the agent context.
    """

    def __init__(
        self,
        shortcut: str = "ctrl+shift+h",
        manager: Optional[CognitiveInterruptManager] = None,
        poll_interval: float = 0.25,
        inject_into_system_prompt: bool = True,
        inject_into_scratchpad: bool = True,
        enable_hotkey: bool = True,
    ) -> None:
        self.shortcut = shortcut
        self.poll_interval = poll_interval
        self.inject_into_system_prompt = inject_into_system_prompt
        self.inject_into_scratchpad = inject_into_scratchpad
        self.enable_hotkey = enable_hotkey

        self._manager = manager
        # Fallback target for callers that reach inject_instruction()
        # directly (e.g. from manager.poll()'s trigger) without an explicit
        # agent -- last agent seen via a lifecycle hook.
        self._last_agent: Optional[Any] = None
        # Exact strings returned by inject_prompt_block() for each override
        # injected this run -- NOT a whole-system_prompt snapshot. A
        # snapshot-and-restore-the-whole-string design breaks the moment
        # another middleware (toolbox, skills) also injects into the same
        # system_prompt: whichever middleware's on_agent_end fires last
        # wins, and a middleware registered after this one would have
        # snapshotted THIS middleware's already-injected text as if it were
        # "the original," so restoring never actually got back to the true
        # original -- see inject_prompt_block's module docstring in
        # autourgos-agent. Removing exactly the substrings THIS instance
        # inserted is correct regardless of registration order or what any
        # other middleware does before/after/in between.
        #
        # Keyed per-agent (PerAgentRegistry) rather than a flat list: this
        # middleware instance is commonly shared across multiple concurrent
        # agents, and a flat self._injected_blocks let one agent's
        # on_agent_start reset the list out from under another agent's
        # still-in-flight injections/restore.
        self._runs: "PerAgentRegistry[List[str]]" = PerAgentRegistry()
        # Tracks which agents this middleware has already warned about
        # running in tool_calling_mode="native" with inject_into_scratchpad
        # enabled -- see inject_instruction's native-mode warning.
        self._warned_native_scratchpad_agents: "weakref.WeakSet[Any]" = weakref.WeakSet()

    @property
    def manager(self) -> CognitiveInterruptManager:
        """Return the active interrupt manager, creating it lazily if needed."""
        if self._manager is None:
            self._manager = CognitiveInterruptManager(
                shortcut=self.shortcut,
                poll_interval=self.poll_interval,
                enable_hotkey=self.enable_hotkey,
            )
        return self._manager

    def on_agent_start(self, query: str, agent: Any = None, **kwargs: Any) -> None:
        """Create and attach the interrupt manager at agent startup."""
        agent = agent or kwargs.get("agent")
        if agent is not None:
            self._last_agent = agent
            self._runs.set(agent, [])
            setattr(agent, "_interrupt_manager", self.manager)
        else:
            _ = self.manager

    def on_iteration_start(self, iteration: int, agent: Any = None, **kwargs: Any) -> None:
        """Poll before the next LLM call when the host agent exposes this hook."""
        self._poll_and_inject(agent or kwargs.get("agent"))

    def on_iteration(
        self,
        iteration: int,
        thought: Optional[str] = None,
        agent: Any = None,
        **kwargs: Any,
    ) -> None:
        """
        Poll when the host agent emits an iteration event.

        Agent emits this after a thought is produced, so injected
        instructions affect the following reasoning step there.
        """
        self._poll_and_inject(agent or kwargs.get("agent"))

    def on_agent_end(self, result: str, agent: Any = None, **kwargs: Any) -> None:
        """Stop listeners and remove temporary system prompt injections."""
        agent = agent or kwargs.get("agent") or self._get_agent()
        self._log_total_pause(agent, "waiting for human interrupts")
        self._restore_system_prompt(agent)
        if self._manager is not None:
            self._manager.stop()

    def on_agent_error(self, error: Exception, agent: Any = None, **kwargs: Any) -> None:
        """Stop listeners and remove temporary system prompt injections after errors."""
        agent = agent or kwargs.get("agent") or self._get_agent()
        self._log_total_pause(agent, "waiting for human interrupts before error")
        self._restore_system_prompt(agent)
        if self._manager is not None:
            self._manager.stop()

    def _get_agent(self) -> Any:
        return self._last_agent

    def _warn_native_scratchpad_noop(self, agent: Any) -> None:
        if self.inject_into_system_prompt:
            message = (
                "HcixInterruptMiddleware: agent.tool_calling_mode is 'native' -- "
                "inject_into_scratchpad has no effect in native mode (scratchpad "
                "is never sent to the LLM there); the override still reaches the "
                "model via system_prompt (inject_into_system_prompt=True)."
            )
        else:
            message = (
                "HcixInterruptMiddleware: agent.tool_calling_mode is 'native' and "
                "inject_into_system_prompt=False -- the injected override will "
                "NOT reach the model at all (inject_into_scratchpad has no effect "
                "in native mode; scratchpad is never sent to the LLM there). Set "
                "inject_into_system_prompt=True to actually deliver overrides in "
                "native mode."
            )
        warn_once_per_agent(self._warned_native_scratchpad_agents, agent, _logger, message)

    def _poll_and_inject(self, agent: Any = None) -> None:
        agent = agent or self._get_agent()
        logger = getattr(agent, "logger", None) if agent is not None else None
        instruction = self.manager.poll(logger=logger)
        if not instruction:
            return
        self.inject_instruction(instruction, agent=agent)

    def inject_instruction(self, instruction: str, agent: Any = None) -> str:
        """Inject an instruction into the agent context and return the block."""
        agent = agent or self._get_agent()
        block = format_human_override(instruction)

        if agent is None:
            return block

        if self.inject_into_scratchpad and isinstance(getattr(agent, "scratchpad", None), str):
            if getattr(agent, "tool_calling_mode", "prompt") == "native":
                # tool_calling_mode="native" never sends agent.scratchpad
                # to the LLM (it's a human-readable trace only -- the real
                # conversation state is an internal message list this
                # middleware has no access to). Appending the override
                # there used to silently drop it with no signal at all if
                # inject_into_system_prompt was also off. Warned once per
                # agent instead of failing silently.
                self._warn_native_scratchpad_noop(agent)
            else:
                agent.scratchpad += f"\n\n{block}"

        if self.inject_into_system_prompt and isinstance(getattr(agent, "system_prompt", None), str):
            # Appended (prepend=False), not prepended -- an override reads
            # naturally as coming after the base system prompt/catalog
            # text, matching this middleware's prior behavior exactly. The
            # isinstance guard preserves this middleware's original scope
            # (system_prompt only, never inject_prompt_block's
            # prompt_template fallback -- HCIx never touched that).
            # inject_prompt_block's returned value (not `block` itself) is
            # what gets tracked, since it includes the separator this call
            # actually introduced -- required for remove_prompt_block() to
            # undo precisely this insertion later.
            inserted = inject_prompt_block(agent, block, prepend=False)
            if inserted is not None:
                self._runs.get(agent, list).append(inserted)

        logger = getattr(agent, "logger", None)
        if logger:
            logger.middleware("HCIx", f"Human override injected: {instruction[:80]!r}")

        return block

    def _restore_system_prompt(self, agent: Any) -> None:
        if agent is None:
            return
        injected_blocks = self._runs.pop(agent, None)
        if self._last_agent is agent:
            self._last_agent = None
        if injected_blocks is None or not isinstance(getattr(agent, "system_prompt", None), str):
            return

        # Remove exactly the blocks THIS run injected -- order-independent
        # and correct regardless of what other middleware (toolbox, skills)
        # injects/removes before, after, or in between. See
        # inject_prompt_block's module docstring in autourgos-agent.
        for block in injected_blocks:
            remove_prompt_block(agent, block)

    def _log_total_pause(self, agent: Any, label: str) -> None:
        logger = getattr(agent, "logger", None) if agent is not None else None
        if logger and self._manager is not None:
            logger.info(f"Total time spent {label}: {self._manager.total_paused_time:.2f} seconds")
