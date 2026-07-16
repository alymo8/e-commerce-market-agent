# 06 — Scaling and optimization

> Theory answer (brief step 6). The running app is deliberately synchronous
> (`POST /analyze` blocks until the graph finishes) and single-process
> (`app/api/store.py` is an in-memory dict) — appropriate for a demo, not for the load
> discussed below. This document is the design for handling 100+ concurrent analyses.

## The current bottlenecks, precisely

Two things in the current implementation would not survive scale, and it's worth being
specific about which:

1. **Synchronous request handling.** `POST /analyze` (`app/api/routes.py::analyze`)
   calls `run_analysis()` inline and blocks the HTTP worker until the whole graph
   finishes (two LLM round-trips + up to three tool calls). Under concurrent load this
   ties up FastAPI/uvicorn workers for the full pipeline duration each.
2. **In-memory, per-process store.** `app/api/store.py`'s `_BY_ID`/`_CACHE` dicts are
   explicitly documented in the file as "not evicted, not synchronized, and per-process
   only (not safe across multiple uvicorn workers)." Running more than one API worker
   or replica today would give each replica its own inconsistent cache/history — a
   cache hit on one replica would be a miss on another for the same request.

Neither is a flaw in the demo (the brief scopes runtime persistence to in-memory only,
and a synchronous API is the simplest correct choice for a single-shot CLI/UI demo) —
they are exactly the two things this design addresses for 100+ concurrent analyses.

## Async workers + a task queue

Move analysis execution off the HTTP request path:

- `POST /analyze` becomes: enqueue a job (`{product, marketplace, request_id}`), return
  `202 Accepted` with a job id immediately; the UI (or a client) polls
  `GET /analyses/{id}` (already the shape of the existing endpoint) or subscribes to a
  websocket/SSE stream for status.
- A pool of **worker processes** (Celery or RQ against Redis, or a managed queue —
  SQS+Lambda, Google Cloud Tasks, or a managed LangGraph/LangServe deployment) pull jobs
  and call `run_analysis()` — the graph itself (`app/agent/graph.py`) does not need to
  change; it's already a plain function from `(product, marketplace)` to a report.
  Workers scale horizontally independently of the API tier.
- **Horizontal API replicas behind a load balancer** handle the (now cheap, since
  they're not blocking) accept/enqueue/status-check requests; this is where "100+
  concurrent analyses" turns into "N API replicas fielding bursty short requests,
  M workers churning through a queue at whatever throughput DeepSeek/tools allow."
- This is exactly where the in-memory store must be replaced: `analyses`/history in
  Postgres, the TTL cache in Redis (`04-data-storage.md`) — both because a single
  in-memory dict can't be shared across API replicas *or* workers, and because the
  queue's pending/in-flight job state itself needs a shared backend (Redis, or
  whatever the managed queue provides) rather than process memory.

## LLM cost optimization

The two LLM calls per analysis (`plan`, `synthesize` — ADR 0001/0002) are the primary
per-request cost; at 100+ concurrent analyses this is the line item to control:

- **Cache the plan/synthesis outputs**, not just the final report. If the TTL cache
  (`04-data-storage.md`) already avoids re-running the *entire* graph for a repeated
  `(product, marketplace)` within its TTL, most of this is already covered — but a
  request for a *similar* product not sharing a literal cache key (e.g. "iPhone 15" vs
  "iphone 15 128gb") could still reuse `plan_node`'s normalization if plans are cached
  by a looser key (e.g. after normalization) independently of the full report cache.
- **Cheaper-model routing.** `plan_node`'s task (normalize a product string, guess a
  marketplace) is far simpler than `synthesize_node`'s (write grounded, non-generic
  recommendations from real data) — route `plan` to a smaller/cheaper DeepSeek variant
  (or a smaller open model) while keeping `synthesize` on the stronger model, rather
  than paying the same per-token rate for both. `app/llm/deepseek.py::get_llm()` already
  reads `deepseek_model` from settings; this becomes two settings (one per node) instead
  of one.
- **Prompt compression.** `synthesize_node` currently interpolates the full raw
  scrape/sentiment/trend dicts into the user message (`app/agent/nodes.py`, the
  f-string in `synthesize_node`) — at scale, trimming this to only the fields the
  prompt actually needs (e.g. summarized sentiment counts and top themes, not the full
  `sample_reviews` list) directly reduces input tokens billed on every single request.
- **Batching**, where the provider supports it: if many analyses for the same rough
  time window/marketplace queue up, batch multiple `synthesize` calls into fewer API
  round-trips where the provider's batch API allows it, trading a little latency for
  meaningfully lower cost at high volume.

## Intelligent caching

Beyond the simple TTL-by-key cache already prototyped:

- **Product-key cache** (what exists today, generalized): key by a normalized
  `(product, marketplace)` — normalization matters more at scale, since "iPhone 15",
  "iphone15", and "Apple iPhone 15" should ideally share a cache entry once `plan_node`
  has normalized them, rather than tripling the cache-miss (and LLM-cost) rate for
  what's functionally the same request.
- **Semantic cache** as a second tier: for near-duplicate but not identical product
  queries, an embedding-similarity lookup (e.g. Redis with a vector index, or a
  dedicated vector store) can serve a "close enough" cached report (or at minimum reuse
  its scrape/sentiment/trend data while still re-running `synthesize` for a fresh
  summary) instead of a full cache miss.
- **TTL by volatility, not a single global TTL.** Price/competitor data
  (`scrape`) is far more volatile than sentiment themes or trend direction for the same
  product over a short window — a production cache would give `scrape` a shorter TTL
  than `sentiment`/`trend`, rather than the single `cache_ttl` (`app/core/config.py`,
  default 3600s) applied uniformly to the whole report today.

## Parallelization

- **Already present, within one analysis:** the graph fans out `sentiment` and `trend`
  from `scrape` and fans them back in at `synthesize` (`app/agent/graph.py`) — this is
  real LangGraph parallel execution, not simulated, and directly cuts single-request
  latency versus running the two analysis tools sequentially.
- **Across products, via the queue:** the fan-out/fan-in inside one graph run is
  orthogonal to running *many* graph invocations concurrently. Once analysis moves
  behind a task queue (above), 100+ concurrent analyses is simply N workers each
  running one graph invocation at a time (or a handful, if a worker is async/I/O-bound
  enough to hold several in flight) — the graph's internal parallelism reduces the
  *latency of each one*, the worker pool's size determines the *throughput across all
  of them*. Both matter and are independent levers: adding workers doesn't help a
  single slow analysis; keeping the sentiment/trend fan-out doesn't help overall
  throughput once workers are the bottleneck.
