# 0005 — Render/Railway for cloud deploy, docker-compose for local

## Status

Accepted (2026-07-15).

## Context

The brief's additions ask the project to be "easily deployable, with deployment
recommendations," and an evaluator needs two things that pull in different directions:
a public link they can click without setting anything up, and a local path that is
guaranteed to work even if the public link is asleep, rate-limited, or the evaluator has
no network trust for a random URL. The project has exactly two runtime services — the
FastAPI backend and the Streamlit UI — plus one secret (the DeepSeek API key) that must
never be committed.

## Decision

Two deployment paths, both driven by the same two Dockerized services:

1. **Local, always works:** `docker-compose.yml` defines `api` (uvicorn on 8000) and
   `ui` (Streamlit on 8501, `depends_on: api`, `API_URL=http://api:8000` via Docker's
   internal DNS). Secrets come from a local `.env` (`DEEPSEEK_API_KEY`, etc.), never
   committed — see `.env.example`. This is what an evaluator runs if they clone the
   repo.
2. **Cloud, shareable link:** `render.yaml` is a Render *blueprint* declaring the same
   two services as `type: web`, `runtime: docker`, each with its own `dockerCommand`.
   `DEEPSEEK_API_KEY` is `sync: false` (must be entered once in Render's dashboard, never
   stored in the repo); `ENABLE_LIVE_SCRAPE` defaults to `"false"` in the blueprint,
   matching the local default (ADR 0004). The UI service's `API_URL` is wired via
   Render's `fromService: { type: web, name: market-agent-api, property: host }`, so
   Render injects the API's own hostname into the UI's environment at deploy time —
   no manually-copied URL to keep in sync. Railway is documented as an equivalent
   push-to-deploy alternative (two services from the same Dockerfile, same env vars)
   for evaluators who prefer it or if Render's free tier is unavailable.

## Alternatives considered

**Hugging Face Spaces.** Excellent free hosting for a single Streamlit or Gradio app,
but this project is *two* cooperating services (API + UI) rather than one
self-contained script, and Spaces' model fits a single-process app much better than a
two-service deployment with inter-service env-var wiring. Would have forced an awkward
single-process merge of API and UI, undermining the "UI is only an API client" boundary
(ADR 0003). Not chosen.

**A single VPS (e.g. a $5 droplet) running docker-compose directly.** Gives full
control and is close to the local setup, but requires the evaluator (or the author) to
provision and maintain a server, manage its own TLS/domain, and manually restart on
crash — none of which a push-to-deploy platform's free tier requires. Rejected as
disproportionate operational overhead for a technical-test deliverable whose lifetime
is short.

## Consequences

- **Two web services, not one.** Both `docker-compose.yml` and `render.yaml` model the
  API and UI as independently deployable containers built from the same Dockerfile
  (different `dockerCommand`/`command` per service) — this mirrors the "UI is only an
  HTTP client of the API" boundary all the way into deployment, rather than special-
  casing it away for convenience.
- **The DeepSeek key is always environment-injected, never baked into an image or
  committed.** Locally via `.env` + `docker-compose`'s `environment:` interpolation
  (`${DEEPSEEK_API_KEY}`); on Render via a `sync: false` env var entered in the
  dashboard.
- **`render.yaml`'s `fromService ... property: host` returns a bare hostname, not a
  URL** — this is a Render-specific quirk that the UI must account for (see ADR 0003):
  `app/ui/streamlit_app.py` prepends `https://` when `API_URL` doesn't already start
  with a scheme. Anyone adapting this blueprint to Railway or another platform needs to
  check whether the equivalent service-reference mechanism has the same behavior.
- **`ENABLE_LIVE_SCRAPE` stays `false` by default in the cloud blueprint too**,
  consistent with ADR 0004 — the hosted demo is reproducible by default; live scraping
  is something an evaluator would opt into explicitly via Render's dashboard, not
  something that could make the hosted demo flaky.
- **Push-to-deploy is the whole cloud release process.** A `git push` to the connected
  branch redeploys both services on Render; there is no separate CI/CD pipeline to
  maintain for a project of this scope.
