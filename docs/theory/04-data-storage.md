# 04 — Data storage design

> Theory answer (brief step 4). Not implemented at runtime: the running app uses only
> the in-memory cache/history in `app/api/store.py` (`_BY_ID`, `_CACHE`), which is
> explicitly documented there as per-process, not evicted, and not safe across
> multiple workers. This document is the production design that in-memory store stands
> in for.

## What needs to be stored

Four distinct kinds of data, with different access patterns, lifetimes, and
consistency requirements:

1. **Analysis results** — the full `MarketReport` produced by a run of the graph
   (`app/core/report.py`): price, competitors, sentiment, trend, summary,
   recommendations, warnings. Written once per analysis, read many times (by
   `GET /analyses/{id}`, and potentially by an evaluation/audit job later). Needs to
   survive process restarts and be queryable by id and by (product, marketplace).
2. **Request history** — a log of every analysis request that came in: who/what asked,
   which product/marketplace, when, which analysis id it resolved to (cache hit or
   fresh run), and how long each pipeline stage took. Append-only, used for auditing,
   debugging, and as the raw material for the metrics in
   [`05-monitoring-observability.md`](05-monitoring-observability.md).
3. **Cached collected data** — the *inputs* to synthesis (scrape/sentiment/trend
   payloads) keyed by `(product, marketplace)`, so a repeated request for the same
   product within a TTL window skips re-scraping and re-running the analysis nodes.
   This is exactly what `app/api/store.py::get_cached` prototypes today, just
   in-process and non-persistent.
4. **Agent configs** — versioned prompts and tunables for the `plan` and `synthesize`
   nodes (`app/agent/prompts.py` today is a static Python module) so that prompt
   changes can be rolled out, compared, and rolled back without a code deploy — the
   basis for the A/B testing described in
   [`07-continuous-improvement.md`](07-continuous-improvement.md).

## Recommended stores

| Store | Used for | Why this store |
|---|---|---|
| **PostgreSQL** | analysis results, request history, agent configs | Relational integrity for history/config rows, transactional writes, and rich querying (filter history by product/date/error-rate); `JSONB` columns absorb the report body's evolving shape without a migration for every field the report gains. |
| **Redis** | cached collected data (TTL cache) | Sub-millisecond reads keyed by `product+marketplace`, native `EXPIRE`/TTL semantics — this *is* what `cache_ttl` in `app/core/config.py` already models, just needing a real backing store instead of a Python dict. Also a natural home for rate-limiting counters and short-lived locks (e.g. "an analysis for this key is already in flight, don't start a second one"). |
| **Object storage (S3 / R2 / GCS)** | large raw scrape payloads, LLM raw responses for audit | Raw HTML/JSON dumps from a live scrape, or the full raw LLM completion before JSON-extraction, are useful for debugging and reprocessing but too large/unstructured to want in Postgres rows; store the blob in object storage and keep only a reference (URL/key) in Postgres. |
| **Queue** (see [`06-scaling-optimization.md`](06-scaling-optimization.md)) | decoupling request intake from graph execution | Not a data store per se, but the fourth leg of the storage design: once analysis becomes async, the queue holds pending-analysis messages between "request accepted" and "graph finished," and the result lands in Postgres/Redis as above. |

### Why not just one store for everything

A single Postgres instance *could* hold the TTL cache too (a row with an
`expires_at` column and a periodic cleanup job), and for a project at this scale that
would work. Redis is called out separately because TTL cache reads are the hottest,
highest-frequency path (every incoming request checks the cache before deciding whether
to run the graph at all — see `app/api/routes.py::analyze`), and an in-memory store
with native expiry is a better fit for that specific access pattern than a
row-per-lookup query against a relational table, especially once request volume grows
enough to matter (see step 6). Postgres remains the source of truth for anything that
must survive beyond a cache TTL.

## Schema sketch

```sql
-- Full analysis results. `report` mirrors app/core/report.py::MarketReport
-- as JSONB so new report fields don't require a migration.
CREATE TABLE analyses (
    id             UUID PRIMARY KEY,
    product         TEXT NOT NULL,
    marketplace     TEXT,
    report          JSONB NOT NULL,       -- full MarketReport.model_dump()
    had_warnings    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_analyses_product_marketplace ON analyses (product, marketplace, created_at DESC);

-- One row per pipeline run, for history/audit/metrics. A run may resolve to
-- a fresh analysis (fills analysis_id after the graph finishes) or a cache hit
-- (analysis_id points at a pre-existing row, cache_hit = true).
CREATE TABLE analysis_events (
    id              UUID PRIMARY KEY,
    analysis_id     UUID REFERENCES analyses(id),
    product         TEXT NOT NULL,
    marketplace     TEXT,
    cache_hit       BOOLEAN NOT NULL,
    node_durations_ms JSONB,              -- {"plan": 812, "scrape": 340, ...}
    errors          JSONB,                -- state.errors from the graph, if any
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);
CREATE INDEX idx_events_requested_at ON analysis_events (requested_at DESC);

-- Cached collected data (Postgres fallback / cold-start view of what Redis holds
-- hot). Mirrors app/api/store.py's (product, marketplace) -> payload mapping.
CREATE TABLE cached_data (
    key             TEXT PRIMARY KEY,     -- e.g. "product|marketplace" hash
    payload         JSONB NOT NULL,       -- scrape/sentiment/trend intermediate data
    expires_at      TIMESTAMPTZ NOT NULL
);

-- Versioned agent configuration: prompt text + params per named config, so
-- plan/synthesize prompts can change without a code deploy and be A/B compared.
CREATE TABLE agent_configs (
    id              UUID PRIMARY KEY,
    name            TEXT NOT NULL,        -- e.g. "synthesis_system_prompt"
    prompt_version  INT NOT NULL,
    params          JSONB NOT NULL,       -- {"temperature": 0.2, "model": "deepseek-chat", ...}
    prompt_text     TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name, prompt_version)
);
```

## Access patterns this supports

- `POST /analyze`: check Redis for `(product, marketplace)` → hit: read the analysis
  row from Postgres by the cached id; miss: enqueue/run the graph, write to
  `analyses` + `cached_data`/Redis + one `analysis_events` row.
- `GET /analyses/{id}`: single indexed Postgres lookup by primary key.
- History/audit UI or query: `SELECT * FROM analysis_events WHERE product = ... ORDER
  BY requested_at DESC` — no need to touch the (potentially large) `analyses.report`
  JSONB unless drilling into a specific run.
- Prompt rollout: flip `is_active` on a new `agent_configs` row, read the active
  prompt/params for a given `name` at the start of `plan_node`/`synthesize_node`
  instead of importing the static constants from `app/agent/prompts.py`.
