# Architecture

This is a living description of the system as built. For the reasoning behind each
major choice, see the ADRs in [`decisions/`](decisions/); for how the design would
extend to production concerns not built here, see [`theory/`](theory/). The original
proposal is [`superpowers/specs/2026-07-15-e-commerce-market-agent-design.md`](superpowers/specs/2026-07-15-e-commerce-market-agent-design.md).

## The three layers

```
app/
├── tools/     Layer 1 — pure, LangGraph-unaware, unit-testable
├── agent/     Layer 2 — LangGraph StateGraph over the tools
├── llm/       DeepSeek client, used only by the agent layer
├── core/      Shared config / logging / report schema / errors
└── api/       )
    ui/        ) Layer 3 — interface: FastAPI (the real product) + Streamlit (its client)
```

**1. Tools (`app/tools/`)** — four tools behind a common `BaseTool` interface
(`app/tools/base.py`). `BaseTool.run(**kwargs)` times the call, catches any exception,
and always returns a `ToolResult(tool, ok, data, error, duration_ms)` — a tool never
raises out of `run()`, and the caller always gets a structured result whether it
succeeded or not. No tool imports LangGraph; each is independently unit-testable.

| Tool | File | Responsibility | Data strategy |
|---|---|---|---|
| `WebScraperTool` | `app/tools/web_scraper.py` | Product price + competitor prices | Live fetch from DummyJSON when `ENABLE_LIVE_SCRAPE=true`, else (or on any failure) deterministic mock — [ADR 0004](decisions/0004-scrape-with-mock-fallback.md) |
| `SentimentAnalyzerTool` | `app/tools/sentiment_analyzer.py` | Classify a mock review corpus, extract themes | Deterministic keyword-based classifier over `mockdata.mock_reviews()` |
| `TrendAnalyzerTool` | `app/tools/trend_analyzer.py` | Price/popularity direction over time | Simulated time-series (`mockdata.mock_series()`) |
| `ReportGeneratorTool` | `app/tools/report_generator.py` | Compile everything into a validated `MarketReport` | Pure compilation, no external calls |

