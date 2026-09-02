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


if __name__ == "__main__":
    unittest.main()
