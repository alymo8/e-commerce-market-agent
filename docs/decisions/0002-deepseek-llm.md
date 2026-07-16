# 0002 — DeepSeek via an OpenAI-compatible client

## Status

Accepted (2026-07-15).

## Context

The agent needs an LLM for exactly two things: normalizing/validating the incoming
analysis request (`plan_node`) and turning structured tool output into an executive
summary + recommendations (`synthesize_node`). The brief's additions explicitly request
**DeepSeek**, with an API key to be supplied via environment configuration, so the
choice of *provider* was largely made upstream. What remained was *how* to integrate
it, and which parts of the codebase should be allowed to depend on it.

## Decision

Call DeepSeek through `langchain_openai.ChatOpenAI`, pointed at DeepSeek's
OpenAI-compatible endpoint, wrapped in a single small module,
`app/llm/deepseek.py`:

```python
def get_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.deepseek_model,        # default "deepseek-chat"
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,   # default "https://api.deepseek.com"
        temperature=0.2,
        timeout=settings.request_timeout,
    )
```

`complete_json(system, user)` wraps `get_llm().invoke(...)`, extracts the first JSON
object from the reply with a regex (`_JSON_RE`), and raises `ValueError` if the reply
isn't parseable JSON. Nothing outside `app/llm/` and `app/agent/nodes.py` talks to an
LLM client directly — tools (`app/tools/`) never import it.

## Alternatives considered

**OpenAI (GPT models).** Rejected as the primary choice: higher cost per token for a
demo/test project where the value is in orchestration, not model quality; the brief
does not ask for OpenAI. (The `ChatOpenAI` client is still OpenAI's SDK shape — DeepSeek
publishes an OpenAI-compatible API, so no OpenAI account or key is needed, only the
client library.)

**Groq.** Attractive for very low latency (LPU-hosted open models), but was not the
model the brief named, and would have meant validating a different prompt/response
quality bar for JSON-mode reliability under time pressure. Not chosen.

**Local Ollama.** Zero API cost and no external dependency, which would even remove the
network requirement for the `plan`/`synthesize` nodes. Rejected for this project because
it shifts the reliability problem from "is the API key valid / is the service up" to
"is a multi-GB model pulled and running on whatever machine runs the demo," which is a
worse fit for a `docker-compose up` demo an evaluator runs on their own machine, and a
worse fit for a public Render/Railway deployment (ADR 0005) where a local model would
need a GPU-backed host.

## Consequences

- **OpenAI-compatible client, DeepSeek endpoint.** Because DeepSeek mirrors the OpenAI
  chat-completions API, `langchain_openai.ChatOpenAI` works unmodified by pointing
  `base_url` at `https://api.deepseek.com` — no bespoke LangChain integration needed,
  and swapping providers later (OpenAI, or another OpenAI-compatible endpoint) is a
  config change (`deepseek_base_url`, `deepseek_model`, `deepseek_api_key` in
  `app/core/config.py`), not a code change.
- **Spend is bounded by construction.** Because the LLM is confined to `plan` and
  `synthesize` (ADR 0001), cost per analysis is exactly two chat completions,
  regardless of how much mock/live data the tools produce. There is no LLM-in-a-loop
  path that could run away.
- **Defensive JSON parsing is required, not optional.** LLM replies are natural-language
  models, not guaranteed structured output — `complete_json` must tolerate prose
  wrapped around the JSON object (hence the regex extraction) and both `plan_node` and
  `synthesize_node` catch `Exception` broadly and fall back to a safe default
  (`app/agent/nodes.py`) rather than letting a malformed reply crash the graph. This
  mirrors the graceful-degradation posture of the tool layer.
- **Secrets stay in env/`.env`.** `deepseek_api_key` is read via `pydantic_settings`
  (`Settings.model_config = SettingsConfigDict(env_file=".env", ...)`); the key is never
  hardcoded and `.env` is not committed (see `.env.example`).
