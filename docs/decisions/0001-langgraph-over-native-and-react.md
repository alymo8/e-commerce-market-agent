# 0001 — LangGraph with a structured graph + LLM planner, over ReAct and Supervisor

## Status

Accepted (2026-07-15).

## Context

The brief asks for an *intelligent agent* that orchestrates several specialized tools
(scraper, sentiment analyzer, trend analyzer, report generator) into a market-analysis
report. The test explicitly rewards clarity, robustness, and justified choices over
raw sophistication, and the additions requested beyond the brief call out **LangGraph**
by name. That still leaves a real design choice: *what shape does the agent take inside
LangGraph?* Three patterns were on the table:

1. **ReAct** (`langgraph.prebuilt.create_react_agent`) — a single LLM loop that decides,
   at every step, which tool to call next, observes the result, and loops until it
   emits a final answer.
2. **Supervisor / worker** — a top-level "supervisor" LLM that routes work to
   specialized sub-agents (each themselves possibly LLM-driven), common in
   multi-agent LangGraph examples.
3. **Structured graph + LLM planner** — a fixed `StateGraph` with named nodes wired by
   explicit edges; the LLM is invoked only inside specific nodes (`plan`,
   `synthesize_report`), and all tool-calling nodes are plain deterministic Python.

## Decision

Use a **structured graph with an LLM planner**, implemented in `app/agent/graph.py`:

```
START -> plan (LLM) -> scrape -> [ sentiment || trend ] (parallel) -> synthesize (LLM) -> report -> END
```

- `plan_node` calls the LLM once to normalize the product name and resolve/validate the
  marketplace (`app/agent/nodes.py::plan_node`, prompt in `app/agent/prompts.py`).
- `scrape_node`, `sentiment_node`, `trend_node`, `report_node` are deterministic: they
  call one tool each (`app/tools/*`) and shape the result into `AgentState`. No LLM,
  no branching decisions — the tool to call is fixed by which node it is.
- `synthesize_node` calls the LLM once more to turn the four data sources into an
  executive summary and recommendations.
- The graph itself, not the LLM, encodes the fan-out/fan-in: `scrape -> sentiment`,
  `scrape -> trend` (parallel), then `sentiment -> synthesize` and `trend -> synthesize`
  (LangGraph waits for both incoming edges before running `synthesize`).

## Alternatives considered

**ReAct (`create_react_agent`).** The LLM sees all four tools and freely decides order,
repetition, and when to stop. Rejected because:
- It makes the control flow non-deterministic: two runs of the same product could call
  tools in a different order, skip a tool, or call one twice, which is hard to
  demonstrate/test and hard to reason about in a report generator that expects to
  always have `scrape` + `sentiment` + `trend` before `synthesize`.
- It puts the LLM in the loop for *every* tool call, multiplying DeepSeek calls (cost
  and latency) for a task whose tool sequence is actually fixed and known ahead of
  time — analyzing a product always needs price, sentiment, and trend data, in that
  dependency order.
- Parallel tool execution (fan-out/fan-in) is not something ReAct expresses naturally;
  it plans and calls tools one at a time from the single agent loop, so it would not
  demonstrate LangGraph's native parallelism.

**Supervisor / worker.** A supervisor LLM routes to specialized sub-agents (e.g. a
"data collection" agent, an "analysis" agent). Rejected because:
- It adds LLM calls purely for routing decisions that, for four fixed tools invoked in
  a fixed dependency order, have no real ambiguity to resolve — the supervisor would
  always route the same way, so the extra LLM calls buy nothing.
- It adds a layer of indirection (sub-agent state, routing tokens) that is harder to
  debug and doesn't map cleanly onto `AgentState`, a flat `TypedDict` that every node
  reads and writes directly.
- The brief rewards clarity; a supervisor of workers, each themselves possibly agentic,
  is more graph than the problem calls for.

## Consequences

- **Determinism and debuggability.** Every run takes the same path through the graph;
  the only variance is the *content* of the two LLM calls, not *which* nodes run. This
  makes the mocked-LLM end-to-end test (see `tests/`) simple: replace `complete_json`
  and assert on the fixed node sequence.
- **Demonstrable parallelization.** `sentiment` and `trend` genuinely fan out from
  `scrape` and fan in to `synthesize` — a direct, visible use of LangGraph's graph
  semantics rather than something implied by prose.
- **Lower LLM cost and blast radius.** DeepSeek is invoked exactly twice per analysis
  (`plan`, `synthesize`); everything else is pure Python behind `BaseTool.run()`. This
  bounds spend and means most of the pipeline is exercised without ever calling out to
  DeepSeek in tests.
- **Cost of the choice:** the graph shape is fixed in code. Adding a new *decision
  type* (e.g. "compare two products" or "monthly trend-only report") is not something
  the current agent can improvise — it means editing `app/agent/graph.py` to add nodes
  and edges (and probably a new field on `AgentState`), not just teaching the LLM a new
  trick. This is an accepted trade-off: the four tools stay behind the same `BaseTool`
  interface (`app/tools/base.py`), so extending the *tool* surface is contained and
  low-risk even though extending the *graph shape* is not automatic.
- **Graceful degradation is a graph property, not an LLM property.** Because tool nodes
  are deterministic and always run (there's no LLM decision to skip a step), a failing
  tool just records an error in `state.errors` (`operator.add`-reduced list) and returns
  a safe fallback payload; the graph still reaches `report_node` and produces a partial
  report instead of aborting. See `app/agent/nodes.py`.
