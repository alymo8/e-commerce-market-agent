# 07 — Continuous improvement

> Theory answer (brief step 7). No A/B harness, judge pipeline, or feedback storage is
> implemented at runtime — this document is the design for evolving the agent's
> quality over time once it's live.

## The core problem

The two LLM nodes (`plan_node`, `synthesize_node`) are the parts of the pipeline whose
*quality* isn't fully captured by pass/fail metrics (05). A `synthesize_node` call can
return schema-valid JSON — `{"summary": ..., "recommendations": [...]}` — that is
generic, ungrounded in the actual `scrape`/`sentiment`/`trend` data, or just not very
useful, and nothing in the current pipeline would catch that. Continuous improvement
means building the feedback loops that would.

## LLM-as-judge for automatic quality scoring

Run a separate, independent LLM call against each (sampled or full) `synthesize_node`
output, scoring it against the underlying data it was supposed to summarize:

- **Inputs to the judge**: the same `scrape`/`sentiment`/`trend` payload that went into
  `synthesize_node`, plus its output (`summary`, `recommendations`).
- **Rubric**: grounded (do the recommendations reference facts actually present in the
  data, e.g. real competitor names/prices, not invented ones), actionable (specific
  enough to act on, not "monitor the market"), internally consistent (does the summary
  match the sentiment/trend direction — e.g. doesn't claim "positive reception" when
  `sentiment.negative > sentiment.positive`), and non-generic (distinguishable from a
  report for a different product).
- **Output**: a numeric score (or per-criterion scores) stored against the
  `analyses` row (`04-data-storage.md`), so quality can be tracked as a time series and
  correlated with prompt version (below), model, and whether the report was partial
  (had `warnings`).
- This is the same idea as the output-quality sampling in
  [`05-monitoring-observability.md`](05-monitoring-observability.md); here the emphasis
  is using the judge's scores to *drive changes* (prompt edits, model changes), not
  just to alert on regressions.

## Prompt A/B testing

`app/agent/prompts.py` today holds `PLAN_SYSTEM`/`SYNTHESIS_SYSTEM` as static module
constants — fine for a fixed demo, but it means changing a prompt requires a code
deploy and gives no way to compare a candidate prompt against the current one on real
traffic before fully switching over. The production design:

- Prompts become rows in `agent_configs` (`04-data-storage.md`:
  `id, name, prompt_version, params, prompt_text, is_active`), loaded at the start of
  `plan_node`/`synthesize_node` instead of imported as constants.
- **Traffic split**: for a candidate prompt version, route a small percentage of live
  requests to it (e.g. hash `run_id` mod 100 < 5 → candidate, else → active), tag the
  resulting `analysis_events` row with which `prompt_version` was used.
- **Metric comparison**: compare the LLM-as-judge score distribution (and simpler
  proxies — response length, whether required JSON keys were present on first try
  without falling back, latency) between `prompt_version` cohorts over a large enough
  sample to be confident, then promote the winner by flipping `is_active`.
- Because this is versioned data, not code, rollback is instant (flip `is_active` back)
  and doesn't require a redeploy — a meaningful advantage once prompts are being
  iterated on frequently.

## User feedback loop

Automatic scoring (judge, proxies) approximates what a real user thinks; closing the
loop means actually collecting that signal:

- Add a lightweight feedback affordance to the UI (`app/ui/streamlit_app.py`): a
  thumbs up/down plus an optional free-text comment, submitted against the
  `analysis_id` already returned in the `X-Analysis-Id` response header
  (`app/api/routes.py::analyze`) — the wiring for this already half-exists, since the
  UI has the id available, it just isn't surfaced as a widget today.
- Store feedback as its own table (`analysis_feedback(analysis_id, rating, comment,
  created_at)`, referencing `analyses.id`) rather than mutating the report row, so
  feedback can arrive after the fact and multiple times.
- Feed low-rated (or commented) analyses into a **curated eval set**: a growing
  collection of `(input, output, human judgment)` triples that both the LLM-as-judge
  rubric and future prompt candidates get regression-tested against before rollout —
  this is what keeps prompt iteration from silently regressing on cases a real user
  already flagged as wrong.

## Capability evolution

The architecture is already built to make adding capability contained rather than
invasive (ADR 0001):

- **New tools** slot in behind the existing `BaseTool` interface
  (`app/tools/base.py`) — uniform `run()`/`ToolResult`/error handling for free; a fifth
  tool (e.g. a real competitor-review scraper, or a currency-conversion tool) doesn't
  touch the other four.
- **New capability in the graph** (e.g. a "compare two products" mode, or a
  trend-only quick report) means adding nodes/edges to `app/agent/graph.py` and
  extending `AgentState` — an explicit, reviewable change to the graph shape, not an
  emergent behavior from giving the LLM more tools to freely choose from (this is the
  trade-off already named as a consequence in ADR 0001).
- **Regression eval set**: before merging a graph or prompt change, run it against the
  curated eval set above (plus a fixed set of representative products) and require the
  LLM-as-judge score (and pass/fail schema validation) to not regress — the automatic-
  quality-scoring and user-feedback loops above aren't just monitoring, they're the
  input corpus that makes "did this change make things worse" answerable before it ships.
