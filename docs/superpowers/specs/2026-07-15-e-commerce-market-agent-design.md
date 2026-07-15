# Design: E-commerce Market Analysis Agent

**Date:** 2026-07-15
**Status:** Approved
**Author:** brainstormed with Claude

## Context

This project is the solution to a technical test ("Test technique - Développeur IA :
Agent d'analyse de marché e-commerce"). The goal is an intelligent agent that
orchestrates several specialized tools to produce strategic market-analysis reports
about e-commerce products.

The test explicitly values **clarity over complexity**, **robustness**, and
**justification of choices** (the README/docs count as much as the code). Programming
is scoped to steps 1–3 (architecture, tools, tests); steps 4–7 are theory answers.

Everything in this repo is written in **English** even though the brief is in French.

### Additions requested beyond the brief
- Use **LangGraph** for the agent design.
- Provide a **UI** to visualize the agent's work and reports.
- Make it **easily deployable**, with deployment recommendations.
- Use **DeepSeek** as the LLM (API key provided via env).
- Build a **robust knowledge layer** in the repo: preferences and design choices
  well documented (ADRs + theory docs + this spec + CLAUDE.md).

## Confirmed decisions

| Decision | Choice | Rationale (short) |
|---|---|---|
| Agent framework | **LangGraph** | Requested; best-in-class for explicit, traceable orchestration. |
| Orchestration pattern | **Structured graph + LLM planner** | Deterministic, debuggable, demonstrates orchestration mastery + parallelization; cheapest LLM usage. Chosen over ReAct and Supervisor patterns (documented in ADR 0001). |
| LLM | **DeepSeek** (OpenAI-compatible client) | Requested; low cost. |
| UI | **Streamlit** | Fastest path to a demo dashboard; single container; Python-native. |
| Data strategy | **Live scrape → deterministic mock fallback** | Real capability without a fragile demo. |
| Deploy target | **Render / Railway** (+ always-working local docker-compose) | Push-to-deploy public URL for evaluators. |
| API style | **Synchronous `POST /analyze`** | Simplest for demo + UI; async job queue is a theory answer (step 6). |
| Tool count | **All four** (scraper, sentiment, trend, report) | Above the minimum three; makes a complete report. |

## Architecture

Three cleanly separated, independently testable layers:

1. **Tools layer** — four specialized tools behind a common `BaseTool` interface with
   uniform error handling, timeouts, and structured results. No LangGraph knowledge
   here; pure and unit-testable.
2. **Agent layer** — a LangGraph `StateGraph` orchestrating the tools over a typed
   `AgentState`.
3. **Interface layer** — a FastAPI REST API (the real product) and a Streamlit UI that
   is *only a client* of that API.

```
Streamlit UI --HTTP--> FastAPI --> LangGraph agent --> Tools --> (live scrape | mock)
                                        |
                                   DeepSeek LLM (plan + synthesis)
```

### Agent graph

```
START -> plan (LLM) -> scrape_products -> [ analyze_sentiment || analyze_trends ] -> synthesize_report (LLM) -> END
```

- Typed `AgentState` carries the request, each tool's output, and a per-node `errors` list.
- **Graceful degradation:** a failing tool records its error in state and the pipeline
  continues -> a *partial* report instead of a crash.
- LLM used only in `plan` (validate/normalize request, choose marketplace) and
  `synthesize_report` (raw data -> insights + business recommendations). The two
  analysis nodes run in **parallel** (fan-out/fan-in) to demonstrate parallelization.

### The four tools

| Tool | Responsibility | Data strategy |
|---|---|---|
| Web Scraper | Product info, price, competitor prices | Live scrape attempt, deterministic mock fallback |
| Sentiment Analyzer | Analyze customer reviews, extract insights | Mock review corpus; LLM extracts themes/sentiment |
| Trend Analyzer | Price history + popularity trend | Simulated time-series |
| Report Generator | Compile everything into a structured report + chart-ready data | Pure compilation |

## API design

- `POST /analyze` — `{ "product": "...", "marketplace": "optional" }` -> full structured report.
- `GET /health` — liveness for deploy platforms.
- `GET /analyses/{id}` + an in-memory **cache/history** — small; demonstrates the
  caching idea (step 6) without over-building. Full storage design remains a step-4
  theory answer.

Report is a validated **Pydantic v2** model: product summary, price/competitor
analysis, sentiment breakdown, trend analysis, business recommendations, plus
chart-ready arrays for the UI.

## UI (Streamlit)

Enter a product -> live per-node status as the pipeline runs -> rendered report with
charts (competitor price bars, sentiment breakdown, price-trend line) and
recommendations. A committed sample report lives in `sample_reports/`.

## Proposed repository structure

```
e-commerce-market-agent/
├── README.md                 # install/use (steps 1-3) + theory summaries (steps 4-7)
├── CLAUDE.md                 # guidance for future Claude sessions
├── docker-compose.yml
├── render.yaml               # Render blueprint
├── .env.example
├── pyproject.toml
├── app/
│   ├── api/                  # FastAPI: main, routes, schemas
│   ├── agent/                # LangGraph: graph, state, nodes, prompts
│   ├── tools/                # base, web_scraper, sentiment_analyzer, trend_analyzer, report_generator
│   ├── llm/                  # DeepSeek client config
│   ├── core/                 # config, logging/tracing, errors
│   └── ui/                   # streamlit_app.py
├── tests/
├── docs/
│   ├── architecture.md
│   ├── decisions/            # ADRs 0001-0005
│   └── theory/               # 04-07 answers
└── sample_reports/           # example generated report (deliverable)
```

## Testing (pytest, focused)

- Tool behavior including the **mock-fallback path**.
- Agent orchestration end-to-end with a **mocked LLM** (fast, free).
- Error-handling paths (a tool failing -> partial report).
- Output-schema validation (Pydantic).

Deliberately lean — the brief warns against over-testing.

## Deployment

- **Local (always works):** `docker-compose up` -> two services (api + ui) + `.env`
  for the DeepSeek key. This is what the evaluator runs.
- **Cloud:** `render.yaml` blueprint (Render) + Railway instructions in the README ->
  shareable public URL. Full recommendation write-up in the README.

## Stack

Python 3.13 · LangGraph + langchain · DeepSeek (OpenAI-compatible) · FastAPI +
Pydantic v2 · Streamlit · pytest · Docker / docker-compose.

## Knowledge layer

Every decision in the table above becomes an ADR in `docs/decisions/` with its full
trade-offs. Theory answers (steps 4–7) live in `docs/theory/` and are summarized in
the README. This spec and `CLAUDE.md` anchor the whole thing. Key preferences are also
stored in Claude's persistent memory.

## Out of scope (deliberately)

- Production storage implementation (step 4 is theory; runtime uses in-memory cache/history).
- Async job queue / autoscaling (step 6 theory).
- LLM-as-judge / A/B harness implementation (step 7 theory).
- Authentication.
