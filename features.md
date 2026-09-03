# autourgos-hcix — Features

A middleware for [Autourgos](https://github.com/devxjitin) agents that lets a human operator interrupt a
long-running agent run mid-flight — via a global hotkey or a programmatic call — and inject a
high-priority instruction that steers the agent's next reasoning step. It also ships lower-level
approval primitives for "worker thread blocks until a human decides" workflows.

## Full Feature List

- **Global-hotkey live steering** — press a configurable shortcut (default `ctrl+shift+h`) during a run,
  type a correction, and the next reasoning step picks it up
- **Programmatic interrupts** (`CognitiveInterruptManager.submit_instruction()`) — no keyboard needed,
  usable from tests, APIs, dashboards, notebooks
- **Headless/autonomous mode** (`CognitiveInterruptManager.headless()`) — skip the hotkey listener
  entirely for server/container/cloud deployments with no `DISPLAY`, and drive interrupts from an
  external control plane instead; also degrades safely on its own if no `DISPLAY`/`WAYLAND_DISPLAY`
  is present
- **Human approval primitives** — `HumanInterrupt`, `HumanInterruptHandler`, `HumanStateEditor` for
  blocking-worker-thread-until-human-decides (approve/edit) workflows
- **Injection into two places** — the override text goes into `agent.system_prompt` and, when the host
  agent exposes it, directly into `agent.scratchpad` (both configurable via
  `inject_into_system_prompt`/`inject_into_scratchpad`)
- **Native on Windows** via `RegisterHotKey`; optional `pynput` extra for Linux/macOS; Tkinter desktop
  prompt with console-prompt fallback
- **Sync and async agent runs** use the same lifecycle hooks
- **Guaranteed cleanup** — hotkey listeners unregister on run end or error, with total-paused-time logging
- Depends on `autourgos-agent`'s `CallbackHandler` interface; standard middleware hooks
  (`on_iteration_start`, `on_iteration`, `on_agent_end`/`on_agent_error`)

---

## Competitor Comparison

This is a narrow, single-purpose primitive (live keyboard interrupt + instruction injection for one
in-process agent loop), not a full orchestration platform. The closest real comparisons are
LangChain/LangGraph's human-in-the-loop (HITL) machinery, which solves a related but distinctly
different problem: pausing before a specific tool call for approve/edit/reject, backed by durable
graph-state persistence, rather than live free-text steering mid-reasoning.

| Capability | **autourgos-hcix** | [LangChain `HumanInTheLoopMiddleware`](https://docs.langchain.com/oss/python/langchain/human-in-the-loop) | [LangGraph interrupts](https://docs.langchain.com/oss/python/langchain/human-in-the-loop) |
|---|---|---|---|
| Scope | In-process middleware, no separate service | In-process middleware (LangChain agents) | Graph-runtime primitive (LangGraph) |
| Trigger model | Any time, via hotkey or explicit call — operator-initiated | Declarative: pauses only on tools listed in `interrupt_on` | `interrupt()` call inside a graph node |
| What the human provides | Free-text instruction injected into context | Structured decision: approve / edit / reject / respond | Arbitrary resume value |
| Live keyboard hotkey support | Yes, built-in (`RegisterHotKey`/`pynput`) | No — needs an external UI/API to deliver the decision | No — needs an external UI/API |
| Persistence across process restarts | No — in-memory, tied to the running process | Via checkpointer (e.g. `InMemorySaver` or a durable store) | Yes — graph state snapshot at the interrupt point |
| Designed for | Steering an agent's reasoning generally, at any point | Gating specific sensitive tool calls before execution | Pausing/resuming a stateful graph workflow |
| Headless/server operation | Yes, explicit `headless()` mode | Yes (it's UI-agnostic; decision delivery is on you) | Yes (resume is a separate call) |
| Requires a specific framework | `autourgos-agent` (for `CallbackHandler`) | LangChain agents | LangGraph |
| Pricing | Free, open source | Free, open source | Free, open source |

### How to read this

- autourgos-hcix and LangChain/LangGraph's HITL tools solve adjacent but different problems: hcix is
  about a human *redirecting* an agent's train of thought at will (closer to "yelling a correction
  across the room"), while LangChain/LangGraph HITL is about *gating specific actions* with a
  structured approve/edit/reject decision, backed by durable state so the pause can survive a
  process restart.
- hcix's differentiator is the literal global-hotkey listener — press a key combo from anywhere and
  type an instruction — which the LangChain/LangGraph primitives don't provide out of the box; they
  assume you build your own delivery UI (chat message, API call, dashboard button) around the
  `interrupt`/decision object.
- LangChain/LangGraph's differentiator is durable, resumable state: a LangGraph interrupt can survive
  a crash or redeploy because the checkpointer persists the paused state; hcix's manager is in-memory
  and tied to the live process.
- hcix also ships generic approval primitives (`HumanInterruptHandler`, `HumanStateEditor`) that
  overlap conceptually with LangChain's approve/edit decision types, but without the graph-level
  persistence guarantees.

Sources:
- [Human-in-the-loop - Docs by LangChain](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- [How to Build a Human-in-the-Loop AI Agent with LangChain & LangGraph](https://medium.com/@syeedmdtalha/how-to-build-a-human-in-the-loop-ai-agent-with-langchain-langgraph-26f2f5d2b83e)
- [Human in the Loop Middleware in Python: Building Safe AI Agents with Approval Workflows | FlowHunt](https://www.flowhunt.io/blog/human-in-the-loop-middleware-python-safe-ai-agents/)
- [Architecting Human-in-the-Loop Agents: Interrupts, Persistence, and State Management in LangGraph](https://medium.com/data-science-collective/architecting-human-in-the-loop-agents-interrupts-persistence-and-state-management-in-langgraph-fa36c9663d6f)
- [humanInTheLoopMiddleware | langchain | LangChain Reference](https://reference.langchain.com/javascript/langchain/index/humanInTheLoopMiddleware)
