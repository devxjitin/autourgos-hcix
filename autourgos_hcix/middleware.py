"""
middleware.py - HCIx middleware for Autourgos agents.
"""
from __future__ import annotations

import weakref
from typing import Any, List, Optional

from .base import CallbackHandler
from .hcix import CognitiveInterruptManager


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
        self._agent_ref: Optional["weakref.ReferenceType[Any]"] = None
        self._injected_blocks: List[str] = []

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
            try:
                self._agent_ref = weakref.ref(agent)
            except TypeError:
                self._agent_ref = None
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
        if self._agent_ref is None:
            return None
        return self._agent_ref()

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
        self._injected_blocks.append(block)

        if agent is None:
            return block

        if self.inject_into_scratchpad and isinstance(getattr(agent, "scratchpad", None), str):
            agent.scratchpad += f"\n\n{block}"

        if self.inject_into_system_prompt and isinstance(getattr(agent, "system_prompt", None), str):
            current = getattr(agent, "system_prompt")
            setattr(agent, "system_prompt", f"{current}\n\n{block}".strip())

        logger = getattr(agent, "logger", None)
        if logger:
            logger.middleware("HCIx", f"Human override injected: {instruction[:80]!r}")

        return block

    def _restore_system_prompt(self, agent: Any) -> None:
        if agent is None or not isinstance(getattr(agent, "system_prompt", None), str):
            return

        prompt = getattr(agent, "system_prompt")
        for block in self._injected_blocks:
            prompt = prompt.replace(f"\n\n{block}", "")
            prompt = prompt.replace(block, "")
        setattr(agent, "system_prompt", prompt.strip())
        self._injected_blocks.clear()

    def _log_total_pause(self, agent: Any, label: str) -> None:
        logger = getattr(agent, "logger", None) if agent is not None else None
        if logger and self._manager is not None:
            logger.info(f"Total time spent {label}: {self._manager.total_paused_time:.2f} seconds")
