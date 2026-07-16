# e-commerce market-analysis agent

An intelligent agent that orchestrates four specialized tools — a web scraper, a
sentiment analyzer, a trend analyzer, and a report generator — behind a LangGraph
`StateGraph` to turn a free-text product name into a structured, validated market-
analysis report: current price and competitor prices, sentiment breakdown with themes,
price/popularity trend, an LLM-written executive summary, and prioritized
recommendations. It is exposed as a FastAPI REST API and visualized by a Streamlit
dashboard that talks to that API over plain HTTP.

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

The LLM (DeepSeek) is called **only** in `plan` (normalize the product name / resolve
the marketplace) and `synthesize` (turn collected data into a summary + recommendations).
Every other node is deterministic Python calling exactly one tool. Tool failures never
abort the run: each node absorbs its own tool's failure into a safe fallback value plus
an entry in `warnings`, so the graph always reaches `report` and returns a report —
complete, or partial with the degradation explained. See
[`docs/architecture.md`](docs/architecture.md) for the full request lifecycle.

## 1. Architecture

Three separated layers:

```
app/
├── tools/     Layer 1 — pure, LangGraph-unaware, unit-testable
│              (WebScraperTool, SentimentAnalyzerTool, TrendAnalyzerTool, ReportGeneratorTool)
├── agent/     Layer 2 — LangGraph StateGraph over the tools (plan/scrape/sentiment/trend/synthesize/report)
├── llm/       DeepSeek client, used only by the agent layer
├── core/      Shared config / logging / report schema / errors
└── api/       )
    ui/        ) Layer 3 — interface: FastAPI (the real product) + Streamlit (its client)
```

Every tool sits behind a common `BaseTool.run(**kwargs)` interface that times the call,
catches any exception, and always returns a `ToolResult(tool, ok, data, error,
duration_ms)` — a tool never raises out of `run()`. The Streamlit UI never imports
`app.agent` or `app.tools`; it is strictly an HTTP client of the FastAPI service.

**Why a structured graph with an LLM planner, instead of ReAct or a supervisor
pattern?** The four tools are always called in the same fixed dependency order
(price → sentiment/trend → synthesis) — there's no real routing decision for an LLM
to make, so putting the LLM in a ReAct loop for every tool call would only add cost,
latency, and non-determinism, and would not naturally express the fan-out/fan-in
parallelism between `sentiment` and `trend`. A fixed `StateGraph` with the LLM confined
to two well-defined nodes gives deterministic, debuggable, cheaply-tested control flow
while still doing the two things that genuinely need language understanding —
normalizing free-text input and writing the summary. Full rationale, alternatives
considered, and consequences: [ADR 0001](docs/decisions/0001-langgraph-over-native-and-react.md).

See also: [`docs/architecture.md`](docs/architecture.md) (living architecture
description, request lifecycle diagram, configuration surface) and the ADRs in
[`docs/decisions/`](docs/decisions/) for every other real design decision.

## 2. Quickstart (Docker)

```bash
cp .env.example .env
# edit .env and set DEEPSEEK_API_KEY=sk-...
docker compose up
```

- UI: http://localhost:8501
- API docs (Swagger): http://localhost:8000/docs

