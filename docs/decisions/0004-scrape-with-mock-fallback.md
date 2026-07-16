# 0004 — Live scrape attempt with deterministic mock fallback

## Status

Accepted (2026-07-15).

## Context

The brief explicitly says mocked data is acceptable and expected — the value under
test is orchestration, not scraper robustness. At the same time, "an agent that
orchestrates a web scraper" is more convincing, and more honest about what was actually
built, if there is a *genuine* fetch-and-parse path somewhere, not just a function that
returns canned numbers. The risk of relying on any live network call in a demo/test
environment is that it makes the outcome non-reproducible: the evaluator's network
might be restricted, the target site might rate-limit or change its markup, or simply
be down, and a crashed pipeline is a worse demo than a mock one.

## Decision

`WebScraperTool` (`app/tools/web_scraper.py`) supports two data strategies, gated by a
single settings flag, `ENABLE_LIVE_SCRAPE` (`Settings.enable_live_scrape`, **default
`false`**):

- **Live path** (`ENABLE_LIVE_SCRAPE=true`): `GET https://dummyjson.com/products/search?q=<product>&limit=5`.
  DummyJSON is a real, key-less public product API — this is a genuine HTTP
  fetch-and-JSON-parse, not a simulation. `_parse()` takes the top hit as the product's
  own price and the next three as competitors (`name` = brand or truncated title,
  `price` = float), and raises `ValueError` if the search returns no products.
- **Mock path** (default, or if the live path raises for *any* reason — network error,
  timeout, empty result, parse error): `_mock()` calls `mock_price()` /
  `mock_competitors()` from `app/tools/mockdata.py`, which derive a price and a fixed
  set of competitor names/prices deterministically from the product string (e.g. via a
  stable hash/seed), so the same product name always produces the same numbers.
- The result always carries `"source": "live"` or `"source": "mock"` so the caller (and
  the report, and the UI) can see which path produced the data — the report is never
  silently ambiguous about this. `_execute()` catches and logs any live-path exception
  and falls through to `_mock()`, so `WebScraperTool.run()` (via `BaseTool.run`) only
  ever reports a hard failure if the mock path itself raises.

## Alternatives considered

**Pure mock, no live path at all.** Simpler and fully reproducible, and fully within
what the brief permits. Rejected as the sole strategy because it would make the "web
scraper" tool a misnomer — nothing in the codebase would ever actually reach the
internet, which undersells the orchestration story ("this agent really can pull live
product data when allowed to") for very little extra cost (one `httpx.get` and a small
parser).

**Real scraping only, no fallback.** Would be the most "honest" demonstration of a
working scraper, but ties the demo's success to an external, uncontrolled dependency
(DummyJSON's uptime, rate limits, or search relevance for arbitrary product strings).
Rejected because a flaky demo is a worse outcome than a mock one — the brief rewards
robustness, and a `docker-compose up` an evaluator runs offline or on a locked-down
network must still produce a full report.

## Consequences

- **`ENABLE_LIVE_SCRAPE` defaults to `false`** in both `app/core/config.py` and the
  shipped deploy configs (`docker-compose.yml`, `render.yaml`) — the default posture is
  the deterministic, reproducible one; live scraping is an explicit opt-in, e.g. for a
  reviewer who wants to see the real path work.
- **The mock corpus must stay deterministic and seeded from the product string**, not
  random per call — this is what makes `sample_reports/` (the committed example report)
  and any test against mock output reproducible across runs and machines.
- **Failure isolation stays inside the tool.** Because `_execute()` swallows live-path
  exceptions and falls back internally, a live-scrape failure never surfaces as a tool
  failure to the graph (`scrape_node` still gets `result.ok == True`) — only a failure
  of the mock path itself would. This is a deliberate two-tier degradation: live → mock
  → (if even mock somehow raises) → the graph-level fallback already described in ADR
  0001 (a zero-valued price payload plus an entry in `state.errors`).
- **Cost of the choice:** DummyJSON's catalog doesn't necessarily contain the product an
  evaluator types in, and search relevance is whatever DummyJSON's own search does —
  live mode is a demonstration of *mechanism* (can this codebase really fetch and parse
  an external API), not a claim that it produces retail-accurate prices for arbitrary
  products.
