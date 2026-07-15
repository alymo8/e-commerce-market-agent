# CLAUDE.md

Guidance for Claude sessions working in this repository.

## What this is

An **e-commerce market-analysis agent**: an intelligent agent that orchestrates
several specialized tools to produce strategic market-analysis reports about products.
It is the solution to a technical test (brief: `Test technique - DevIA .pdf` on the
user's Desktop, in French — but **all code, docs, comments, and UI in this repo are in
English**).

The full design lives in
[`docs/superpowers/specs/2026-07-15-e-commerce-market-agent-design.md`](docs/superpowers/specs/2026-07-15-e-commerce-market-agent-design.md).
Read it before making architectural changes.

## Guiding principles (from the brief — honor these)

- **Clarity before complexity.** A simple, well-explained, robust solution beats a
  complex unfinished one. Do not add speculative features.
- **Orchestration is the point.** The value is in how tools collaborate via the agent,
  not the perfection of any single tool. Mocked data is acceptable and expected.
- **Justify every choice.** Docs count as much as code. Any real design decision gets
  an ADR in `docs/decisions/`.

## Architecture (three separated layers)

1. **Tools** (`app/tools/`) — four tools behind a common `BaseTool` interface: uniform
   error handling, timeouts, structured results. No LangGraph knowledge here; keep them
   pure and unit-testable.
2. **Agent** (`app/agent/`) — a LangGraph `StateGraph` over a typed `AgentState`.
   Graph: `plan (LLM) -> scrape_products -> [analyze_sentiment || analyze_trends] ->
   synthesize_report (LLM) -> END`. Tool failures are recorded in `state.errors` and
   the pipeline continues (graceful degradation -> partial report).
3. **Interface** — FastAPI REST API in `app/api/` (the real product) and a Streamlit UI
   in `app/ui/` that is **only a client of the API** (it must not import the agent
   directly).

The LLM (DeepSeek) is called **only** in the `plan` and `synthesize_report` nodes.
Everything else is deterministic.

## Key decisions (see `docs/decisions/` for full rationale)

- **LangGraph**, structured graph + LLM planner pattern — chosen over ReAct and
  Supervisor for determinism, debuggability, and demonstrable parallelization (ADR 0001).
- **DeepSeek** via an OpenAI-compatible client (ADR 0002).
- **Streamlit** UI (ADR 0003).
- **Live scrape with deterministic mock fallback** (ADR 0004) — the demo must always
  work even with no network.
- **Render / Railway** for cloud deploy; local `docker-compose up` always works
  (ADR 0005).

## Conventions

- Python **3.13**. Pydantic **v2** for all schemas. Type hints everywhere.
- The API report is a validated Pydantic model — changes to report shape update both
  the model and the Streamlit renderer.
- Tests are **lean and essential** (the brief warns against over-testing): tool
  behavior + mock fallback, agent orchestration end-to-end with a **mocked LLM**,
  error paths, output-schema validation.
- Secrets (DeepSeek key) come from env / `.env` only — never commit them. See
  `.env.example`.

## Commands

> Note: the project scaffold may not be built yet — check what exists before assuming.

- Run everything locally: `docker-compose up`
- API: FastAPI (see `app/api/`), health at `GET /health`, analysis at `POST /analyze`.
- UI: Streamlit (see `app/ui/`), talks to the API over HTTP.
- Tests: `pytest`

## Knowledge layer (keep it current)

- `docs/architecture.md` — living architecture description.
- `docs/decisions/` — one ADR per real decision, with trade-offs.
- `docs/theory/` — answers to brief steps 4–7 (data storage, monitoring, scaling,
  continuous improvement); summarized in the README.
- When you make a non-trivial choice, **write or update an ADR** in the same change.

## Scope reminder

Programming is scoped to brief steps 1–3 (architecture, tools, tests). Steps 4–7 are
**theory answers only** — do not build storage backends, job queues, or A/B harnesses;
document them in `docs/theory/` instead. Runtime persistence is an in-memory
cache/history only.
