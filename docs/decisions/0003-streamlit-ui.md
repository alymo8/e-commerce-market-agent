# 0003 — Streamlit UI as a pure API client

## Status

Accepted (2026-07-15).

## Context

The brief's additions ask for a UI to visualize the agent's work and its reports. The
real product being evaluated is the agent/API; the UI's job is to make the pipeline and
its output legible to a human in as little build effort as possible, without becoming
a second thing to design, test, and deploy.

## Decision

Build the UI as a single Streamlit script, `app/ui/streamlit_app.py`, that:

- Takes a product name + optional marketplace via a form.
- Calls `POST {API_URL}/analyze` over plain HTTP (`httpx`) and renders the JSON
  response — executive summary, metrics (price/sentiment/trend), recommendations,
  competitor-price bar chart, sentiment bar chart, price-history and popularity line
  charts (via `pandas` + Streamlit's built-in chart primitives) — plus a raw-JSON
  expander for inspection.
- Surfaces `report["warnings"]` as a Streamlit warning banner when the report is
  partial (a tool degraded).
- Reads `API_URL` from the environment (default `http://localhost:8000`), with a small
  normalization step for Render's service-discovery value (see Consequences).

Critically, `app/ui/` contains **no import of `app.agent` or `app.tools`**. The UI only
knows the API's JSON contract (`AnalyzeResponse` / `MarketReport`).

## Alternatives considered

**React + FastAPI single-page app.** Would give full control over interaction design
and a "real" production-grade UI. Rejected: it requires a JS build pipeline, a second
language/toolchain, and a second container image, all to visualize essentially one
form and a handful of charts — disproportionate effort for a test that rewards clarity
over polish, and it wouldn't better demonstrate the actual point of the exercise (the
agent orchestration).

**Server-rendered HTML (Jinja2 templates via FastAPI).** Would keep everything in one
Python process/container and avoid Streamlit's opinionated widget model. Rejected
because it still means hand-rolling charts (client-side JS or server-side image
generation) and form handling that Streamlit provides for free; for the amount of UI
surface needed here, Streamlit gets to a working, chart-rendering demo in far less code
with no templating layer to maintain.

## Consequences

- **Fastest path to a demo dashboard**, single-purpose script, no build step, no
  additional container tooling — `streamlit run app/ui/streamlit_app.py` is the whole
  deployment unit (its own Docker service in `docker-compose.yml` and `render.yaml`).
- **UI is strictly a client, never a second entry point into the agent.** This keeps
  the three-layer separation (tools / agent / interface) honest: if the UI ever needs
  something the API doesn't expose, the fix is to extend the API (`app/api/routes.py`,
  `app/api/schemas.py`), not to reach into `app/agent` from Streamlit. It also means the
  UI can be pointed at any deployment of the API (local, Render, Railway) purely via the
  `API_URL` env var, with no code change.
- **Render's `fromService ... property: host` injects a bare hostname** (no
  `https://` scheme) into `API_URL` for the UI service. `streamlit_app.py` normalizes
  this by prepending `https://` when the value doesn't already start with `http://` or
  `https://` (see the guard at the top of the file) — otherwise `httpx.post(f"{API_URL}/analyze")`
  would build an invalid URL like `market-agent-api.onrender.com/analyze` and fail.
- **No client-side state beyond the current form submission.** History/caching is the
  API's responsibility (`app/api/store.py`); the UI doesn't need its own persistence.
