# Changelog

## [3.1.2] - 2026-09-01

- Fixed: `_restore_system_prompt` used a global substring `.replace()` to
  remove each injected override block, which strips *every* occurrence of
  that text — including one that legitimately pre-existed in the agent's
  base prompt before this run's injection, not just the one HCIx itself
  added. It now restores the exact pre-injection snapshot taken in
  `on_agent_start` instead.

## [3.1.0] - 2026-08-30

- BREAKING: dependency migrated from `autourgos-react-agent>=1.6.0` (the
  pre-fork legacy package) to `autourgos-agent>=2.0.2`. `autourgos-react-agent`
  still carries its original loop bugs (denied tool calls never firing
  `on_tool_end`, an async `approval_callback` silently always-approving under
  `invoke()`, no duck-typed tool support, an unbounded tool-call thread pool)
  that `autourgos-agent` 2.0.2 fixed — staying on the old dependency meant
  this middleware ran against an agent loop with unfixed bugs regardless of
  fixes made downstream. All `ReactAgent` references in code/docs/tests are
  now `Agent`, matching the current package name.

## [3.0.0] - 2026-07-27

- BREAKING: requires autourgos-react-agent>=1.6.0.
- Fixed: `inject_into_scratchpad` was silently broken against a real
  `ReactAgent` due to missing scratchpad support in the core agent (fixed
  in react-agent 1.6.0); this release wires this package up to the new
  real contract. `agent.scratchpad` is now a genuine, live instance
  attribute, so a human override injected here actually appears in the
  agent's next LLM call, not just in a local loop variable that was never
  externally readable.
- Tests rewritten to run against `make_test_agent()` (a real `ReactAgent`)
  instead of hand-rolled fake agents, and now assert that after triggering
  a human override, `agent.scratchpad` actually contains the injected
  override text.

## [2.1.1] - 2026-07-27

- Added: module logger; hotkey-listener shutdown failures in stop()/__del__ are now logged instead of silently swallowed. Docs: fixed undefined my_llm/my_tool placeholders.

## 2.1.0 - 2026-07-27

- Added: narrates its own actions into the host ReactAgent's verbose trace via
  `agent.logger.middleware(...)` when available (see autourgos-react-agent's
  README for the pattern). Purely additive and defensive — no crash if the
  host agent has no `.logger`, no output when verbose=False, no existing
  logging affected (this package has no stdlib logging).

## 2.0.0 - 2026-07-27

- BREAKING: this package now depends on autourgos-react-agent>=1.1.0
  (previously zero-dependency). `CallbackHandler` is now re-exported from
  autourgos-react-agent instead of being duplicated locally, to eliminate
  interface drift risk. No public API/behavior change for typical usage —
  `CallbackHandler`'s method signatures and semantics are unchanged.

## 1.0.1 - 2026-07-27

- Fixed a bug where the Windows global hotkey ID used by `CognitiveInterruptManager`
  was a fixed constant, causing `RegisterHotKey`/`UnregisterHotKey` to collide when
  two or more manager instances ran in the same OS process at the same time. Each
  instance now gets a unique hotkey ID from a process-wide counter, kept within the
  valid Windows app-defined hotkey ID range (0x0000-0xBFFF). The default shortcut
  (`ctrl+shift+h`) and the public constructor signature are unchanged.

## 1.0.0 - 2026-07-05

- Rebuilt HCIx as a self-contained PyPI package for the current Autourgos workspace.
- Added typed package exports under `autourgos_hcix`.
- Added global hotkey interrupt manager with Windows native hotkeys and optional `pynput` support for Linux/macOS.
- Added `HcixInterruptMiddleware` with sync lifecycle hooks for Autourgos agents.
- Added programmatic interrupt primitives: `HumanInterrupt`, `HumanInterruptHandler`, and `HumanStateEditor`.
- Added production packaging metadata, README, license, `py.typed`, and smoke tests.
