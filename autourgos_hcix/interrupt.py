"""
interrupt.py - programmatic human-interrupt primitives.
"""
from __future__ import annotations

import copy
import json
import threading
from typing import Any, Dict, Optional, Tuple


class HumanInterrupt(Exception):
    """Exception raised to signal a dynamic human intervention request."""

    def __init__(self, prompt: str, state_data: Optional[Dict[str, Any]] = None) -> None:
        self.prompt = prompt
        self.state_data = state_data or {}
        super().__init__(prompt)


class HumanInterruptHandler:
    """Synchronize a worker thread with an external human response."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._pending = False
        self._action: Optional[str] = None
        self._edits: Dict[str, Any] = {}

    def wait_for_human(self, timeout: Optional[float] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Block until a human operator submits an action.

        Returns ("timeout", {}) when the timeout elapses without a response.
        """
        with self._lock:
            self._pending = True
            self._action = None
            self._edits = {}
            self._event.clear()

        was_set = self._event.wait(timeout=timeout)
        with self._lock:
            if not was_set:
                self._pending = False
                return "timeout", {}
            action = self._action or "approve"
            edits = dict(self._edits)
            self._pending = False
            return action, edits

    def submit(self, action: str, edits: Optional[Dict[str, Any]] = None) -> None:
        """Resume the waiting thread with an action and optional state edits."""
        with self._lock:
            self._action = action
            self._edits = edits or {}
            self._event.set()

    def reset(self) -> None:
        """Clear event, action, edits, and pending state."""
        with self._lock:
            self._event.clear()
            self._pending = False
            self._action = None
            self._edits = {}

    @property
    def is_pending(self) -> bool:
        """Return True while wait_for_human is actively waiting."""
        with self._lock:
            return self._pending and not self._event.is_set()


class HumanStateEditor:
    """Console state visualizer and simple programmatic state editor."""

    @staticmethod
    def edit(state_data: Dict[str, Any], edits: Dict[str, Any]) -> Dict[str, Any]:
        """Apply edits to a deep copy of state_data and return the new state."""
        new_state = copy.deepcopy(state_data)
        new_state.update(edits)
        return new_state

    @staticmethod
    def display_panel(prompt: str, state_data: Dict[str, Any]) -> None:
        """Display a compact ANSI panel containing the active state."""
        border = "=" * 70
        print(f"\n\033[93m+{border}+\033[0m")
        print("\033[93m|\033[1m   HUMAN COGNITIVE INTERRUPT (HCIx) ACTIVATED\033[0m")
        print(f"\033[93m+{border}+\033[0m")
        print(f"\033[96m| Prompt: {prompt}\033[0m")
        print(f"\033[93m+{border}+\033[0m")
        print("| Active State Variables:")
        for key, value in state_data.items():
            value_text = str(value)
            if len(value_text) > 50:
                value_text = value_text[:47] + "..."
            print(f"|   - \033[1m{key}\033[0m: {value_text}")
        print(f"\033[93m+{border}+\033[0m")

    @staticmethod
    def prompt_user(prompt: str, state_data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Prompt the user in the CLI to approve, edit, or reject state."""
        HumanStateEditor.display_panel(prompt, state_data)

        while True:
            choice = input("\nSelect Action: [A]pprove | [E]dit State | [R]eject: ").strip().lower()
            if choice in ("a", "approve"):
                print("\033[92mExecution approved by human.\033[0m")
                return "approve", {}
            if choice in ("r", "reject"):
                print("\033[91mExecution rejected by human.\033[0m")
                return "reject", {}
            if choice in ("e", "edit"):
                edits: Dict[str, Any] = {}
                print("\nEnter state key to edit, or press Enter to finish editing.")
                while True:
                    key = input("  Variable Name: ").strip()
                    if not key:
                        break
                    if key not in state_data:
                        print(f"  Warning: {key!r} is not an active state variable; it will be added.")
                    raw_value = input(f"  New Value for {key!r}: ").strip()
                    try:
                        parsed_value = json.loads(raw_value)
                    except Exception:
                        parsed_value = raw_value
                    edits[key] = parsed_value
                    print(f"  Staged: {key} = {parsed_value!r}")
                return "edit", edits
            print("Invalid choice. Please select A, E, or R.")
