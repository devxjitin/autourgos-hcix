import os
import threading
import unittest
from unittest.mock import MagicMock, patch

from autourgos_agent.testing import make_test_agent

from autourgos_hcix import (
    CognitiveInterruptManager,
    HcixInterruptMiddleware,
    HumanInterruptHandler,
    HumanStateEditor,
    InterruptState,
)
from autourgos_hcix.middleware import format_human_override


class DummyAgent:
    def __init__(self):
        self.system_prompt = "base prompt"
        self.scratchpad = ""
        self.logger = None


class NoLoggerAgent:
    """Fake agent with no .logger attribute at all."""

    def __init__(self):
        self.system_prompt = "base prompt"
        self.scratchpad = ""


class HcixInterruptTests(unittest.TestCase):
    def test_manager_consumes_programmatic_instruction(self):
        manager = CognitiveInterruptManager(enable_hotkey=False)
        manager.submit_instruction("change course")

        self.assertEqual(manager.check_state(), InterruptState.COMMITTED)
        self.assertEqual(manager.poll(), "change course")
        self.assertEqual(manager.check_state(), InterruptState.IDLE)

    def test_middleware_injects_and_restores_prompt(self):
        manager = CognitiveInterruptManager(enable_hotkey=False)
        middleware = HcixInterruptMiddleware(manager=manager)
        agent = DummyAgent()

        middleware.on_agent_start("query", agent=agent)
        manager.submit_instruction("summarize now")
        middleware.on_iteration_start(1, agent=agent)

        self.assertIn("summarize now", agent.system_prompt)
        self.assertIn("summarize now", agent.scratchpad)

        middleware.on_agent_end("done", agent=agent)
        self.assertEqual(agent.system_prompt, "base prompt")

    def test_restore_preserves_preexisting_text_matching_injected_block(self):
        """Regression: _restore_system_prompt used to remove injected blocks
        via a global substring .replace(), which strips EVERY occurrence of
        that text -- including one that was already part of the agent's
        base prompt before this run's injection, not just the one HCIx
        itself added. It now restores the exact pre-injection snapshot, so
        anything present before injection (matching or not) survives."""
        manager = CognitiveInterruptManager(enable_hotkey=False)
        middleware = HcixInterruptMiddleware(manager=manager)
        agent = DummyAgent()

        # Craft the base prompt to already contain, verbatim, the text a
        # later override injection will also produce.
        preexisting_block = format_human_override("summarize now")
        agent.system_prompt = f"base prompt\n\n{preexisting_block}"

        middleware.on_agent_start("query", agent=agent)
        manager.submit_instruction("summarize now")
        middleware.on_iteration_start(1, agent=agent)

        # both the pre-existing occurrence and HCIx's own new injection are
        # now present
        self.assertEqual(agent.system_prompt.count(preexisting_block), 2)

        middleware.on_agent_end("done", agent=agent)

        # Old (buggy) behavior: global .replace() would strip BOTH
        # occurrences, losing the pre-existing one that was never HCIx's to
        # remove. New behavior: restore the exact snapshot from before this
        # run's injection, so the pre-existing occurrence survives.
        self.assertEqual(agent.system_prompt, f"base prompt\n\n{preexisting_block}")

    def test_state_editor_does_not_mutate_original(self):
        original = {"nested": {"count": 1}}
        edited = HumanStateEditor.edit(original, {"status": "approved"})

        self.assertEqual(original, {"nested": {"count": 1}})
        self.assertEqual(edited["status"], "approved")

    def test_concurrent_managers_get_unique_hotkey_ids(self):
        manager_a = CognitiveInterruptManager(enable_hotkey=False)
        manager_b = CognitiveInterruptManager(enable_hotkey=False)

        self.assertNotEqual(manager_a._instance_hotkey_id, manager_b._instance_hotkey_id)
        # Both ids must fall within the Windows app-defined hotkey id range.
        for hotkey_id in (manager_a._instance_hotkey_id, manager_b._instance_hotkey_id):
            self.assertGreaterEqual(hotkey_id, 0x0000)
            self.assertLessEqual(hotkey_id, 0xBFFF)

    def test_middleware_narrates_injection_via_agent_logger(self):
        manager = CognitiveInterruptManager(enable_hotkey=False)
        middleware = HcixInterruptMiddleware(manager=manager)
        agent = DummyAgent()
        agent.logger = MagicMock()

        middleware.on_agent_start("query", agent=agent)
        manager.submit_instruction("summarize now")
        middleware.on_iteration_start(1, agent=agent)

        agent.logger.middleware.assert_called_once()
        args, _ = agent.logger.middleware.call_args
        self.assertEqual(args[0], "HCIx")
        self.assertIn("summarize now", args[1])

    def test_no_crash_when_agent_has_no_logger_attribute(self):
        manager = CognitiveInterruptManager(enable_hotkey=False)
        middleware = HcixInterruptMiddleware(manager=manager)
        agent = NoLoggerAgent()
        self.assertFalse(hasattr(agent, "logger"))

        middleware.on_agent_start("query", agent=agent)
        manager.submit_instruction("summarize now")
        # should not raise even though agent has no .logger
        middleware.on_iteration_start(1, agent=agent)

        self.assertIn("summarize now", agent.system_prompt)

    def test_real_agent_scratchpad_actually_contains_injected_override(self):
        """
        End-to-end against a real Agent (make_test_agent): before
        react-agent 1.6.0, agent.scratchpad was never a real attribute on a
        live agent, so this injection path silently never fired against a
        real agent (only against hand-rolled fakes that pre-set
        scratchpad = ""). This verifies a human override actually lands in
        the real, live agent.scratchpad mid-run.
        """
        import json

        manager = CognitiveInterruptManager(enable_hotkey=False)
        middleware = HcixInterruptMiddleware(manager=manager)

        responses = [
            json.dumps({
                "thought": "working",
                "actions": [{"action": "echo", "action_input": {"text": "step one"}}],
                "final_answer": None,
            }),
            json.dumps({"thought": None, "actions": [], "final_answer": "final"}),
        ]

        # Submit the override before the loop starts polling, so the first
        # on_iteration_start call picks it up.
        manager.submit_instruction("switch to plan B")

        agent = make_test_agent(responses=responses, middleware=[middleware])
        result = agent.invoke("do the task")

        self.assertEqual(result, "final")
        self.assertIn("switch to plan B", agent.scratchpad)
        self.assertIn("HUMAN COGNITIVE INTERRUPT", agent.scratchpad)

    def test_headless_classmethod_disables_hotkey(self):
        manager = CognitiveInterruptManager.headless()

        self.assertIsNone(manager._listener)
        self.assertIsNone(manager._hotkey_id)
        manager.submit_instruction("go")
        self.assertEqual(manager.poll(), "go")

    def test_headless_environment_skips_pynput_without_importing_it(self):
        env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        with patch.dict(os.environ, env, clear=True), \
             patch("autourgos_hcix.hcix.os.name", "posix"), \
             patch.object(CognitiveInterruptManager, "_start_pynput_listener") as start_pynput:
            manager = CognitiveInterruptManager(enable_hotkey=True)

        start_pynput.assert_not_called()
        self.assertIsNotNone(manager.registration_error)
        self.assertIn("DISPLAY", manager.registration_error)

    def test_interrupt_handler_waits_for_submit(self):
        handler = HumanInterruptHandler()

        def submit_later():
            handler.submit("edit", {"x": 2})

        timer = threading.Timer(0.01, submit_later)
        timer.start()
        action, edits = handler.wait_for_human(timeout=1.0)
        timer.cancel()

        self.assertEqual(action, "edit")
        self.assertEqual(edits, {"x": 2})

    def test_restore_is_exact_even_with_foreign_text_injected_around_it(self):
        """
        Regression: restore used to snapshot the WHOLE system_prompt before
        injecting and restore that whole snapshot after -- if another
        middleware (autourgos-toolbox, autourgos-skills) prepended text of
        its own between this middleware's on_agent_start and on_agent_end,
        this middleware's snapshot-based restore would silently discard
        that other middleware's still-active injection (or, depending on
        registration order, permanently bake HCIx's own override into what
        the other middleware treats as "the original"). Restore must now
        remove exactly the block THIS middleware added, leaving anything
        else untouched regardless of when it was added.
        """
        manager = CognitiveInterruptManager(enable_hotkey=False)
        middleware = HcixInterruptMiddleware(manager=manager)
        agent = DummyAgent()
        base_prompt = agent.system_prompt

        middleware.on_agent_start("query", agent=agent)
        manager.submit_instruction("summarize now")
        middleware.on_iteration_start(1, agent=agent)
        self.assertIn("summarize now", agent.system_prompt)

        # simulate a second, unrelated middleware injecting its own text
        # AFTER hcix already injected, still active when hcix's own
        # on_agent_end fires
        agent.system_prompt = f"{agent.system_prompt}\n\nFOREIGN BLOCK"

        middleware.on_agent_end("done", agent=agent)

        self.assertEqual(agent.system_prompt, f"{base_prompt}\n\nFOREIGN BLOCK")

    def test_native_mode_scratchpad_injection_is_skipped_and_warns_once(self):
        """
        Regression: tool_calling_mode="native" never sends agent.scratchpad
        to the LLM. inject_into_scratchpad used to append the override
        there anyway, silently dropping it with zero signal if
        inject_into_system_prompt was also disabled. Must now skip the
        scratchpad append for a native-mode agent and warn once (not per
        injection), and system_prompt injection must still work normally.
        """
        manager = CognitiveInterruptManager(enable_hotkey=False)
        middleware = HcixInterruptMiddleware(manager=manager)
        agent = DummyAgent()
        agent.tool_calling_mode = "native"

        with self.assertLogs("autourgos_hcix.middleware", level="WARNING") as log_ctx:
            middleware.on_agent_start("query", agent=agent)
            manager.submit_instruction("first override")
            middleware.on_iteration_start(1, agent=agent)
            manager.submit_instruction("second override")
            middleware.on_iteration_start(2, agent=agent)

        self.assertEqual(agent.scratchpad, "")  # never appended to in native mode
        self.assertIn("first override", agent.system_prompt)  # still reaches the model
        self.assertIn("second override", agent.system_prompt)
        native_mode_warnings = [msg for msg in log_ctx.output if "native" in msg]
        self.assertEqual(len(native_mode_warnings), 1)  # warned once, not per injection

    def test_native_mode_with_system_prompt_injection_disabled_warns_override_dropped(self):
        manager = CognitiveInterruptManager(enable_hotkey=False)
        middleware = HcixInterruptMiddleware(manager=manager, inject_into_system_prompt=False)
        agent = DummyAgent()
        agent.tool_calling_mode = "native"

        with self.assertLogs("autourgos_hcix.middleware", level="WARNING") as log_ctx:
            middleware.on_agent_start("query", agent=agent)
            manager.submit_instruction("dropped override")
            middleware.on_iteration_start(1, agent=agent)

        self.assertEqual(agent.scratchpad, "")
        self.assertEqual(agent.system_prompt, "base prompt")  # override never reached anywhere
        self.assertTrue(any("NOT reach the model" in msg for msg in log_ctx.output))

    def test_two_agents_sharing_one_middleware_do_not_clash(self):
        """
        Sprint 5 regression: HcixInterruptMiddleware used to track injected
        blocks in a flat self._injected_blocks list and a flat
        self._agent_ref -- a single middleware instance shared by two agents
        would have one agent's on_agent_start reset state out from under the
        other's in-flight injection/restore. Now per-agent (PerAgentRegistry),
        so two agents' overrides and restores stay independent regardless of
        interleaving.
        """
        manager = CognitiveInterruptManager(enable_hotkey=False)
        middleware = HcixInterruptMiddleware(manager=manager)
        agent_a = DummyAgent()
        agent_b = DummyAgent()

        middleware.on_agent_start("query", agent=agent_a)
        middleware.on_agent_start("query", agent=agent_b)

        middleware.inject_instruction("override for a", agent=agent_a)

        self.assertIn("override for a", agent_a.system_prompt)
        self.assertNotIn("override for a", agent_b.system_prompt)
        self.assertEqual(agent_b.system_prompt, "base prompt")

        middleware.inject_instruction("override for b", agent=agent_b)
        self.assertIn("override for b", agent_b.system_prompt)
        self.assertNotIn("override for b", agent_a.system_prompt)

        middleware.on_agent_end("done", agent=agent_a)
        self.assertEqual(agent_a.system_prompt, "base prompt")
        # agent_b's still-active injection must survive agent_a's restore
        self.assertIn("override for b", agent_b.system_prompt)

        middleware.on_agent_end("done", agent=agent_b)
        self.assertEqual(agent_b.system_prompt, "base prompt")

    def test_two_concurrent_agents_threaded_do_not_clash(self):
        manager = CognitiveInterruptManager(enable_hotkey=False)
        middleware = HcixInterruptMiddleware(manager=manager)
        agent_a = DummyAgent()
        agent_b = DummyAgent()

        errors = []
        barrier = threading.Barrier(2)

        def drive(agent, own_text, other_text):
            try:
                middleware.on_agent_start("query", agent=agent)
                barrier.wait(timeout=5)
                middleware.inject_instruction(own_text, agent=agent)
                for _ in range(20):
                    assert other_text not in agent.system_prompt, f"leaked {other_text!r} into agent"
                middleware.on_agent_end("done", agent=agent)
                assert agent.system_prompt == "base prompt"
            except Exception as exc:  # pragma: no cover - surfaced via errors list
                errors.append(exc)

        t_a = threading.Thread(target=drive, args=(agent_a, "override for a", "override for b"))
        t_b = threading.Thread(target=drive, args=(agent_b, "override for b", "override for a"))
        t_a.start()
        t_b.start()
        t_a.join(timeout=10)
        t_b.join(timeout=10)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
