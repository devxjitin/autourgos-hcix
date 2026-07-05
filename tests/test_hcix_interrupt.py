import threading
import unittest

from autourgos_hcix import (
    CognitiveInterruptManager,
    HcixInterruptMiddleware,
    HumanInterruptHandler,
    HumanStateEditor,
    InterruptState,
)


class DummyAgent:
    def __init__(self):
        self.system_prompt = "base prompt"
        self.scratchpad = ""
        self.logger = None


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

    def test_state_editor_does_not_mutate_original(self):
        original = {"nested": {"count": 1}}
        edited = HumanStateEditor.edit(original, {"status": "approved"})

        self.assertEqual(original, {"nested": {"count": 1}})
        self.assertEqual(edited["status"], "approved")

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
