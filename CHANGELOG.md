# Changelog

## 1.0.0 - 2026-07-05

- Rebuilt HCIx as a self-contained PyPI package for the current Autourgos workspace.
- Added typed package exports under `autourgos_hcix`.
- Added global hotkey interrupt manager with Windows native hotkeys and optional `pynput` support for Linux/macOS.
- Added `HcixInterruptMiddleware` with sync lifecycle hooks for Autourgos agents.
- Added programmatic interrupt primitives: `HumanInterrupt`, `HumanInterruptHandler`, and `HumanStateEditor`.
- Added production packaging metadata, README, license, `py.typed`, and smoke tests.
