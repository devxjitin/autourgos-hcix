"""
hcix.py - Human Cognitive Interrupt manager.
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from enum import Enum
from queue import Empty, Queue
from typing import Any, Optional, Tuple

try:
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
except ImportError:  # pragma: no cover - depends on Python distribution
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    ScrolledText = None  # type: ignore[assignment]


class InterruptState(Enum):
    """Current state of the HCIx interrupt flow."""

    IDLE = "IDLE"
    WRITING = "WRITING"
    COMMITTED = "COMMITTED"
    PROCESSING = "PROCESSING"


class CognitiveInterruptManager:
    """
    Manage global hotkey detection and human interrupt collection.

    The manager is intentionally separate from middleware so tests, dashboards,
    and custom UIs can submit instructions programmatically.
    """

    _MODIFIERS = {
        "alt": 0x0001,
        "ctrl": 0x0002,
        "control": 0x0002,
        "shift": 0x0004,
        "win": 0x0008,
        "meta": 0x0008,
        "windows": 0x0008,
    }

    _KEYS = {
        "enter": 0x0D,
        "return": 0x0D,
        "tab": 0x09,
        "space": 0x20,
        "esc": 0x1B,
        "escape": 0x1B,
        "backspace": 0x08,
        "delete": 0x2E,
        "del": 0x2E,
        "insert": 0x2D,
        "ins": 0x2D,
        "home": 0x24,
        "end": 0x23,
        "pageup": 0x21,
        "pgup": 0x21,
        "pagedown": 0x22,
        "pgdn": 0x22,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
    }

    for _i in range(1, 25):
        _KEYS[f"f{_i}"] = 0x6F + _i

    def __init__(
        self,
        shortcut: str = "ctrl+shift+h",
        poll_interval: float = 0.25,
        enable_hotkey: bool = True,
    ) -> None:
        self.shortcut = shortcut
        self.poll_interval = poll_interval
        self.state = InterruptState.IDLE
        self.total_paused_time = 0.0

        self._ui_open = False
        self._lock = threading.RLock()
        self._instruction_queue: "Queue[str]" = Queue()
        self._stop_event = threading.Event()
        self._listener_warning_emitted = False
        self._registration_error: Optional[str] = None
        self._hotkey_id: Optional[int] = None
        self._listener: Any = None

        if enable_hotkey:
            self._start_hotkey_listener()

    @property
    def registration_error(self) -> Optional[str]:
        """Return the hotkey registration error, if listener startup failed."""
        return self._registration_error

    def _start_hotkey_listener(self) -> None:
        if os.name == "nt":
            listener = threading.Thread(
                target=self._hotkey_loop,
                daemon=True,
                name="hcix-hotkey-listener",
            )
            listener.start()
            return

        try:
            self._start_pynput_listener()
        except ImportError:
            self._registration_error = (
                "Cross-platform HCIx hotkeys require pynput on non-Windows systems. "
                "Install it with: pip install 'autourgos-hcix[hcix]'."
            )
        except Exception as exc:
            self._registration_error = f"Failed to start HCIx hotkey listener: {exc}"

    def _start_pynput_listener(self) -> None:
        from pynput import keyboard as pynput_keyboard  # type: ignore

        hotkey = self._to_pynput_hotkey(self.shortcut)
        listener = pynput_keyboard.GlobalHotKeys({hotkey: self.open_prompt})
        listener.start()
        self._listener = listener

    def _to_pynput_hotkey(self, shortcut: str) -> str:
        parts = [part.strip().lower() for part in shortcut.split("+") if part.strip()]
        if not parts:
            raise ValueError("Shortcut must not be empty.")

        translated = []
        for part in parts:
            if part in ("ctrl", "control"):
                translated.append("<ctrl>")
            elif part == "shift":
                translated.append("<shift>")
            elif part == "alt":
                translated.append("<alt>")
            elif part in ("cmd", "command", "win", "meta", "windows"):
                translated.append("<cmd>")
            elif len(part) == 1:
                translated.append(part)
            elif part in self._KEYS:
                translated.append(f"<{part}>")
            else:
                raise ValueError(f"Unsupported shortcut token: {part!r}")
        return "+".join(translated)

    def _parse_shortcut(self, shortcut: str) -> Tuple[int, int]:
        tokens = [token.strip().lower() for token in shortcut.split("+") if token.strip()]
        if not tokens:
            raise ValueError("Shortcut must not be empty.")

        modifiers = 0
        key_code: Optional[int] = None
        for token in tokens:
            if token in self._MODIFIERS:
                modifiers |= self._MODIFIERS[token]
                continue
            if token in self._KEYS:
                if key_code is not None:
                    raise ValueError("Shortcut can only contain one non-modifier key.")
                key_code = self._KEYS[token]
                continue
            if len(token) == 1 and token.isalnum():
                if key_code is not None:
                    raise ValueError("Shortcut can only contain one non-modifier key.")
                key_code = ord(token.upper()) if token.isalpha() else ord(token)
                continue
            raise ValueError(f"Unsupported shortcut token: {token!r}")

        if key_code is None:
            raise ValueError("Shortcut must include a final key, for example ctrl+shift+h.")
        return modifiers, key_code

    def _hotkey_loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        msg = wintypes.MSG()

        try:
            modifiers, key_code = self._parse_shortcut(self.shortcut)
        except ValueError as exc:
            self._registration_error = f"Invalid hcix shortcut {self.shortcut!r}: {exc}"
            return

        hotkey_id = 0xC1A0
        if not user32.RegisterHotKey(None, hotkey_id, modifiers, key_code):
            self._registration_error = f"Failed to register HCIx shortcut {self.shortcut!r}."
            return

        self._hotkey_id = hotkey_id
        try:
            while not self._stop_event.is_set():
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0312:
                        self.open_prompt()
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.05)
        finally:
            if self._hotkey_id is not None:
                user32.UnregisterHotKey(None, self._hotkey_id)
                self._hotkey_id = None

    def open_prompt(self) -> None:
        """Open the human interrupt prompt if one is not already active."""
        with self._lock:
            if self._ui_open or self.state in (InterruptState.COMMITTED, InterruptState.PROCESSING):
                return
            self._ui_open = True
            self.state = InterruptState.WRITING

        if sys.platform == "darwin" or tk is None or ttk is None or ScrolledText is None:
            threading.Thread(
                target=self._run_console_interrupt,
                daemon=True,
                name="hcix-console-input",
            ).start()
        else:
            threading.Thread(
                target=self._run_interrupt_window,
                daemon=True,
                name="hcix-ui-window",
            ).start()

    def submit_instruction(self, instruction: str) -> None:
        """Programmatically submit an instruction without opening a UI."""
        text = instruction.strip()
        if not text:
            return
        with self._lock:
            self._instruction_queue.put(text)
            self.state = InterruptState.COMMITTED
            self._ui_open = False

    def cancel_prompt(self) -> None:
        """Cancel the current prompt and return to idle state."""
        with self._lock:
            self._ui_open = False
            self.state = InterruptState.IDLE

    def _run_console_interrupt(self) -> None:
        try:
            print("\n--- Human Cognitive Interrupt ---")
            print("Provide a high-priority instruction, or leave blank to cancel.")
            instruction = input("> ").strip()
            if instruction:
                self.submit_instruction(instruction)
            else:
                self.cancel_prompt()
        except Exception:
            self.cancel_prompt()

    def _run_interrupt_window(self) -> None:
        try:
            root = tk.Tk()
            root.title("HCIx Human Interrupt")
            root.geometry("720x500")
            root.resizable(False, False)
            root.configure(bg="#090E1A")
            root.attributes("-topmost", True)
            root.after(250, lambda: root.attributes("-topmost", False))

            window_w, window_h = 720, 500
            screen_w = root.winfo_screenwidth()
            screen_h = root.winfo_screenheight()
            x = (screen_w - window_w) // 2
            y = (screen_h - window_h) // 2
            root.geometry(f"{window_w}x{window_h}+{x}+{y}")

            style = ttk.Style(root)
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass
            style.configure("HCIX.Root.TFrame", background="#090E1A")
            style.configure("HCIX.Card.TFrame", background="#111827", relief="flat")
            style.configure(
                "HCIX.Title.TLabel",
                background="#111827",
                foreground="#F8FAFC",
                font=("Segoe UI Semibold", 16),
            )
            style.configure(
                "HCIX.Subtitle.TLabel",
                background="#111827",
                foreground="#94A3B8",
                font=("Segoe UI", 10),
            )
            style.configure(
                "HCIX.Badge.TLabel",
                background="#1E293B",
                foreground="#93C5FD",
                font=("Segoe UI Semibold", 9),
                padding=(8, 3),
            )
            style.configure(
                "HCIX.Footer.TLabel",
                background="#111827",
                foreground="#64748B",
                font=("Segoe UI", 9),
            )
            style.configure(
                "HCIX.Send.TButton",
                font=("Segoe UI Semibold", 10),
                background="#2563EB",
                foreground="#F8FAFC",
                padding=(14, 8),
                borderwidth=0,
                focuscolor="none",
            )
            style.map("HCIX.Send.TButton", background=[("active", "#1D4ED8"), ("pressed", "#1E40AF")])
            style.configure(
                "HCIX.Cancel.TButton",
                font=("Segoe UI", 10),
                background="#334155",
                foreground="#E2E8F0",
                padding=(14, 8),
                borderwidth=0,
                focuscolor="none",
            )
            style.map("HCIX.Cancel.TButton", background=[("active", "#475569"), ("pressed", "#334155")])

            root_frame = ttk.Frame(root, style="HCIX.Root.TFrame", padding=14)
            root_frame.pack(fill="both", expand=True)

            outer_shadow = tk.Frame(root_frame, bg="#0B1222", padx=1, pady=1)
            outer_shadow.pack(fill="both", expand=True)

            card = ttk.Frame(outer_shadow, style="HCIX.Card.TFrame", padding=18)
            card.pack(fill="both", expand=True)

            header_row = ttk.Frame(card, style="HCIX.Card.TFrame")
            header_row.pack(fill="x")

            left_header = ttk.Frame(header_row, style="HCIX.Card.TFrame")
            left_header.pack(side="left", fill="x", expand=True)
            ttk.Label(left_header, text="Human Cognitive Interrupt", style="HCIX.Title.TLabel").pack(anchor="w")
            ttk.Label(
                left_header,
                text="Provide a high-priority instruction. The agent will apply it immediately.",
                style="HCIX.Subtitle.TLabel",
            ).pack(anchor="w", pady=(4, 0))

            ttk.Label(
                header_row,
                text=f"Shortcut  {self.shortcut}",
                style="HCIX.Badge.TLabel",
            ).pack(side="right", anchor="n")

            editor_wrap = ttk.Frame(card, style="HCIX.Card.TFrame")
            editor_wrap.pack(fill="both", expand=True, pady=(14, 10))
            editor_wrap.columnconfigure(0, weight=1)
            editor_wrap.rowconfigure(0, weight=1)

            text = ScrolledText(
                editor_wrap,
                wrap="word",
                height=14,
                font=("Consolas", 11),
                bg="#0F172A",
                fg="#E2E8F0",
                insertbackground="#E2E8F0",
                borderwidth=0,
                padx=12,
                pady=12,
                undo=True,
            )
            text.grid(row=0, column=0, sticky="nsew")
            text.configure(highlightthickness=1, highlightbackground="#334155", highlightcolor="#2563EB")
            text.focus_set()

            status_var = tk.StringVar(value="Ready to send interrupt")
            meta_row = ttk.Frame(card, style="HCIX.Card.TFrame")
            meta_row.pack(fill="x", pady=(0, 10))
            ttk.Label(meta_row, textvariable=status_var, style="HCIX.Subtitle.TLabel").pack(side="left")
            count_var = tk.StringVar(value="0 characters")
            ttk.Label(meta_row, textvariable=count_var, style="HCIX.Footer.TLabel").pack(side="right")

            def close_without_send() -> None:
                self.cancel_prompt()
                root.destroy()

            def submit() -> None:
                instruction = text.get("1.0", "end").strip()
                if not instruction:
                    status_var.set("Please type an instruction before sending.")
                    return
                self.submit_instruction(instruction)
                root.destroy()

            def refresh_count(_event: Any = None) -> None:
                body = text.get("1.0", "end-1c")
                count_var.set(f"{len(body)} characters")
                text.edit_modified(False)

            text.bind("<<Modified>>", refresh_count)
            refresh_count()

            button_row = ttk.Frame(card, style="HCIX.Card.TFrame")
            button_row.pack(fill="x")
            ttk.Button(button_row, text="Send", style="HCIX.Send.TButton", command=submit).pack(side="right")
            ttk.Button(
                button_row,
                text="Cancel",
                style="HCIX.Cancel.TButton",
                command=close_without_send,
            ).pack(side="right", padx=(0, 8))

            root.bind("<Control-Return>", lambda _event: submit())
            root.bind("<Escape>", lambda _event: close_without_send())
            root.protocol("WM_DELETE_WINDOW", close_without_send)
            root.mainloop()
        except Exception:
            self.cancel_prompt()

    def check_state(self) -> InterruptState:
        """Return the current interrupt state without blocking."""
        with self._lock:
            if self.state in (InterruptState.COMMITTED, InterruptState.PROCESSING):
                return self.state
            if self._ui_open:
                self.state = InterruptState.WRITING
            else:
                self.state = InterruptState.IDLE
            return self.state

    def _consume_instruction(self) -> Optional[str]:
        try:
            instruction = self._instruction_queue.get_nowait()
        except Empty:
            return None
        with self._lock:
            self.state = InterruptState.PROCESSING
        return instruction

    def _log_registration_issue(self, logger: Any) -> None:
        if self._registration_error and logger and not self._listener_warning_emitted:
            logger.warning(self._registration_error)
            self._listener_warning_emitted = True

    def poll(self, logger: Any = None) -> Optional[str]:
        """
        Poll synchronously for a committed instruction.

        If the prompt is open, this blocks until the user submits or cancels.
        """
        self._log_registration_issue(logger)
        pause_start = None
        while True:
            state = self.check_state()

            if state == InterruptState.IDLE:
                if pause_start is not None:
                    with self._lock:
                        self.total_paused_time += time.time() - pause_start
                return None

            if state == InterruptState.WRITING:
                if pause_start is None:
                    pause_start = time.time()
                    if logger:
                        logger.info("Human interrupt detected. Waiting for HCIx input.")
                time.sleep(self.poll_interval)
                continue

            if state == InterruptState.COMMITTED:
                if pause_start is not None:
                    with self._lock:
                        self.total_paused_time += time.time() - pause_start
                instruction = self._consume_instruction()
                with self._lock:
                    self.state = InterruptState.IDLE
                if instruction and logger:
                    logger.info(f"Human interrupt committed: {instruction[:80]}...")
                return instruction

            if logger:
                logger.warning(f"Unexpected HCIx state {state!r}; resetting to IDLE.")
            with self._lock:
                self.state = InterruptState.IDLE
            return None

    async def apoll(self, logger: Any = None) -> Optional[str]:
        """
        Poll asynchronously for a committed instruction.

        If the prompt is open, this awaits until the user submits or cancels.
        """
        self._log_registration_issue(logger)
        pause_start = None
        while True:
            state = self.check_state()

            if state == InterruptState.IDLE:
                if pause_start is not None:
                    with self._lock:
                        self.total_paused_time += time.time() - pause_start
                return None

            if state == InterruptState.WRITING:
                if pause_start is None:
                    pause_start = time.time()
                    if logger:
                        logger.info("Human interrupt detected. Waiting for HCIx input.")
                await asyncio.sleep(self.poll_interval)
                continue

            if state == InterruptState.COMMITTED:
                if pause_start is not None:
                    with self._lock:
                        self.total_paused_time += time.time() - pause_start
                instruction = self._consume_instruction()
                with self._lock:
                    self.state = InterruptState.IDLE
                if instruction and logger:
                    logger.info(f"Human interrupt committed: {instruction[:80]}...")
                return instruction

            if logger:
                logger.warning(f"Unexpected HCIx state {state!r}; resetting to IDLE.")
            with self._lock:
                self.state = InterruptState.IDLE
            return None

    def stop(self) -> None:
        """Stop background hotkey listeners."""
        self._stop_event.set()
        listener = self._listener
        if listener is not None and hasattr(listener, "stop"):
            try:
                listener.stop()
            except Exception:
                pass

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