Two containers, one image: `api` (uvicorn/FastAPI on 8000) and `ui` (Streamlit on 8501,
pointed at `api` via Docker's internal DNS). No `DEEPSEEK_API_KEY`? The pipeline still
starts and still returns a valid report — see [§5 note on graceful
degradation](#graceful-degradation-without-an-api-key).

## 3. Quickstart (local Python)

Requires Python 3.13.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env   # set DEEPSEEK_API_KEY

uvicorn app.api.main:app --reload --port 8000
# in a second terminal
streamlit run app/ui/streamlit_app.py
```

## 4. API examples

**Health check**

```bash
curl http://localhost:8000/health
```
```json
{"status": "ok"}
```

**Run an analysis**

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"product": "iPhone 15", "marketplace": "amazon"}'
```

The response is a `MarketReport` (see [`sample_reports/iphone-15.json`](sample_reports/iphone-15.json)
for a full example), and two response headers carry request metadata:

- `X-Analysis-Id` — the id to fetch this exact result again via `GET /analyses/{id}`.
- `X-Cache` — `HIT` if this `(product, marketplace)` pair was served from the in-memory
  TTL cache, `MISS` if the graph actually ran.

```json
{
  "product": "iPhone 15",
  "marketplace": "amazon",
  "price": {"price": 1081.33, "currency": "USD", "source": "mock"},
  "competitors": [{"name": "BestBuy", "price": 1181.87}],
  "sentiment": {"positive": 10, "neutral": 2, "negative": 3, "total": 15,
                "top_positive_themes": ["amazing", "worth", "best"],
                "top_negative_themes": ["slow", "unhelpful", "expensive"]},
  "trend": {"direction": "up", "price_change_pct": 2.62,
            "price_history": [{"month": "2026-01", "price": 1049.67}],
            "popularity": [{"month": "2026-01", "value": 79.7}]},
  "summary": "iPhone 15 holds a premium price with strong positive sentiment ...",
  "recommendations": ["Maintain premium positioning; sentiment supports the price."],
  "warnings": [],
  "generated_at": "2026-07-16T00:50:45.737244+00:00"
}
```

**Fetch a past result by id**

```bash
curl http://localhost:8000/analyses/<analysis_id>
```

Returns the same `MarketReport`, or `404 {"detail": "analysis not found"}` if the id is
unknown to the (in-memory, per-process) store.

<a id="graceful-degradation-without-an-api-key"></a>
**Graceful degradation without a working `DEEPSEEK_API_KEY`.** The two LLM-calling
nodes (`plan`, `synthesize` — `app/agent/nodes.py`) each catch any failure from the
DeepSeek client (missing/invalid key, timeout, unparseable JSON reply) and fall back to
a safe default: `plan` reuses the raw product/marketplace input as-is; `synthesize`
emits a generic "LLM synthesis unavailable" summary and a "review the data manually"
recommendation. Either way the failure is recorded and surfaces as a human-readable
string in the report's `warnings` array — `POST /analyze` still returns `200` with a
fully valid, schema-conformant `MarketReport`, just a partial one. The same posture
applies to the scraper, sentiment, and trend tools independently (each has its own
fallback — see [ADR 0001](docs/decisions/0001-langgraph-over-native-and-react.md) and
[ADR 0004](docs/decisions/0004-scrape-with-mock-fallback.md)).

## 5. Running tests

```bash
pytest -v
# or, from this repo's venv on Windows:
.venv/Scripts/python.exe -m pytest -v
```

Tests are lean and essential per the project's guiding principles: tool behavior +
mock fallback for each of the four tools, agent orchestration end-to-end with a
**mocked LLM** (`app.agent.nodes.complete_json` is monkeypatched — no test ever hits
the network), error/degradation paths, and output-schema validation for `MarketReport`.
See `tests/`.

## 6. Sample report

A committed, reproducible example (no live LLM or network needed to regenerate it):
[`sample_reports/iphone-15.json`](sample_reports/iphone-15.json), produced by
[`sample_reports/generate_sample.py`](sample_reports/generate_sample.py), which
monkeypatches `complete_json` with a fixed fake response and runs the real graph
end-to-end:

```bash
python sample_reports/generate_sample.py
```

## 7. Deployment recommendations

The project ships two deployment paths built from the same Dockerfile and the same two
services (`api`, `ui`); which one to use depends on what you need:

| Need | Recommendation |
|---|---|
| A public, shareable link, zero server maintenance | **Render**, via the included [`render.yaml`](render.yaml) blueprint — push the repo, connect it in Render's dashboard ("New +" → "Blueprint"), set `DEEPSEEK_API_KEY` once (it's `sync: false`, so it's never read from the repo), and both services deploy. The UI's `API_URL` is wired automatically via Render's `fromService: { property: host }`, so there's no URL to copy by hand. |
| Same idea, different free-tier provider | **Railway** — create two services from this repo's `Dockerfile` (different start commands: `uvicorn app.api.main:app --host 0.0.0.0 --port $PORT` and `streamlit run app/ui/streamlit_app.py --server.address 0.0.0.0 --server.port $PORT`), set `DEEPSEEK_API_KEY` on the API service and `API_URL` on the UI service pointing at the API's Railway URL. |
| Guaranteed-to-work local demo, no network trust required | `docker compose up` — see [§2](#2-quickstart-docker). This always works, independent of whether any cloud deployment is awake or reachable. |
| Full control over the host, a long-lived deployment, custom domain/TLS | A VPS running `docker compose up` directly (e.g. a small droplet/instance) — appropriate once you need to manage uptime, scaling, or a domain yourself; disproportionate for a short-lived demo, which is why it isn't the default recommendation here. |

Notes:
- `ENABLE_LIVE_SCRAPE` defaults to `false` everywhere (local `.env.example`,
  `docker-compose.yml`, `render.yaml`) — the deployed demo is deterministic and
  reproducible by default; live scraping against DummyJSON is an explicit opt-in.
- The only secret is `DEEPSEEK_API_KEY`. It is never committed or baked into an image —
  locally it comes from `.env` (gitignored), on Render/Railway it's entered once in the
  platform's dashboard/env-var UI.
- Full rationale and alternatives considered (Hugging Face Spaces, a bare VPS): [ADR
  0005](docs/decisions/0005-deploy-render-railway.md).

## 8. Design choices

| Decision | ADR |
|---|---|
| Structured graph + LLM planner, over ReAct and Supervisor/worker | [0001](docs/decisions/0001-langgraph-over-native-and-react.md) |
| DeepSeek via an OpenAI-compatible client (`langchain_openai.ChatOpenAI`) | [0002](docs/decisions/0002-deepseek-llm.md) |
| Streamlit UI as a pure API client (no React/Jinja) | [0003](docs/decisions/0003-streamlit-ui.md) |
| Live scrape (DummyJSON) with deterministic mock fallback | [0004](docs/decisions/0004-scrape-with-mock-fallback.md) |
| Render/Railway for cloud deploy, docker-compose for local | [0005](docs/decisions/0005-deploy-render-railway.md) |

## 9. Theory answers (brief steps 4–7)

Programming scope for this project stops at architecture/tools/tests (brief steps
1–3); steps 4–7 are documented as production designs rather than built, per
`CLAUDE.md`'s scope reminder. Summaries, each linking its full document:

- **[Data storage](docs/theory/04-data-storage.md)** — what the running app models with
  a single in-memory dict (`app/api/store.py`) would become, in production, four
  distinct stores: PostgreSQL for analysis results/history/agent configs (relational
  integrity, `JSONB` for the evolving report body), Redis for the TTL-cached
  scrape/sentiment/trend inputs (native `EXPIRE`, sub-millisecond reads), plus a design
  for versioned prompt configs that supports the A/B testing in step 7.
- **[Monitoring & observability](docs/theory/05-monitoring-observability.md)** — the
  pipeline has two independent failure modes (a tool, or an LLM call), so it needs both
  tracing (LangSmith, since the agent is already LangGraph, or OpenTelemetry spans per
  node) and metrics (per-node latency, per-tool success rate off the existing
  `ToolResult.ok`, LLM token/cost per call, and the cache hit rate already emitted as
  the `X-Cache` response header).
- **[Scaling & optimization](docs/theory/06-scaling-optimization.md)** — the two
  concrete bottlenecks in the current build (synchronous `POST /analyze`, single-process
  in-memory store) are named precisely, then addressed with an async task queue
  (`202 Accepted` + polling/SSE, worker pool calling the same `run_analysis()`
  unchanged), horizontal API replicas behind a load balancer, and LLM cost controls.
- **[Continuous improvement](docs/theory/07-continuous-improvement.md)** — because
  `synthesize_node` can return schema-valid but low-quality output that nothing today
  would catch, this design adds an LLM-as-judge scoring pipeline (grounded, actionable,
  consistent, non-generic), prompt A/B testing against `app/agent/prompts.py`, and a
  user-feedback loop to drive both.

## 10. Project structure

```
app/
├── agent/
│   ├── graph.py            LangGraph StateGraph build + run_analysis(product, marketplace)
│   ├── nodes.py             plan/scrape/sentiment/trend/synthesize/report node functions
│   ├── prompts.py           PLAN_SYSTEM / SYNTHESIS_SYSTEM prompt text
│   └── state.py              AgentState TypedDict (operator.add-reduced `errors`)
├── api/
│   ├── main.py               FastAPI app factory
│   ├── routes.py              /health, /analyze, /analyses/{id}
│   ├── schemas.py              AnalyzeRequest / AnalyzeResponse
│   └── store.py                 in-memory result store + TTL cache
├── core/
│   ├── config.py              Settings (env-driven, pydantic-settings)
│   ├── errors.py                shared exception types
│   ├── logging.py                 structured logger helper
│   └── report.py                   MarketReport and nested Pydantic models
├── llm/
│   └── deepseek.py            get_llm() / complete_json() — DeepSeek client
├── tools/
│   ├── base.py                BaseTool / ToolResult
│   ├── mockdata.py              deterministic mock price/competitor/review/series generators
│   ├── web_scraper.py            price + competitors (live DummyJSON or mock)
│   ├── sentiment_analyzer.py       mock review corpus → sentiment breakdown
│   ├── trend_analyzer.py            simulated price/popularity time series
│   └── report_generator.py           compiles everything into a MarketReport
└── ui/
    └── streamlit_app.py       Streamlit dashboard, HTTP client of the API only

docs/
├── architecture.md          living architecture description + request lifecycle
├── decisions/                ADRs 0001–0005
└── theory/                    brief steps 4–7 (storage, monitoring, scaling, improvement)

sample_reports/
├── generate_sample.py       reproducible sample-report generator (mocked LLM)
└── iphone-15.json            committed example MarketReport

tests/                       tool/agent/API/report-model tests (mocked LLM, no network)
docker-compose.yml           local api + ui services
render.yaml                  Render blueprint (cloud api + ui services)
Dockerfile                   shared image for both services
.env.example                 documented environment variables
pyproject.toml               dependencies, dev extras, pytest config
```

## License

Provided as-is for evaluation purposes.
