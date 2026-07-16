# 05 — Monitoring and observability

> Theory answer (brief step 5). Nothing here is wired up in the running app beyond the
> plain `logging` calls already present (`app/core/logging.py`, used by
> `app/tools/base.py` and `app/agent/nodes.py`); this document is the design for a
> production deployment.

## Why this pipeline specifically needs both tracing and metrics

The agent has two qualitatively different failure/slowdown modes: a **tool** can be
slow or wrong (e.g. the live scrape times out, or the mock sentiment classifier
produces a nonsensical breakdown), or the **LLM** can be slow, wrong, or unparseable
(`plan`/`synthesize`). Metrics alone tell you *that* p95 latency spiked; only a trace
tells you *which node* in a specific run caused it. Both are needed.

## Tracing

- **LangSmith**, since the agent is already built on LangGraph — it captures a trace
  per `_GRAPH.invoke()` call automatically (each node, its inputs/outputs, timing), with
  no code change beyond setting `LANGCHAIN_TRACING_V2=true` and an API key. This gives,
  for free, exactly the per-node breakdown the graph in `app/agent/graph.py` already
  has structurally: `plan → scrape → {sentiment, trend} → synthesize → report`.
- **Alternative: OpenTelemetry spans per node**, for teams that want a
  vendor-neutral trace store (Jaeger/Tempo/Honeycomb) instead of LangSmith. Wrap each
  node function in `app/agent/nodes.py` with a span (`tracer.start_as_current_span("plan")`,
  etc.), tag it with `run_id` (already present on `AgentState`), and record whether the
  node fell back to a degraded result (`state.errors` non-empty for that tool). This is
  more setup than LangSmith but keeps trace data infra-agnostic.
- Either way, `run_id` (`AgentState.run_id`, a UUID minted once in
  `run_analysis()`) is the correlation key that ties a trace, its logs, and its
  eventual `analysis_events` row (see `04-data-storage.md`) together.

## Metrics

| Metric | Why it matters |
|---|---|
| **Latency per node** (p50/p95/p99 for `plan`, `scrape`, `sentiment`, `trend`, `synthesize`, `report`) | The graph fans out `sentiment`/`trend` in parallel specifically so total latency is `max(sentiment, trend)` not their sum — per-node latency is what proves that's actually happening in production, and pinpoints which node to optimize first. |
| **Tool success rate** (`ToolResult.ok` rate, per tool name) | Every tool already returns a uniform `ToolResult` with `ok`/`error` (`app/tools/base.py`) — this is a one-line aggregation away from a metric. A dropping success rate for `web_scraper` specifically would flag a live-scrape target (DummyJSON) becoming unreliable, independent of the mock fallback masking it in the report. |
| **LLM tokens / cost** (per call, split `plan` vs `synthesize`) | The two LLM nodes are the only spend in the pipeline (ADR 0002); tracking tokens per node catches prompt bloat (e.g. `synthesize`'s user message embeds the full scrape/sentiment/trend dicts — this can grow) before it shows up as a cost surprise. |
| **Cache hit rate** (`X-Cache: HIT` vs `MISS` — already emitted as a response header in `app/api/routes.py::analyze`) | Directly measures how much load the TTL cache (`app/api/store.py`, `04-data-storage.md`) is absorbing; a falling hit rate under steady traffic patterns suggests the TTL is too short or the cache key is too specific. |
| **Error rate** (fraction of runs with any `state.errors` entry, i.e. partial reports) | The graph's whole graceful-degradation design (ADR 0001) means a "failed" run rarely 500s — it silently becomes a partial report instead. Without this metric, degraded quality is invisible; `report.warnings` (rendered as a UI banner in `app/ui/streamlit_app.py`) is the per-request signal, this metric is the aggregate. |
| **Partial-report rate, by which tool degraded** | A refinement of error rate: is it always the scraper falling back to mock (expected, low severity) or is `synthesize` failing (LLM/JSON-parsing issue, higher severity since it means the recommendations are the generic fallback text in `nodes.py::synthesize_node`)? |
| **End-to-end request latency** (`POST /analyze` wall time) | The number the UI's spinner and any evaluator actually feels; should track sum/max of node latencies plus HTTP/serialization overhead — a growing gap between "node latencies look fine" and "end-to-end is slow" points at something outside the graph (FastAPI, network, DeepSeek connection setup). |

## Alerting

- **Error-rate threshold**: alert if partial-report rate over a rolling window (e.g. 15
  min) exceeds a baseline (e.g. >10% of runs have any `state.errors` entry) —
  Prometheus recording rule + Alertmanager, or the equivalent in a hosted APM
  (Datadog/Grafana Cloud monitors) if not self-hosting Prometheus.
- **Latency threshold**: alert on p95 end-to-end latency crossing a bound (e.g. > 20s,
  given `request_timeout` defaults to 20s per external call in
  `app/core/config.py`) — a sustained breach usually means either DeepSeek or the
  live-scrape target is degraded.
- **Hard-down**: `GET /health` (already implemented, `app/api/routes.py`) polled by the
  hosting platform (Render/Railway) and by an external uptime check; page on
  consecutive failures.
- Route alerts by severity: LLM/JSON-parse failures (degrade silently to a fallback
  summary today) are a warning, not a page; the API being unreachable or Postgres/Redis
  being down is a page.

## Output quality

Latency and error-rate metrics say nothing about whether a *successful* report is
actually good — a `synthesize_node` call can return valid JSON with a bland or wrong
summary and every metric above stays green. Two complementary checks:

- **LLM-as-judge sampling**: periodically sample completed reports (e.g. 5% of runs, or
  every run with `warnings` present, which is the riskier case) and have a separate,
  higher-quality LLM call score the `summary`/`recommendations` against the underlying
  `price`/`sentiment`/`trend` data on a rubric (grounded in the data? actionable?
  internally consistent?) — store the score alongside the `analyses` row so quality can
  be tracked over time and correlated with prompt versions (see
  [`07-continuous-improvement.md`](07-continuous-improvement.md)).
- **Schema validation as a quality floor**: `MarketReport` (`app/core/report.py`) being
  a Pydantic v2 model already guarantees *structural* quality (every report has the
  required fields, correctly typed) — this is a cheap, always-on check that should be
  tracked as its own metric (validation failure rate) even though it says nothing about
  semantic quality.

## Key metrics to watch first (short list)

If only instrumenting a handful of things on day one: **tool success rate per tool**,
**partial-report rate**, **p95 end-to-end latency**, **cache hit rate**, and **LLM cost
per day**. These five catch the failure modes most specific to this architecture
(degraded tools hiding behind graceful fallback, cache not doing its job, and LLM spend
creeping) that generic uptime/latency dashboards would miss.
