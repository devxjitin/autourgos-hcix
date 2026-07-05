# autourgos-hcix

Human Cognitive Interrupt (HCIx) middleware for [Autourgos](https://github.com/devxjitin) agents.

Press a global shortcut during a long-running agent task, type a high-priority instruction, and the middleware injects that instruction into the agent so the next reasoning step is steered by the human operator.

---

## Why use this?

Long-running agents sometimes need live human steering:

- **Stop drift** - redirect an agent when its current plan is no longer useful
- **Inject new context** - add fresh information without restarting the run
- **Pause for operator input** - wait while a person writes a corrective instruction
- **Keep cleanup reliable** - unregister hotkey listeners when the run ends or errors

`HcixInterruptMiddleware` is self-contained and has zero required runtime dependencies.

---

## Install

```bash
pip install autourgos-hcix
```

For global hotkey support on Linux/macOS, install the optional `pynput` extra:

```bash
pip install 'autourgos-hcix[hcix]'
```

Windows uses the native `RegisterHotKey` API. Tkinter is used for the desktop prompt when available; otherwise HCIx falls back to a console prompt.

---

## Quick Start

```python
from autourgos_hcix import HcixInterruptMiddleware
from autourgos_react_agent import ReactAgent

middleware = HcixInterruptMiddleware(shortcut="ctrl+shift+h")

agent = ReactAgent(
    llm=my_llm,
    tools=[my_tool],
    middleware=[middleware],
    verbose=True,
)

result = agent.invoke("Research this task and keep working until you have a final answer.")
print(result)
```

During the run, press `ctrl+shift+h`, type the new instruction, then send it. HCIx injects an authoritative override block into the agent context.

---

## Async Usage

```python
import asyncio

from autourgos_hcix import HcixInterruptMiddleware
from autourgos_react_agent import ReactAgent

agent = ReactAgent(
    llm=my_llm,
    tools=[my_tool],
    middleware=[HcixInterruptMiddleware(shortcut="ctrl+alt+k")],
)

async def main() -> None:
    result = await agent.ainvoke("Prepare a detailed cloud service comparison.")
    print(result)

asyncio.run(main())
```

HCIx uses the same lifecycle hooks in sync and async agent runs. When the user is actively writing an interrupt, the hook waits until the instruction is submitted or cancelled.

---

## Programmatic Interrupts

You can submit an interrupt without using a keyboard shortcut. This is useful for tests, APIs, dashboards, and notebooks.

```python
from autourgos_hcix import CognitiveInterruptManager, HcixInterruptMiddleware

manager = CognitiveInterruptManager(enable_hotkey=False)
middleware = HcixInterruptMiddleware(manager=manager)

manager.submit_instruction("Stop searching. Summarize only the sources already collected.")
```

At the next supported middleware hook, the instruction is consumed and injected once.

---

## Human Approval Primitives

The package also includes programmatic approval helpers.

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
| `on_iteration(iteration, thought, ...)` | Polls after an iteration event. In `autourgos-react-agent`, this injects the override for the following reasoning step. |
| `on_agent_end` / `on_agent_error` | Stops hotkey listeners and logs total paused time. |

The current `ReactAgent` keeps its scratchpad local to the loop, so HCIx injects into `agent.system_prompt` when no public scratchpad is available.

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

## Package Structure

```text
autourgos-hcix/
|-- autourgos_hcix/
|   |-- __init__.py
|   |-- base.py
|   |-- hcix.py
|   |-- interrupt.py
|   |-- middleware.py
|   `-- py.typed
|-- tests/
|   `-- test_hcix_interrupt.py
|-- CHANGELOG.md
|-- LICENSE
|-- README.md
`-- pyproject.toml
```

## Requirements

- Python 3.9+
- Optional: `pynput` for non-Windows global hotkeys
- Optional: Tkinter for the desktop prompt UI

---

## Links

- PyPI: https://pypi.org/project/autourgos-hcix/
- GitHub: https://github.com/devxjitin/autourgos-hcix
- Issues: https://github.com/devxjitin/autourgos-hcix/issues

---

## License

MIT - see [LICENSE](LICENSE)