**2. Agent (`app/agent/`)** — a LangGraph `StateGraph` over a typed `AgentState`
(`app/agent/state.py`, a `TypedDict` with an `operator.add`-reduced `errors` list so
parallel branches can each append their own error without clobbering the other's). The
graph is built and compiled once at import time (`app/agent/graph.py::_GRAPH`) and
invoked per request via `run_analysis(product, marketplace)`. The LLM (DeepSeek, via
`app/llm/deepseek.py`) is called **only** inside `plan_node` and `synthesize_node`
(`app/agent/nodes.py`); every other node is deterministic Python calling exactly one
tool. See [ADR 0001](decisions/0001-langgraph-over-native-and-react.md) for why this
shape was chosen over ReAct/Supervisor, and [ADR 0002](decisions/0002-deepseek-llm.md)
for the LLM client.

**3. Interface** — FastAPI (`app/api/`) is the real product: `POST /analyze`,
`GET /analyses/{id}`, `GET /health` (`app/api/routes.py`), backed by an in-memory
result store + TTL cache (`app/api/store.py`). Streamlit (`app/ui/streamlit_app.py`) is
**only an HTTP client** of that API — it never imports `app.agent` or `app.tools` —
see [ADR 0003](decisions/0003-streamlit-ui.md).

## The graph

```
                                 ┌───────────────┐
 START ──▶ plan (LLM) ──▶ scrape │ (web_scraper) │
                                 └───────┬───────┘
                                         │  fan-out
                       ┌─────────────────┴─────────────────┐
                       ▼                                   ▼
              sentiment (sentiment_analyzer)        trend (trend_analyzer)
                       │                                   │
                       └─────────────────┬─────────────────┘
                                         │  fan-in
                                         ▼
                          synthesize (LLM) ──▶ report (report_generator) ──▶ END
```

- `plan_node` — LLM call #1. Normalizes the free-text product name and resolves the
  marketplace; on failure (exception, unparsable JSON) falls back to the raw input and
  records the error, so the pipeline always proceeds with *some* product/marketplace.
- `scrape_node` / `sentiment_node` / `trend_node` — one tool call each. Each interprets
  `ToolResult.ok`: success feeds `state[...]` from `result.data`; failure feeds a safe
  zero-valued fallback dict *and* appends `{tool, error}` to `state.errors`. `scrape`
  runs first (its output — competitor prices — isn't needed by sentiment/trend, but it
  establishes the product context); `sentiment` and `trend` then run **in parallel**
  (LangGraph fan-out from a shared predecessor, fan-in at their shared successor) —
  genuine concurrent execution of two independent tool calls, not simulated.
- `synthesize_node` — LLM call #2. Takes the accumulated scrape/sentiment/trend data
  and produces `{"summary": ..., "recommendations": [...]}`; on failure/missing keys,
  falls back to a generic summary plus a "review the data manually" recommendation and
  records the error.
- `report_node` — pure compilation. Assembles everything (including every warning
  collected in `state.errors`, rendered as human-readable strings) into a `MarketReport`
  (`app/core/report.py`), a Pydantic v2 model, and returns its `model_dump()`.
- **Graceful degradation** is a structural property of this graph, not a special case:
  every tool-calling node always runs (there is no LLM decision that could skip a
  node), and every node absorbs its own tool's failure into a fallback value plus an
  error entry rather than raising — so the graph *always* reaches `report_node` and
  produces a report, complete or partial. `state.errors` accumulates via
  `Annotated[list[dict], operator.add]`, so the parallel `sentiment`/`trend` branches
  can both report independent failures without one overwriting the other.

## Request lifecycle

```
Streamlit UI                FastAPI                    LangGraph agent              Tools
─────────────                ───────                    ───────────────              ─────
 form submit
   │  POST /analyze
   │  {product, marketplace}
   ▼
                        route: analyze()
                          │
                          ├─ store.get_cached(product, marketplace)  ──▶ HIT: return cached MarketReport
                          │                                                (X-Cache: HIT)
                          └─ MISS ──▶ run_analysis(product, marketplace)
                                         │
                                         ▼
                                    _GRAPH.invoke(initial_state)
                                         │
                                         ├─ plan_node ──────────────▶ DeepSeek (plan)
                                         ├─ scrape_node ────────────▶ WebScraperTool
                                         ├─ sentiment_node ─────────▶ SentimentAnalyzerTool  ┐ parallel
                                         ├─ trend_node ─────────────▶ TrendAnalyzerTool       ┘
                                         ├─ synthesize_node ────────▶ DeepSeek (synthesize)
                                         └─ report_node ────────────▶ ReportGeneratorTool
                                         │
                                         ▼
                                    MarketReport (validated)
                          │
                          ├─ store.save(report)  → analysis_id, cached under (product, marketplace)
                          │  (X-Cache: MISS, X-Analysis-Id: <id>)
                          ▼
   ◀── AnalyzeResponse (= MarketReport JSON) ──
 render report:
 summary, metrics,
 recommendations,
 charts (bar/line via pandas)
```

Where each responsibility lives:

| Responsibility | Lives in |
|---|---|
| HTTP contract, request validation | `app/api/schemas.py` (`AnalyzeRequest`/`AnalyzeResponse`), `app/api/routes.py` |
| Result cache + history (demo-scope: in-memory) | `app/api/store.py` — see [`theory/04-data-storage.md`](theory/04-data-storage.md) for the production design |
| Orchestration / control flow | `app/agent/graph.py`, `app/agent/nodes.py` |
| Typed pipeline state | `app/agent/state.py` |
| LLM prompts | `app/agent/prompts.py` |
| LLM client | `app/llm/deepseek.py` — see [ADR 0002](decisions/0002-deepseek-llm.md) |
| Tool logic + mock data | `app/tools/*.py`, `app/tools/mockdata.py` |
| Report schema (source of truth for both API response and UI rendering) | `app/core/report.py` |
| Settings (env-driven) | `app/core/config.py` |
| UI rendering | `app/ui/streamlit_app.py` — see [ADR 0003](decisions/0003-streamlit-ui.md) |

## Configuration surface

All runtime behavior is controlled via environment variables read into
`app/core/config.py::Settings` (see `.env.example`): `DEEPSEEK_API_KEY`,
`DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`, `REQUEST_TIMEOUT`, `CACHE_TTL`,
`ENABLE_LIVE_SCRAPE` (default `false` — [ADR 0004](decisions/0004-scrape-with-mock-fallback.md)),
`API_URL` (read by the UI, not the API). No secret is hardcoded or committed.

## Deployment

Two containers from one codebase — `api` (uvicorn/FastAPI) and `ui` (Streamlit) — run
via `docker-compose up` locally, and as two Render (or Railway) web services in the
cloud via `render.yaml`. See [ADR 0005](decisions/0005-deploy-render-railway.md) for the
full rationale, including the Render hostname-injection quirk the UI normalizes.

## Where the design stops and theory begins

Per the brief's scope (programming = steps 1–3; steps 4–7 = theory answers), this repo
implements the architecture above with in-memory persistence, synchronous request
handling, and no automated eval/feedback harness. The corresponding production designs
are documented, not built:

- [`theory/04-data-storage.md`](theory/04-data-storage.md) — Postgres/Redis/object-storage
  schema for analysis results, history, cache, and agent configs.
- [`theory/05-monitoring-observability.md`](theory/05-monitoring-observability.md) —
  tracing, metrics, alerting, and output-quality evaluation.
- [`theory/06-scaling-optimization.md`](theory/06-scaling-optimization.md) — async
  workers/queue, horizontal scaling, LLM cost controls, intelligent caching, and
  parallelization beyond the graph's built-in fan-out.
- [`theory/07-continuous-improvement.md`](theory/07-continuous-improvement.md) —
  LLM-as-judge scoring, prompt A/B testing, user feedback loops, and capability
  evolution.

## Keeping this document current

Whenever the graph shape, tool set, or interface boundary changes, update this file in
the same change — and if the change reflects a real design decision (not just an
implementation detail), add a new ADR in [`decisions/`](decisions/) rather than only
updating this narrative (see `CLAUDE.md`'s knowledge-layer guidance).
