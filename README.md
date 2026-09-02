# autourgos-hcix

[![Framework: Autourgos](https://img.shields.io/badge/Framework-Autourgos-orange.svg)](https://github.com/devxjitin)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://pypi.org/project/autourgos-hcix/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg)](https://github.com/devxjitin/autourgos-hcix/blob/main/LICENSE)
[![Author](https://img.shields.io/badge/Author-Jitin%20Kumar%20Sengar-blue.svg)](https://github.com/devxjitin)
[![Contributor](https://img.shields.io/badge/Contributor-Sonia-blueviolet.svg)](https://github.com/dahiyasonia)
[![Contributor](https://img.shields.io/badge/Contributor-Vishwanil%20Suman-blueviolet.svg)]()

Human Cognitive Interrupt (HCIx) middleware for [Autourgos](https://github.com/devxjitin) agents. Press a
global shortcut during a long-running agent task, type a high-priority instruction, and the middleware
injects it so the next reasoning step is steered by the human operator.

```python
from autourgos_hcix import HcixInterruptMiddleware
from autourgos_agent import Agent
from autourgos_openaichat import OpenAIChatModel

middleware = HcixInterruptMiddleware(shortcut="ctrl+shift+h")
agent = Agent(llm=OpenAIChatModel(model="gpt-4o-mini"), middleware=[middleware], verbose=True)
result = agent.invoke("Research this task and keep working until you have a final answer.")
```

---

## Features

- **Global-hotkey live steering** — interrupt a running agent, type a correction, and the next reasoning
  step picks it up
- **Programmatic interrupts** — submit an instruction without a keyboard, for tests, APIs, dashboards,
  notebooks
- **Human approval primitives** — `HumanInterrupt`, `HumanInterruptHandler`, `HumanStateEditor` for
  worker-thread-blocks-until-a-human-decides workflows
- **Native on Windows** (`RegisterHotKey`), `pynput` optional extra for Linux/macOS
- **Cleanup guaranteed** — hotkey listeners unregister on run end or error

---

## Table of Contents

- [Why Use This?](#why-use-this)
- [Install](#install)
- [Quick Start](#quick-start)
- [Async Usage](#async-usage)
- [Programmatic Interrupts](#programmatic-interrupts)
- [Human Approval Primitives](#human-approval-primitives)
- [Agent Hooks](#agent-hooks)
- [Constructor Parameters](#constructor-parameters)
- [License](#license)

---

## Why Use This?

Long-running agents sometimes need live human steering:

- **Stop drift** — redirect an agent when its current plan is no longer useful
- **Inject new context** — add fresh information without restarting the run
- **Pause for operator input** — wait while a person writes a corrective instruction
- **Keep cleanup reliable** — unregister hotkey listeners when the run ends or errors

`HcixInterruptMiddleware` depends on `autourgos-agent` (for the shared `CallbackHandler` interface).

---

## Install

```bash
pip install autourgos-hcix
```

For global hotkey support on Linux/macOS, install the optional `pynput` extra:

```bash
pip install 'autourgos-hcix[hcix]'
```

Windows uses the native `RegisterHotKey` API. Tkinter is used for the desktop prompt when available;
otherwise HCIx falls back to a console prompt.

---

## Quick Start

`my_llm` is any chat-model instance, e.g. `OpenAIChatModel` from `autourgos-openaichat` (needs
`OPENAI_API_KEY` set). `my_tool` is any plain callable used as an agent tool.

```python
from autourgos_hcix import HcixInterruptMiddleware
from autourgos_agent import Agent
from autourgos_openaichat import OpenAIChatModel

my_llm = OpenAIChatModel(model="gpt-4o-mini")

def my_tool(query: str) -> str:
    return f"Result for: {query}"

middleware = HcixInterruptMiddleware(shortcut="ctrl+shift+h")

agent = Agent(
    llm=my_llm,
    tools=[my_tool],
    middleware=[middleware],
    verbose=True,
)

result = agent.invoke("Research this task and keep working until you have a final answer.")
print(result)
```

During the run, press `ctrl+shift+h`, type the new instruction, then send it. HCIx injects an authoritative
override block into the agent context. With `verbose=True`, HCIx also narrates the injection into the
agent's verbose trace:

```
[HCIx] Human override injected: 'Stop researching and summarize what you have so far.'
```

---

## Async Usage

```python
import asyncio

from autourgos_hcix import HcixInterruptMiddleware
from autourgos_agent import Agent

agent = Agent(
    llm=my_llm,
    tools=[my_tool],
    middleware=[HcixInterruptMiddleware(shortcut="ctrl+alt+k")],
)

async def main() -> None:
    result = await agent.ainvoke("Prepare a detailed cloud service comparison.")
    print(result)

asyncio.run(main())
```

HCIx uses the same lifecycle hooks in sync and async agent runs. When the user is actively writing an
interrupt, the hook waits until the instruction is submitted or cancelled.

---

## Programmatic Interrupts

Submit an interrupt without using a keyboard shortcut — useful for tests, APIs, dashboards, and notebooks.

```python
from autourgos_hcix import CognitiveInterruptManager, HcixInterruptMiddleware

manager = CognitiveInterruptManager(enable_hotkey=False)
middleware = HcixInterruptMiddleware(manager=manager)

manager.submit_instruction("Stop searching. Summarize only the sources already collected.")
```

At the next supported middleware hook, the instruction is consumed and injected once.

---

## Autonomous / Headless Agents

Global hotkeys and desktop prompts assume a human is sitting at a keyboard. An autonomous
agent running on a server, in a container, or in the cloud has neither — there's no `DISPLAY`
for `pynput` to bind to, and no one to press `ctrl+shift+h`.

For these deployments, skip the hotkey listener entirely and drive HCIx from your own control
plane (an API endpoint, a queue consumer, a supervisor process) instead:

```python
from autourgos_hcix import CognitiveInterruptManager, HcixInterruptMiddleware

manager = CognitiveInterruptManager.headless()
middleware = HcixInterruptMiddleware(manager=manager)

# elsewhere -- an API handler, a queue consumer, an operator dashboard:
manager.submit_instruction("Stop researching. Summarize what you have.")
```

`CognitiveInterruptManager.headless()` is shorthand for `enable_hotkey=False`. On a headless
box, `enable_hotkey=True` (the default) also degrades safely on its own -- no `DISPLAY`/
`WAYLAND_DISPLAY` means HCIx skips the hotkey listener without attempting to import `pynput` --
but for an autonomous deployment, being explicit is clearer than relying on that fallback.

---

## Human Approval Primitives

```python
from autourgos_hcix import HumanInterrupt, HumanInterruptHandler, HumanStateEditor

state = {"step": "delete_files", "count": 3}
edited = HumanStateEditor.edit(state, {"count": 2})

handler = HumanInterruptHandler()

# Worker thread:
# action, edits = handler.wait_for_human(timeout=60.0)

# UI/API thread later:
# handler.submit("approve", edited)
```

---

## Agent Hooks

HCIx uses standard Autourgos middleware hooks:

| Hook | Behavior |
|---|---|
| `on_iteration_start(iteration, agent=...)` | Polls before the next LLM call when the host agent exposes this hook. |
| `on_iteration(iteration, thought, ...)` | Polls after an iteration event. In `autourgos-agent`, this injects the override for the following reasoning step. |
| `on_agent_end` / `on_agent_error` | Stops hotkey listeners and logs total paused time. |

`agent.scratchpad` is a real, live instance attribute on `autourgos-agent`, so HCIx injects the override
directly into it (in addition to `agent.system_prompt`) and the running agent picks it up on its very next
LLM call.

---

## Constructor Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `shortcut` | `str` | `"ctrl+shift+h"` | Global hotkey, such as `"ctrl+shift+h"` or `"ctrl+alt+k"`. |
| `manager` | `CognitiveInterruptManager` | `None` | Optional preconfigured manager for tests or custom UIs. |
| `poll_interval` | `float` | `0.25` | Seconds between checks while the human prompt is open. |
| `inject_into_system_prompt` | `bool` | `True` | Add override text to `agent.system_prompt` when available. |
| `inject_into_scratchpad` | `bool` | `True` | Add override text to `agent.scratchpad` when the agent exposes one. |
| `enable_hotkey` | `bool` | `True` | Start the global hotkey listener. Disable for tests, servers, and headless runs. |

---

## Requirements

- Python 3.9+
- Optional: `pynput` for non-Windows global hotkeys
- Optional: Tkinter for the desktop prompt UI

---

## License

Apache License 2.0, Copyright (c) 2026 Jitin Kumar Sengar
