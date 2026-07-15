# E-commerce Market Analysis Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an e-commerce market-analysis agent that orchestrates four specialized tools via a LangGraph state graph, exposed through a FastAPI REST API and a Streamlit UI, containerized for local and cloud (Render/Railway) deployment.

**Architecture:** Three separated layers — pure testable **tools** behind a common `BaseTool`, a LangGraph **agent** graph (`plan → scrape → [sentiment ∥ trend] → synthesize → report`) over a typed `AgentState`, and an **interface** layer (FastAPI API as the product, Streamlit UI as a client). The DeepSeek LLM is called only in the `plan` and `synthesize` nodes; everything else is deterministic. Tool failures are recorded in state and yield a partial report rather than a crash.

**Tech Stack:** Python 3.13 · LangGraph + langchain-openai (DeepSeek) · FastAPI + Pydantic v2 · Streamlit · httpx · pytest · Docker / docker-compose · Render.

## Global Constraints

- Python **3.13**. All schemas are **Pydantic v2**. Type hints on all public functions.
- All code, comments, docs, and UI text in **English**.
- LLM (DeepSeek) is called **only** in the `plan` and `synthesize` agent nodes. Tools are deterministic and LLM-free.
- The shared domain model `MarketReport` lives in `app/core/report.py` and is the single source of truth for report shape — imported by both tools and API.
- The Streamlit UI talks to the API over HTTP only; it must **not** import `app.agent` or `app.tools`.
- Secrets come from env / `.env` only. Never commit a real key. `DEEPSEEK_API_KEY` is required at runtime; tests never call the real LLM (always monkeypatched).
- Tests are lean and essential — do not over-test.
- Commit after every task.

## Shared Interfaces (locked — use these exact names/types across all tasks)

```python
# app/core/report.py — the domain model, imported everywhere a report is produced/consumed
class PriceInfo(BaseModel):        price: float; currency: str; source: str  # source: "live" | "mock"
class Competitor(BaseModel):       name: str; price: float
class SentimentBreakdown(BaseModel): positive: int; neutral: int; negative: int; total: int; top_positive_themes: list[str]; top_negative_themes: list[str]
class TrendPoint(BaseModel):       month: str; price: float
class PopularityPoint(BaseModel):  month: str; value: float
class TrendInfo(BaseModel):        direction: str; price_change_pct: float; price_history: list[TrendPoint]; popularity: list[PopularityPoint]
class MarketReport(BaseModel):
    product: str; marketplace: str | None
    price: PriceInfo; competitors: list[Competitor]
    sentiment: SentimentBreakdown; trend: TrendInfo
    summary: str; recommendations: list[str]
    warnings: list[str] = []       # partial-report tool errors surfaced to the user
    generated_at: str              # ISO 8601

# app/tools/base.py
class ToolResult(BaseModel):       tool: str; ok: bool; data: dict | None = None; error: str | None = None; duration_ms: float
class BaseTool(ABC):
    name: str
    def run(self, **kwargs) -> ToolResult   # wraps _execute with timing + exception capture
    @abstractmethod
    def _execute(self, **kwargs) -> dict

# Tool _execute return dicts (validated indirectly via MarketReport at report assembly):
# WebScraperTool.run(product: str, marketplace: str | None) -> data={"price","currency","source","competitors":[{"name","price"}]}
# SentimentAnalyzerTool.run(product: str) -> data={"positive","neutral","negative","total","top_positive_themes","top_negative_themes","sample_reviews"}
# TrendAnalyzerTool.run(product: str, months: int=6) -> data={"direction","price_change_pct","price_history":[{"month","price"}],"popularity":[{"month","value"}]}
# ReportGeneratorTool.run(product, marketplace, scrape, sentiment, trend, synthesis, warnings) -> data=MarketReport-shaped dict

# app/llm/deepseek.py
def get_llm() -> ChatOpenAI                # DeepSeek via OpenAI-compatible base_url
def complete_json(system: str, user: str) -> dict   # calls get_llm(), parses JSON object from the reply

# app/agent/state.py
class AgentState(TypedDict):
    run_id: str; product: str; marketplace: str | None
    plan: dict | None; scrape: dict | None; sentiment: dict | None; trend: dict | None
    synthesis: dict | None; report: dict | None
    errors: Annotated[list[dict], operator.add]   # reducer: parallel nodes append

# app/agent/graph.py
def build_graph()                          # returns compiled LangGraph
def run_analysis(product: str, marketplace: str | None = None) -> MarketReport

# app/api/store.py
def save(report: MarketReport) -> str      # returns analysis id
def get(analysis_id: str) -> MarketReport | None
def get_cached(product: str, marketplace: str | None) -> MarketReport | None
```

---

## File Structure

```
app/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── config.py          # pydantic-settings Settings + get_settings()
│   ├── errors.py          # ToolError
│   ├── logging.py         # configure_logging(), get_logger()
│   └── report.py          # MarketReport + sub-models (SHARED domain model)
├── tools/
│   ├── __init__.py
│   ├── base.py            # ToolResult, BaseTool
│   ├── mockdata.py        # deterministic seeded generators
│   ├── web_scraper.py     # WebScraperTool (live httpx + mock fallback)
│   ├── sentiment_analyzer.py
│   ├── trend_analyzer.py
│   └── report_generator.py
├── llm/
│   ├── __init__.py
│   └── deepseek.py        # get_llm(), complete_json()
├── agent/
│   ├── __init__.py
│   ├── state.py           # AgentState
│   ├── prompts.py         # PLAN_SYSTEM, SYNTHESIS_SYSTEM
│   ├── nodes.py           # plan/scrape/sentiment/trend/synthesize/report nodes
│   └── graph.py           # build_graph(), run_analysis()
├── api/
│   ├── __init__.py
│   ├── schemas.py         # AnalyzeRequest, AnalyzeResponse (= MarketReport)
│   ├── store.py           # in-memory cache/history
│   ├── routes.py          # /analyze, /analyses/{id}, /health
│   └── main.py            # FastAPI app
└── ui/
    └── streamlit_app.py   # API client UI

tests/
├── conftest.py            # fake_llm fixture
├── test_base_tool.py
├── test_web_scraper.py
├── test_sentiment_analyzer.py
├── test_trend_analyzer.py
├── test_report_generator.py
├── test_agent.py
└── test_api.py

Dockerfile
docker-compose.yml
render.yaml
.env.example
pyproject.toml
README.md                  # written last; install/use + theory summaries
docs/decisions/            # ADRs 0001-0005
docs/theory/               # 04-07
docs/architecture.md
sample_reports/            # generated example
```

---

## Task 1: Project scaffold, config, errors, logging

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.gitignore`
- Create: `app/__init__.py`, `app/core/__init__.py`, `app/core/config.py`, `app/core/errors.py`, `app/core/logging.py`
- Create: `tests/__init__.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `get_settings() -> Settings` with fields `deepseek_api_key`, `deepseek_base_url`, `deepseek_model`, `request_timeout`, `cache_ttl`, `enable_live_scrape`, `api_url`. `ToolError(tool, message)`. `configure_logging()`, `get_logger(name)`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "e-commerce-market-agent"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "langgraph>=0.2.28",
    "langchain-openai>=0.2.0",
    "langchain-core>=0.3.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",
    "httpx>=0.27.0",
    "streamlit>=1.38.0",
    "pandas>=2.2.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.3.0", "pytest-asyncio>=0.24.0"]

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.gitignore` and `.env.example`**

`.gitignore`:
```
__pycache__/
*.pyc
.env
.venv/
.pytest_cache/
*.egg-info/
```

`.env.example`:
```
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
REQUEST_TIMEOUT=20
CACHE_TTL=3600
ENABLE_LIVE_SCRAPE=false
API_URL=http://localhost:8000
```

- [ ] **Step 3: Write the failing test** — `tests/test_config.py`

```python
from app.core.config import get_settings
from app.core.errors import ToolError


def test_settings_have_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    s = get_settings()
    assert s.deepseek_api_key == "test-key"
    assert s.deepseek_base_url == "https://api.deepseek.com"
    assert s.deepseek_model == "deepseek-chat"
    assert s.enable_live_scrape is False


def test_tool_error_carries_tool_name():
    err = ToolError("web_scraper", "boom")
    assert err.tool == "web_scraper"
    assert "boom" in str(err)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.config'`

- [ ] **Step 5: Implement `app/__init__.py` and `app/core/__init__.py`** (both empty files), then `app/core/errors.py`

```python
class ToolError(Exception):
    """Raised inside a tool's _execute; carries the tool name for tracing."""

    def __init__(self, tool: str, message: str) -> None:
        self.tool = tool
        self.message = message
        super().__init__(f"[{tool}] {message}")
```

- [ ] **Step 6: Implement `app/core/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str = "not-set"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    request_timeout: int = 20
    cache_ttl: int = 3600
    enable_live_scrape: bool = False
    api_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 7: Implement `app/core/logging.py`**

```python
import logging

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml .gitignore .env.example app/ tests/
git commit -m "feat: project scaffold with config, errors, logging"
```

---

## Task 2: Shared domain model (`MarketReport`)

**Files:**
- Create: `app/core/report.py`
- Test: `tests/test_report_model.py`

**Interfaces:**
- Produces: `MarketReport`, `PriceInfo`, `Competitor`, `SentimentBreakdown`, `TrendPoint`, `PopularityPoint`, `TrendInfo` (exact fields from Shared Interfaces).

- [ ] **Step 1: Write the failing test** — `tests/test_report_model.py`

```python
from app.core.report import MarketReport


def _valid_payload() -> dict:
    return {
        "product": "iPhone 15",
        "marketplace": "amazon",
        "price": {"price": 999.0, "currency": "USD", "source": "mock"},
        "competitors": [{"name": "BestBuy", "price": 989.0}],
        "sentiment": {
            "positive": 7, "neutral": 2, "negative": 1, "total": 10,
            "top_positive_themes": ["camera"], "top_negative_themes": ["price"],
        },
        "trend": {
            "direction": "up", "price_change_pct": 3.5,
            "price_history": [{"month": "2026-01", "price": 990.0}],
            "popularity": [{"month": "2026-01", "value": 80.0}],
        },
        "summary": "Strong product.",
        "recommendations": ["Hold price"],
        "warnings": [],
        "generated_at": "2026-07-15T00:00:00Z",
    }


def test_market_report_validates():
    report = MarketReport.model_validate(_valid_payload())
    assert report.product == "iPhone 15"
    assert report.sentiment.total == 10
    assert report.trend.direction == "up"


def test_warnings_default_empty():
    payload = _valid_payload()
    del payload["warnings"]
    report = MarketReport.model_validate(payload)
    assert report.warnings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.report'`

- [ ] **Step 3: Implement `app/core/report.py`**

```python
from pydantic import BaseModel, Field


class PriceInfo(BaseModel):
    price: float
    currency: str
    source: str  # "live" | "mock"


class Competitor(BaseModel):
    name: str
    price: float


class SentimentBreakdown(BaseModel):
    positive: int
    neutral: int
    negative: int
    total: int
    top_positive_themes: list[str]
    top_negative_themes: list[str]


class TrendPoint(BaseModel):
    month: str
    price: float


class PopularityPoint(BaseModel):
    month: str
    value: float


class TrendInfo(BaseModel):
    direction: str  # "up" | "down" | "stable"
    price_change_pct: float
    price_history: list[TrendPoint]
    popularity: list[PopularityPoint]


class MarketReport(BaseModel):
    product: str
    marketplace: str | None = None
    price: PriceInfo
    competitors: list[Competitor]
    sentiment: SentimentBreakdown
    trend: TrendInfo
    summary: str
    recommendations: list[str]
    warnings: list[str] = Field(default_factory=list)
    generated_at: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report_model.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/core/report.py tests/test_report_model.py
git commit -m "feat: shared MarketReport domain model"
```

---

## Task 3: BaseTool + ToolResult

**Files:**
- Create: `app/tools/__init__.py`, `app/tools/base.py`
- Test: `tests/test_base_tool.py`

**Interfaces:**
- Consumes: `ToolError` (Task 1).
- Produces: `ToolResult`, `BaseTool` with `run(**kwargs) -> ToolResult` catching all exceptions and timing `_execute`.

- [ ] **Step 1: Write the failing test** — `tests/test_base_tool.py`

```python
from app.tools.base import BaseTool, ToolResult


class OkTool(BaseTool):
    name = "ok_tool"

    def _execute(self, **kwargs) -> dict:
        return {"value": kwargs["x"] * 2}


class BoomTool(BaseTool):
    name = "boom_tool"

    def _execute(self, **kwargs) -> dict:
        raise ValueError("kaboom")


def test_run_returns_ok_result_with_timing():
    result = OkTool().run(x=21)
    assert isinstance(result, ToolResult)
    assert result.ok is True
    assert result.data == {"value": 42}
    assert result.duration_ms >= 0


def test_run_captures_exception_as_failed_result():
    result = BoomTool().run()
    assert result.ok is False
    assert result.data is None
    assert "kaboom" in result.error
    assert result.tool == "boom_tool"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_base_tool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.tools.base'`

- [ ] **Step 3: Implement `app/tools/__init__.py`** (empty) and `app/tools/base.py`

```python
import time
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger("tools")


class ToolResult(BaseModel):
    tool: str
    ok: bool
    data: dict | None = None
    error: str | None = None
    duration_ms: float


class BaseTool(ABC):
    name: str = "base"

    @abstractmethod
    def _execute(self, **kwargs) -> dict:
        """Do the work. Raise on failure; the base class captures it."""

    def run(self, **kwargs) -> ToolResult:
        start = time.perf_counter()
        try:
            data = self._execute(**kwargs)
            duration = (time.perf_counter() - start) * 1000
            logger.info("tool=%s ok duration_ms=%.1f", self.name, duration)
            return ToolResult(tool=self.name, ok=True, data=data, duration_ms=duration)
        except Exception as exc:  # noqa: BLE001 - tools must never crash the graph
            duration = (time.perf_counter() - start) * 1000
            logger.warning("tool=%s failed: %s", self.name, exc)
            return ToolResult(
                tool=self.name, ok=False, error=str(exc), duration_ms=duration
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_base_tool.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/tools/__init__.py app/tools/base.py tests/test_base_tool.py
git commit -m "feat: BaseTool with timing and error capture"
```

---

## Task 4: Deterministic mock data generators

**Files:**
- Create: `app/tools/mockdata.py`
- Test: `tests/test_mockdata.py`

**Interfaces:**
- Produces: `seeded_rng(product) -> random.Random`, `mock_price(product) -> tuple[float, str]`, `mock_competitors(product) -> list[dict]`, `mock_reviews(product) -> list[str]`, `mock_series(product, months) -> tuple[list[dict], list[dict]]`. Deterministic per product string.

- [ ] **Step 1: Write the failing test** — `tests/test_mockdata.py`

```python
from app.tools import mockdata


def test_price_is_deterministic():
    assert mockdata.mock_price("iPhone 15") == mockdata.mock_price("iPhone 15")


def test_different_products_differ():
    assert mockdata.mock_price("iPhone 15") != mockdata.mock_price("Nike Air Max")


def test_reviews_and_series_shape():
    reviews = mockdata.mock_reviews("iPhone 15")
    assert len(reviews) >= 8
    prices, popularity = mockdata.mock_series("iPhone 15", months=6)
    assert len(prices) == 6 and len(popularity) == 6
    assert set(prices[0]) == {"month", "price"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mockdata.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/tools/mockdata.py`**

```python
import hashlib
import random
from datetime import date

_POSITIVE = [
    "Amazing build quality, worth every penny.",
    "The camera is fantastic and battery lasts all day.",
    "Fast shipping and works exactly as described.",
    "Best purchase this year, highly recommend.",
    "Great value, the design feels premium.",
]
_NEGATIVE = [
    "Too expensive for what you get.",
    "Stopped working after two weeks, disappointed.",
    "Customer support was slow and unhelpful.",
]
_NEUTRAL = [
    "It is okay, does the job but nothing special.",
    "Average product, matches the description.",
]
_COMPETITOR_NAMES = ["BestBuy", "Walmart", "eBay", "Newegg", "Target"]


def seeded_rng(product: str) -> random.Random:
    digest = hashlib.sha256(product.lower().encode()).hexdigest()
    return random.Random(int(digest[:8], 16))


def mock_price(product: str) -> tuple[float, str]:
    rng = seeded_rng(product)
    return round(rng.uniform(20, 1200), 2), "USD"


def mock_competitors(product: str) -> list[dict]:
    rng = seeded_rng(product)
    base, _ = mock_price(product)
    names = rng.sample(_COMPETITOR_NAMES, k=3)
    return [
        {"name": n, "price": round(base * rng.uniform(0.9, 1.1), 2)} for n in names
    ]


def mock_reviews(product: str) -> list[str]:
    rng = seeded_rng(product)
    reviews = _POSITIVE * 2 + _NEGATIVE + _NEUTRAL
    rng.shuffle(reviews)
    return reviews


def mock_series(product: str, months: int = 6) -> tuple[list[dict], list[dict]]:
    rng = seeded_rng(product)
    base, _ = mock_price(product)
    today = date.today()
    prices, popularity = [], []
    price = base
    pop = rng.uniform(40, 90)
    for i in range(months, 0, -1):
        m = (today.month - i - 1) % 12 + 1
        y = today.year + ((today.month - i - 1) // 12)
        label = f"{y:04d}-{m:02d}"
        price = round(price * rng.uniform(0.97, 1.03), 2)
        pop = round(min(100, max(0, pop + rng.uniform(-8, 8))), 1)
        prices.append({"month": label, "price": price})
        popularity.append({"month": label, "value": pop})
    return prices, popularity
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mockdata.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/tools/mockdata.py tests/test_mockdata.py
git commit -m "feat: deterministic seeded mock data generators"
```

---

## Task 5: Web Scraper tool (live + mock fallback)

**Files:**
- Create: `app/tools/web_scraper.py`
- Test: `tests/test_web_scraper.py`

**Interfaces:**
- Consumes: `BaseTool` (Task 3), `mockdata` (Task 4), `get_settings` (Task 1).
- Produces: `WebScraperTool.run(product, marketplace=None) -> ToolResult` with `data={"price","currency","source","competitors":[{"name","price"}]}`. `source` is `"live"` or `"mock"`. Live path genuinely fetches + parses DummyJSON; `_parse(payload)` is a pure staticmethod so it is unit-testable without network.

- [ ] **Step 1: Write the failing test** — `tests/test_web_scraper.py`

```python
from app.tools.web_scraper import WebScraperTool

# A realistic DummyJSON search payload (trimmed to the fields we read).
SAMPLE_PAYLOAD = {
    "products": [
        {"title": "iPhone 15", "brand": "Apple", "price": 999.0},
        {"title": "iPhone 15 Case", "brand": "Spigen", "price": 19.0},
        {"title": "Phone Charger", "brand": "Anker", "price": 25.0},
        {"title": "Screen Protector", "brand": "ESR", "price": 9.0},
    ]
}


def test_parse_extracts_price_and_competitors():
    data = WebScraperTool._parse(SAMPLE_PAYLOAD)
    assert data["source"] == "live"
    assert data["price"] == 999.0
    assert data["currency"] == "USD"
    assert len(data["competitors"]) == 3
    assert data["competitors"][0]["name"] == "Spigen"


def test_parse_raises_on_empty_results():
    import pytest
    with pytest.raises(ValueError):
        WebScraperTool._parse({"products": []})


def test_fallback_to_mock_when_live_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.tools.web_scraper.get_settings",
        lambda: type("S", (), {"enable_live_scrape": False, "request_timeout": 5})(),
    )
    result = WebScraperTool().run(product="iPhone 15", marketplace="amazon")
    assert result.ok is True
    assert result.data["source"] == "mock"
    assert result.data["currency"] == "USD"
    assert len(result.data["competitors"]) == 3


def test_live_failure_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(
        "app.tools.web_scraper.get_settings",
        lambda: type("S", (), {"enable_live_scrape": True, "request_timeout": 5})(),
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("app.tools.web_scraper.WebScraperTool._scrape_live", boom)
    result = WebScraperTool().run(product="iPhone 15")
    assert result.ok is True
    assert result.data["source"] == "mock"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_scraper.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/tools/web_scraper.py`**

```python
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.tools.base import BaseTool
from app.tools.mockdata import mock_competitors, mock_price

logger = get_logger("tools.web_scraper")


class WebScraperTool(BaseTool):
    """Collect product price + competitor prices.

    Strategy: when live scraping is enabled, genuinely fetch structured product
    data from DummyJSON (a real, key-less product API) and parse a price plus
    competitor prices. On any network/parse failure, or when disabled, fall back
    to deterministic mock data so the demo always produces a result.
    """

    name = "web_scraper"
    SEARCH_URL = "https://dummyjson.com/products/search"

    def _execute(self, product: str, marketplace: str | None = None) -> dict:
        settings = get_settings()
        if settings.enable_live_scrape:
            try:
                return self._scrape_live(product, settings.request_timeout)
            except Exception as exc:  # noqa: BLE001 - fall back, never crash
                logger.warning("live scrape failed (%s); using mock", exc)
        return self._mock(product)

    def _scrape_live(self, product: str, timeout: int) -> dict:
        resp = httpx.get(
            self.SEARCH_URL,
            params={"q": product, "limit": 5},
            timeout=timeout,
            headers={"User-Agent": "market-agent/0.1"},
        )
        resp.raise_for_status()
        return self._parse(resp.json())

    @staticmethod
    def _parse(payload: dict) -> dict:
        """Pure parser over a DummyJSON search response. Raises on empty results."""
        products = payload.get("products", [])
        if not products:
            raise ValueError("no live results")
        top = products[0]
        competitors = [
            {
                "name": p.get("brand") or str(p.get("title", "Unknown"))[:24],
                "price": float(p["price"]),
            }
            for p in products[1:4]
        ]
        return {
            "price": float(top["price"]),
            "currency": "USD",
            "source": "live",
            "competitors": competitors,
        }

    def _mock(self, product: str) -> dict:
        price, currency = mock_price(product)
        return {
            "price": price,
            "currency": currency,
            "source": "mock",
            "competitors": mock_competitors(product),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_scraper.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/tools/web_scraper.py tests/test_web_scraper.py
git commit -m "feat: web scraper tool with live attempt and mock fallback"
```

---

## Task 6: Sentiment Analyzer tool

**Files:**
- Create: `app/tools/sentiment_analyzer.py`
- Test: `tests/test_sentiment_analyzer.py`

**Interfaces:**
- Consumes: `BaseTool`, `mockdata.mock_reviews`.
- Produces: `SentimentAnalyzerTool.run(product) -> ToolResult` with `data={"positive","neutral","negative","total","top_positive_themes","top_negative_themes","sample_reviews"}`. Deterministic keyword-based classification (no LLM).

- [ ] **Step 1: Write the failing test** — `tests/test_sentiment_analyzer.py`

```python
from app.tools.sentiment_analyzer import SentimentAnalyzerTool


def test_sentiment_counts_sum_to_total():
    result = SentimentAnalyzerTool().run(product="iPhone 15")
    d = result.data
    assert result.ok is True
    assert d["positive"] + d["neutral"] + d["negative"] == d["total"]
    assert d["total"] >= 8
    assert isinstance(d["top_positive_themes"], list)
    assert len(d["sample_reviews"]) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sentiment_analyzer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/tools/sentiment_analyzer.py`**

```python
from app.tools.base import BaseTool
from app.tools.mockdata import mock_reviews

_POSITIVE_WORDS = {"amazing", "fantastic", "great", "best", "worth", "premium", "recommend", "fast"}
_NEGATIVE_WORDS = {"expensive", "disappointed", "slow", "stopped", "unhelpful", "too"}


def _classify(review: str) -> str:
    text = review.lower()
    pos = sum(w in text for w in _POSITIVE_WORDS)
    neg = sum(w in text for w in _NEGATIVE_WORDS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _themes(reviews: list[str], words: set[str]) -> list[str]:
    hits = [w for r in reviews for w in words if w in r.lower()]
    seen = []
    for w in hits:
        if w not in seen:
            seen.append(w)
    return seen[:3]


class SentimentAnalyzerTool(BaseTool):
    """Classify a mock review corpus with deterministic keyword rules."""

    name = "sentiment_analyzer"

    def _execute(self, product: str) -> dict:
        reviews = mock_reviews(product)
        labels = [_classify(r) for r in reviews]
        pos = labels.count("positive")
        neg = labels.count("negative")
        neu = labels.count("neutral")
        return {
            "positive": pos,
            "neutral": neu,
            "negative": neg,
            "total": len(reviews),
            "top_positive_themes": _themes(reviews, _POSITIVE_WORDS),
            "top_negative_themes": _themes(reviews, _NEGATIVE_WORDS),
            "sample_reviews": reviews[:3],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sentiment_analyzer.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/tools/sentiment_analyzer.py tests/test_sentiment_analyzer.py
git commit -m "feat: sentiment analyzer tool (deterministic keyword classification)"
```

---

## Task 7: Trend Analyzer tool

**Files:**
- Create: `app/tools/trend_analyzer.py`
- Test: `tests/test_trend_analyzer.py`

**Interfaces:**
- Consumes: `BaseTool`, `mockdata.mock_series`.
- Produces: `TrendAnalyzerTool.run(product, months=6) -> ToolResult` with `data={"direction","price_change_pct","price_history","popularity"}`.

- [ ] **Step 1: Write the failing test** — `tests/test_trend_analyzer.py`

```python
from app.tools.trend_analyzer import TrendAnalyzerTool


def test_trend_structure_and_direction():
    result = TrendAnalyzerTool().run(product="iPhone 15", months=6)
    d = result.data
    assert result.ok is True
    assert len(d["price_history"]) == 6
    assert len(d["popularity"]) == 6
    assert d["direction"] in {"up", "down", "stable"}
    assert isinstance(d["price_change_pct"], float)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_trend_analyzer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/tools/trend_analyzer.py`**

```python
from app.tools.base import BaseTool
from app.tools.mockdata import mock_series


class TrendAnalyzerTool(BaseTool):
    """Compute price/popularity trend from a simulated time-series."""

    name = "trend_analyzer"

    def _execute(self, product: str, months: int = 6) -> dict:
        prices, popularity = mock_series(product, months)
        first = prices[0]["price"]
        last = prices[-1]["price"]
        change = round((last - first) / first * 100, 2) if first else 0.0
        if change > 2:
            direction = "up"
        elif change < -2:
            direction = "down"
        else:
            direction = "stable"
        return {
            "direction": direction,
            "price_change_pct": change,
            "price_history": prices,
            "popularity": popularity,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_trend_analyzer.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/tools/trend_analyzer.py tests/test_trend_analyzer.py
git commit -m "feat: trend analyzer tool"
```

---

## Task 8: Report Generator tool

**Files:**
- Create: `app/tools/report_generator.py`
- Test: `tests/test_report_generator.py`

**Interfaces:**
- Consumes: `BaseTool`, `MarketReport` (Task 2).
- Produces: `ReportGeneratorTool.run(product, marketplace, scrape, sentiment, trend, synthesis, warnings) -> ToolResult` with `data` = a dict that validates as `MarketReport`. Pure compilation; no data invention beyond assembly + timestamp.

- [ ] **Step 1: Write the failing test** — `tests/test_report_generator.py`

```python
from app.core.report import MarketReport
from app.tools.report_generator import ReportGeneratorTool

SCRAPE = {"price": 999.0, "currency": "USD", "source": "mock",
          "competitors": [{"name": "BestBuy", "price": 989.0}]}
SENTIMENT = {"positive": 7, "neutral": 2, "negative": 1, "total": 10,
             "top_positive_themes": ["great"], "top_negative_themes": ["expensive"],
             "sample_reviews": ["Great value."]}
TREND = {"direction": "up", "price_change_pct": 3.5,
         "price_history": [{"month": "2026-01", "price": 990.0}],
         "popularity": [{"month": "2026-01", "value": 80.0}]}
SYNTHESIS = {"summary": "Strong.", "recommendations": ["Hold price"]}


def test_report_generator_produces_valid_market_report():
    result = ReportGeneratorTool().run(
        product="iPhone 15", marketplace="amazon",
        scrape=SCRAPE, sentiment=SENTIMENT, trend=TREND,
        synthesis=SYNTHESIS, warnings=["trend degraded"],
    )
    assert result.ok is True
    report = MarketReport.model_validate(result.data)
    assert report.product == "iPhone 15"
    assert report.price.price == 999.0
    assert report.warnings == ["trend degraded"]
    assert report.recommendations == ["Hold price"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_generator.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/tools/report_generator.py`**

```python
from datetime import datetime, timezone

from app.core.report import MarketReport
from app.tools.base import BaseTool


class ReportGeneratorTool(BaseTool):
    """Compile tool outputs + LLM synthesis into a validated MarketReport dict."""

    name = "report_generator"

    def _execute(
        self,
        product: str,
        marketplace: str | None,
        scrape: dict,
        sentiment: dict,
        trend: dict,
        synthesis: dict,
        warnings: list[str],
    ) -> dict:
        report = MarketReport(
            product=product,
            marketplace=marketplace,
            price={
                "price": scrape["price"],
                "currency": scrape["currency"],
                "source": scrape["source"],
            },
            competitors=scrape["competitors"],
            sentiment={
                "positive": sentiment["positive"],
                "neutral": sentiment["neutral"],
                "negative": sentiment["negative"],
                "total": sentiment["total"],
                "top_positive_themes": sentiment["top_positive_themes"],
                "top_negative_themes": sentiment["top_negative_themes"],
            },
            trend={
                "direction": trend["direction"],
                "price_change_pct": trend["price_change_pct"],
                "price_history": trend["price_history"],
                "popularity": trend["popularity"],
            },
            summary=synthesis["summary"],
            recommendations=synthesis["recommendations"],
            warnings=warnings,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        return report.model_dump()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report_generator.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/tools/report_generator.py tests/test_report_generator.py
git commit -m "feat: report generator tool compiling a validated MarketReport"
```

---

## Task 9: DeepSeek LLM client

**Files:**
- Create: `app/llm/__init__.py`, `app/llm/deepseek.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Consumes: `get_settings`.
- Produces: `get_llm() -> ChatOpenAI`; `complete_json(system, user) -> dict` that invokes the LLM and parses the first JSON object from the reply (raises `ValueError` if none).

- [ ] **Step 1: Write the failing test** — `tests/test_llm.py`

```python
from app.llm.deepseek import extract_json_object


def test_extract_json_from_fenced_reply():
    reply = 'Here you go:\n```json\n{"summary": "ok", "recommendations": ["a"]}\n```'
    obj = extract_json_object(reply)
    assert obj["summary"] == "ok"
    assert obj["recommendations"] == ["a"]


def test_extract_json_raises_when_absent():
    import pytest
    with pytest.raises(ValueError):
        extract_json_object("no json here")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/llm/__init__.py`** (empty) and `app/llm/deepseek.py`

```python
import json
import re

from langchain_openai import ChatOpenAI

from app.core.config import get_settings

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def get_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=0.2,
        timeout=settings.request_timeout,
    )


def extract_json_object(text: str) -> dict:
    match = _JSON_RE.search(text)
    if not match:
        raise ValueError("no JSON object found in LLM reply")
    return json.loads(match.group(0))


def complete_json(system: str, user: str) -> dict:
    llm = get_llm()
    reply = llm.invoke([("system", system), ("human", user)])
    return extract_json_object(reply.content)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/llm/ tests/test_llm.py
git commit -m "feat: DeepSeek LLM client with JSON extraction"
```

---

## Task 10: Agent state + prompts

**Files:**
- Create: `app/agent/__init__.py`, `app/agent/state.py`, `app/agent/prompts.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces: `AgentState` TypedDict (exact fields from Shared Interfaces); `PLAN_SYSTEM`, `SYNTHESIS_SYSTEM` prompt strings.

- [ ] **Step 1: Write the failing test** — `tests/test_state.py`

```python
from app.agent.state import AgentState
from app.agent import prompts


def test_state_keys_present():
    keys = AgentState.__annotations__
    for k in ["run_id", "product", "marketplace", "plan", "scrape",
              "sentiment", "trend", "synthesis", "report", "errors"]:
        assert k in keys


def test_prompts_nonempty():
    assert "JSON" in prompts.PLAN_SYSTEM
    assert "JSON" in prompts.SYNTHESIS_SYSTEM
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/agent/__init__.py`** (empty), `app/agent/state.py`

```python
import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict):
    run_id: str
    product: str
    marketplace: str | None
    plan: dict | None
    scrape: dict | None
    sentiment: dict | None
    trend: dict | None
    synthesis: dict | None
    report: dict | None
    errors: Annotated[list[dict], operator.add]
```

- [ ] **Step 4: Implement `app/agent/prompts.py`**

```python
PLAN_SYSTEM = """You are a market-analysis planner. Given a raw product request,
normalize it and decide the analysis scope. Reply ONLY with a JSON object:
{"normalized_product": "<clean product name>",
 "marketplace": "<marketplace or null>",
 "focus": "<one short sentence on what matters for this product>"}"""

SYNTHESIS_SYSTEM = """You are a senior e-commerce market analyst. Given structured
data (price, competitors, sentiment, trend) you write a concise executive summary and
concrete business recommendations. Reply ONLY with a JSON object:
{"summary": "<3-4 sentence executive summary>",
 "recommendations": ["<action 1>", "<action 2>", "<action 3>"]}"""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_state.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add app/agent/__init__.py app/agent/state.py app/agent/prompts.py tests/test_state.py
git commit -m "feat: agent state and prompts"
```

---

## Task 11: Agent nodes

**Files:**
- Create: `app/agent/nodes.py`
- Test: `tests/test_nodes.py`

**Interfaces:**
- Consumes: `AgentState`, prompts, all four tools, `complete_json` (imported as module attribute so tests can monkeypatch `app.agent.nodes.complete_json`).
- Produces: `plan_node`, `scrape_node`, `sentiment_node`, `trend_node`, `synthesize_node`, `report_node` — each `(state: AgentState) -> dict` returning a partial state update. On tool failure a node appends to `errors` and writes a safe empty default so downstream nodes can proceed.

- [ ] **Step 1: Write the failing test** — `tests/test_nodes.py`

```python
from app.agent import nodes


def test_scrape_node_populates_scrape():
    state = {"product": "iPhone 15", "marketplace": "amazon", "errors": []}
    update = nodes.scrape_node(state)
    assert update["scrape"]["currency"] == "USD"


def test_synthesize_node_uses_llm(monkeypatch):
    monkeypatch.setattr(
        nodes, "complete_json",
        lambda system, user: {"summary": "s", "recommendations": ["r1"]},
    )
    state = {
        "product": "iPhone 15", "marketplace": "amazon",
        "scrape": {"price": 1.0, "currency": "USD", "source": "mock", "competitors": []},
        "sentiment": {"positive": 1, "neutral": 0, "negative": 0, "total": 1,
                      "top_positive_themes": [], "top_negative_themes": []},
        "trend": {"direction": "up", "price_change_pct": 1.0,
                  "price_history": [], "popularity": []},
        "errors": [],
    }
    update = nodes.synthesize_node(state)
    assert update["synthesis"]["summary"] == "s"


def test_synthesize_node_falls_back_on_llm_error(monkeypatch):
    def boom(system, user):
        raise RuntimeError("llm down")
    monkeypatch.setattr(nodes, "complete_json", boom)
    state = {"product": "x", "marketplace": None, "scrape": {}, "sentiment": {},
             "trend": {}, "errors": []}
    update = nodes.synthesize_node(state)
    assert "synthesis" in update
    assert update["errors"]  # error recorded
    assert update["synthesis"]["recommendations"]  # safe default present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_nodes.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/agent/nodes.py`**

```python
from app.agent.prompts import PLAN_SYSTEM, SYNTHESIS_SYSTEM
from app.core.logging import get_logger
from app.llm.deepseek import complete_json
from app.tools.report_generator import ReportGeneratorTool
from app.tools.sentiment_analyzer import SentimentAnalyzerTool
from app.tools.trend_analyzer import TrendAnalyzerTool
from app.tools.web_scraper import WebScraperTool

logger = get_logger("agent.nodes")

_scraper = WebScraperTool()
_sentiment = SentimentAnalyzerTool()
_trend = TrendAnalyzerTool()
_report = ReportGeneratorTool()


def _err(tool: str, message: str) -> dict:
    return {"tool": tool, "error": message}


def plan_node(state: dict) -> dict:
    product = state["product"]
    marketplace = state.get("marketplace")
    try:
        plan = complete_json(PLAN_SYSTEM, f"Product: {product}\nMarketplace: {marketplace}")
    except Exception as exc:  # noqa: BLE001 - planning is best-effort
        logger.warning("plan failed: %s", exc)
        plan = {"normalized_product": product, "marketplace": marketplace, "focus": ""}
        return {"plan": plan, "product": product, "marketplace": marketplace,
                "errors": [_err("planner", str(exc))]}
    return {
        "plan": plan,
        "product": plan.get("normalized_product") or product,
        "marketplace": plan.get("marketplace") if plan.get("marketplace") != "null" else marketplace,
    }


def scrape_node(state: dict) -> dict:
    result = _scraper.run(product=state["product"], marketplace=state.get("marketplace"))
    if result.ok:
        return {"scrape": result.data}
    fallback = {"price": 0.0, "currency": "USD", "source": "mock", "competitors": []}
    return {"scrape": fallback, "errors": [_err("web_scraper", result.error)]}


def sentiment_node(state: dict) -> dict:
    result = _sentiment.run(product=state["product"])
    if result.ok:
        return {"sentiment": result.data}
    fallback = {"positive": 0, "neutral": 0, "negative": 0, "total": 0,
                "top_positive_themes": [], "top_negative_themes": []}
    return {"sentiment": fallback, "errors": [_err("sentiment_analyzer", result.error)]}


def trend_node(state: dict) -> dict:
    result = _trend.run(product=state["product"])
    if result.ok:
        return {"trend": result.data}
    fallback = {"direction": "stable", "price_change_pct": 0.0,
                "price_history": [], "popularity": []}
    return {"trend": fallback, "errors": [_err("trend_analyzer", result.error)]}


def synthesize_node(state: dict) -> dict:
    user = (
        f"Product: {state['product']}\n"
        f"Price data: {state['scrape']}\n"
        f"Sentiment: {state['sentiment']}\n"
        f"Trend: {state['trend']}"
    )
    try:
        synthesis = complete_json(SYNTHESIS_SYSTEM, user)
        if "summary" not in synthesis or "recommendations" not in synthesis:
            raise ValueError("synthesis missing required keys")
        return {"synthesis": synthesis}
    except Exception as exc:  # noqa: BLE001 - degrade to a safe default summary
        logger.warning("synthesis failed: %s", exc)
        fallback = {
            "summary": f"Automated analysis for {state['product']} "
                       "(LLM synthesis unavailable; showing collected data).",
            "recommendations": ["Review collected price, sentiment, and trend data manually."],
        }
        return {"synthesis": fallback, "errors": [_err("synthesizer", str(exc))]}


def report_node(state: dict) -> dict:
    warnings = [f"{e['tool']}: {e['error']}" for e in state.get("errors", [])]
    result = _report.run(
        product=state["product"],
        marketplace=state.get("marketplace"),
        scrape=state["scrape"],
        sentiment=state["sentiment"],
        trend=state["trend"],
        synthesis=state["synthesis"],
        warnings=warnings,
    )
    if result.ok:
        return {"report": result.data}
    return {"report": None, "errors": [_err("report_generator", result.error)]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_nodes.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/agent/nodes.py tests/test_nodes.py
git commit -m "feat: agent nodes with graceful degradation"
```

---

## Task 12: Agent graph assembly

**Files:**
- Create: `app/agent/graph.py`
- Test: `tests/test_agent.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: nodes, `AgentState`, `MarketReport`.
- Produces: `build_graph()` (compiled LangGraph with parallel sentiment/trend) and `run_analysis(product, marketplace=None) -> MarketReport`.

- [ ] **Step 1: Write `tests/conftest.py`** (shared fake-LLM fixture)

```python
import pytest


@pytest.fixture
def fake_llm(monkeypatch):
    """Patch complete_json everywhere the nodes use it, no network calls."""
    def _fake(system, user):
        if "planner" in system.lower() or "normalized_product" in system:
            return {"normalized_product": "iPhone 15", "marketplace": "amazon", "focus": "x"}
        return {"summary": "Executive summary.", "recommendations": ["Do A", "Do B"]}
    monkeypatch.setattr("app.agent.nodes.complete_json", _fake)
    return _fake
```

- [ ] **Step 2: Write the failing test** — `tests/test_agent.py`

```python
from app.agent.graph import run_analysis
from app.core.report import MarketReport


def test_full_pipeline_produces_valid_report(fake_llm):
    report = run_analysis("iPhone 15", "amazon")
    assert isinstance(report, MarketReport)
    assert report.product
    assert report.price.currency == "USD"
    assert report.sentiment.total >= 8
    assert len(report.trend.price_history) == 6
    assert report.summary == "Executive summary."
    assert len(report.recommendations) == 2
    assert report.warnings == []


def test_pipeline_degrades_when_a_tool_fails(fake_llm, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("scraper exploded")
    monkeypatch.setattr("app.agent.nodes._scraper._execute", boom)
    report = run_analysis("iPhone 15", "amazon")
    assert isinstance(report, MarketReport)          # still returns a report
    assert any("web_scraper" in w for w in report.warnings)  # failure surfaced
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agent.graph'`

- [ ] **Step 4: Implement `app/agent/graph.py`**

```python
import uuid

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    plan_node,
    report_node,
    scrape_node,
    sentiment_node,
    synthesize_node,
    trend_node,
)
from app.agent.state import AgentState
from app.core.report import MarketReport


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("plan", plan_node)
    g.add_node("scrape", scrape_node)
    g.add_node("sentiment", sentiment_node)
    g.add_node("trend", trend_node)
    g.add_node("synthesize", synthesize_node)
    g.add_node("report", report_node)

    g.add_edge(START, "plan")
    g.add_edge("plan", "scrape")
    # fan-out: sentiment and trend run in parallel after scrape
    g.add_edge("scrape", "sentiment")
    g.add_edge("scrape", "trend")
    # fan-in: synthesize waits for BOTH analysis nodes
    g.add_edge("sentiment", "synthesize")
    g.add_edge("trend", "synthesize")
    g.add_edge("synthesize", "report")
    g.add_edge("report", END)
    return g.compile()


_GRAPH = build_graph()


def run_analysis(product: str, marketplace: str | None = None) -> MarketReport:
    initial: AgentState = {
        "run_id": str(uuid.uuid4()),
        "product": product,
        "marketplace": marketplace,
        "plan": None, "scrape": None, "sentiment": None, "trend": None,
        "synthesis": None, "report": None, "errors": [],
    }
    final = _GRAPH.invoke(initial)
    return MarketReport.model_validate(final["report"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_agent.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add app/agent/graph.py tests/test_agent.py tests/conftest.py
git commit -m "feat: LangGraph assembly with parallel analysis and partial-report degradation"
```

---

## Task 13: API layer (store, schemas, routes, app)

**Files:**
- Create: `app/api/__init__.py`, `app/api/store.py`, `app/api/schemas.py`, `app/api/routes.py`, `app/api/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `run_analysis`, `MarketReport`, `get_settings`.
- Produces: `POST /analyze`, `GET /analyses/{id}`, `GET /health`. In-memory store with TTL cache keyed by `(product, marketplace)`.

- [ ] **Step 1: Write the failing test** — `tests/test_api.py`

```python
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_analyze_returns_report_and_is_retrievable(fake_llm):
    resp = client.post("/analyze", json={"product": "iPhone 15", "marketplace": "amazon"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["product"]
    assert body["price"]["currency"] == "USD"
    analysis_id = resp.headers["X-Analysis-Id"]
    got = client.get(f"/analyses/{analysis_id}")
    assert got.status_code == 200
    assert got.json()["product"] == body["product"]


def test_unknown_analysis_returns_404():
    assert client.get("/analyses/does-not-exist").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api.main'`

- [ ] **Step 3: Implement `app/api/__init__.py`** (empty) and `app/api/store.py`

```python
import time
import uuid

from app.core.config import get_settings
from app.core.report import MarketReport

_BY_ID: dict[str, MarketReport] = {}
_CACHE: dict[str, tuple[float, str]] = {}  # key -> (expires_at, analysis_id)


def _key(product: str, marketplace: str | None) -> str:
    return f"{product.lower().strip()}::{(marketplace or '').lower().strip()}"


def save(report: MarketReport) -> str:
    analysis_id = str(uuid.uuid4())
    _BY_ID[analysis_id] = report
    ttl = get_settings().cache_ttl
    _CACHE[_key(report.product, report.marketplace)] = (time.time() + ttl, analysis_id)
    return analysis_id


def get(analysis_id: str) -> MarketReport | None:
    return _BY_ID.get(analysis_id)


def get_cached(product: str, marketplace: str | None) -> MarketReport | None:
    entry = _CACHE.get(_key(product, marketplace))
    if not entry:
        return None
    expires_at, analysis_id = entry
    if time.time() > expires_at:
        return None
    return _BY_ID.get(analysis_id)
```

- [ ] **Step 4: Implement `app/api/schemas.py`**

```python
from pydantic import BaseModel, Field

from app.core.report import MarketReport

AnalyzeResponse = MarketReport


class AnalyzeRequest(BaseModel):
    product: str = Field(min_length=1, examples=["iPhone 15"])
    marketplace: str | None = Field(default=None, examples=["amazon"])
```

- [ ] **Step 5: Implement `app/api/routes.py`**

```python
from fastapi import APIRouter, HTTPException, Response

from app.agent.graph import run_analysis
from app.api import store
from app.api.schemas import AnalyzeRequest, AnalyzeResponse

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest, response: Response) -> AnalyzeResponse:
    cached = store.get_cached(req.product, req.marketplace)
    report = cached or run_analysis(req.product, req.marketplace)
    analysis_id = store.save(report)
    response.headers["X-Analysis-Id"] = analysis_id
    response.headers["X-Cache"] = "HIT" if cached else "MISS"
    return report


@router.get("/analyses/{analysis_id}", response_model=AnalyzeResponse)
def get_analysis(analysis_id: str) -> AnalyzeResponse:
    report = store.get(analysis_id)
    if report is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return report
```

- [ ] **Step 6: Implement `app/api/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="E-commerce Market Analysis Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.include_router(router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 8: Run the full suite**

Run: `pytest -v`
Expected: PASS (all tests green)

- [ ] **Step 9: Commit**

```bash
git add app/api/ tests/test_api.py
git commit -m "feat: FastAPI layer with analyze/retrieve endpoints and TTL cache"
```

---

## Task 14: Streamlit UI

**Files:**
- Create: `app/ui/__init__.py`, `app/ui/streamlit_app.py`

**Interfaces:**
- Consumes: the HTTP API only (via `API_URL` env). Must not import `app.agent`/`app.tools`.

- [ ] **Step 1: Implement `app/ui/__init__.py`** (empty) and `app/ui/streamlit_app.py`

```python
import os

import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Market Analysis Agent", page_icon="📊", layout="wide")
st.title("📊 E-commerce Market Analysis Agent")
st.caption("Enter a product; the agent scrapes price, analyzes sentiment and trend, "
           "then an LLM writes recommendations.")

with st.form("analyze"):
    col1, col2 = st.columns([3, 1])
    product = col1.text_input("Product", value="iPhone 15")
    marketplace = col2.text_input("Marketplace", value="amazon")
    submitted = st.form_submit_button("Run analysis", use_container_width=True)

if submitted:
    with st.spinner("Running the agent pipeline (plan → scrape → sentiment ∥ trend → synthesize)..."):
        try:
            resp = httpx.post(
                f"{API_URL}/analyze",
                json={"product": product, "marketplace": marketplace or None},
                timeout=120,
            )
            resp.raise_for_status()
            report = resp.json()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Request failed: {exc}")
            st.stop()

    if report.get("warnings"):
        st.warning("Partial report — some tools degraded:\n\n" +
                   "\n".join(f"- {w}" for w in report["warnings"]))

    st.subheader("Executive summary")
    st.write(report["summary"])

    m1, m2, m3 = st.columns(3)
    m1.metric("Price", f"{report['price']['price']} {report['price']['currency']}",
              help=f"source: {report['price']['source']}")
    m2.metric("Sentiment (pos/total)",
              f"{report['sentiment']['positive']}/{report['sentiment']['total']}")
    m3.metric("Trend", report["trend"]["direction"],
              f"{report['trend']['price_change_pct']}%")

    st.subheader("Recommendations")
    for rec in report["recommendations"]:
        st.markdown(f"- {rec}")

    left, right = st.columns(2)
    with left:
        st.markdown("**Competitor prices**")
        comp = pd.DataFrame(report["competitors"])
        if not comp.empty:
            st.bar_chart(comp.set_index("name")["price"])
        st.markdown("**Sentiment breakdown**")
        s = report["sentiment"]
        st.bar_chart(pd.DataFrame(
            {"count": [s["positive"], s["neutral"], s["negative"]]},
            index=["positive", "neutral", "negative"],
        ))
    with right:
        st.markdown("**Price history**")
        ph = pd.DataFrame(report["trend"]["price_history"])
        if not ph.empty:
            st.line_chart(ph.set_index("month")["price"])
        st.markdown("**Popularity**")
        pop = pd.DataFrame(report["trend"]["popularity"])
        if not pop.empty:
            st.line_chart(pop.set_index("month")["value"])

    with st.expander("Raw report JSON"):
        st.json(report)
```

- [ ] **Step 2: Manually verify the UI renders** (no automated test — it's a thin API client)

Run (two terminals):
```bash
uvicorn app.api.main:app --port 8000
streamlit run app/ui/streamlit_app.py
```
Expected: submitting "iPhone 15" shows metrics, four charts, recommendations. (Requires a valid `DEEPSEEK_API_KEY`, or the synthesis falls back to a default summary.)

- [ ] **Step 3: Commit**

```bash
git add app/ui/
git commit -m "feat: Streamlit UI client for the analysis API"
```

---

## Task 15: Containerization + deploy config

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `render.yaml`, `.dockerignore`

**Interfaces:** none (infra).

- [ ] **Step 1: Create `.dockerignore`**

```
.git
.venv
__pycache__
.pytest_cache
*.egg-info
.env
docs
sample_reports
```

- [ ] **Step 2: Create `Dockerfile`** (one image, two entrypoints via compose command)

```dockerfile
FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

COPY app ./app

EXPOSE 8000 8501
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  api:
    build: .
    command: uvicorn app.api.main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    environment:
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - DEEPSEEK_BASE_URL=${DEEPSEEK_BASE_URL:-https://api.deepseek.com}
      - DEEPSEEK_MODEL=${DEEPSEEK_MODEL:-deepseek-chat}
      - ENABLE_LIVE_SCRAPE=${ENABLE_LIVE_SCRAPE:-false}

  ui:
    build: .
    command: streamlit run app/ui/streamlit_app.py --server.address 0.0.0.0 --server.port 8501
    ports:
      - "8501:8501"
    environment:
      - API_URL=http://api:8000
    depends_on:
      - api
```

- [ ] **Step 4: Create `render.yaml`** (Render blueprint — two services)

```yaml
services:
  - type: web
    name: market-agent-api
    runtime: docker
    dockerCommand: uvicorn app.api.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DEEPSEEK_API_KEY
        sync: false
      - key: ENABLE_LIVE_SCRAPE
        value: "false"
  - type: web
    name: market-agent-ui
    runtime: docker
    dockerCommand: streamlit run app/ui/streamlit_app.py --server.address 0.0.0.0 --server.port $PORT
    envVars:
      - key: API_URL
        fromService:
          type: web
          name: market-agent-api
          property: host
```

- [ ] **Step 5: Verify compose builds and boots**

Run: `docker compose build`
Expected: both services build with no error. (Full `up` requires a real `DEEPSEEK_API_KEY` in `.env`.)

- [ ] **Step 6: Commit**

```bash
git add Dockerfile docker-compose.yml render.yaml .dockerignore
git commit -m "feat: Docker, docker-compose, and Render deploy config"
```

---

## Task 16: Knowledge layer — ADRs, theory docs, architecture

**Files:**
- Create: `docs/architecture.md`, `docs/decisions/0001..0005*.md`, `docs/theory/04..07*.md`

**Interfaces:** none (docs). Content is prose; write the actual rationale, do not stub.

- [ ] **Step 1: Write the five ADRs** in `docs/decisions/`

Each ADR uses this structure (Context / Decision / Alternatives considered / Consequences). Write real content:
- `0001-langgraph-over-native-and-react.md` — chose LangGraph + **structured graph + LLM planner**; alternatives ReAct (`create_react_agent`) and Supervisor; rationale: determinism, debuggability, demonstrable parallelization, lower LLM cost; consequence: adding a new *decision type* means editing the graph.
- `0002-deepseek-llm.md` — DeepSeek via OpenAI-compatible client; alternative OpenAI/Groq; rationale: cost, requested; consequence: LLM only in plan/synthesize keeps spend bounded.
- `0003-streamlit-ui.md` — Streamlit; alternatives React+FastAPI, server-rendered HTML; rationale: fastest demo, single container; consequence: UI is an API client, not a separate build.
- `0004-scrape-with-mock-fallback.md` — live attempt + deterministic mock fallback; alternative pure-mock or real-only; rationale: real capability without a fragile demo; consequence: `ENABLE_LIVE_SCRAPE` flag, mock is seeded/deterministic.
- `0005-deploy-render-railway.md` — Render/Railway + local compose; alternatives HF Spaces, VPS; rationale: push-to-deploy public URL; consequence: two web services, env-injected key.

- [ ] **Step 2: Write the four theory docs** in `docs/theory/` (answers to brief steps 4–7)

- `04-data-storage.md` — schema for analysis results / request history / cached collected data / agent configs. Recommend: **PostgreSQL** (results + history, JSONB for flexible report bodies), **Redis** (cache with TTL, keyed by product+marketplace hash — mirrors `store.py`), **object storage** (S3) for large raw scrapes, and a queue (see step 6). Include table sketches: `analyses(id, product, marketplace, report jsonb, created_at)`, `analysis_events(...)`, `agent_configs(id, name, prompt_version, params jsonb)`.
- `05-monitoring-observability.md` — tracing with **LangSmith** (native to LangGraph) or OpenTelemetry spans per node; metrics (latency per node, tool success rate, LLM tokens/cost, cache hit rate, error rate); alerting (error-rate + latency thresholds via Prometheus/Alertmanager or hosted); output-quality via LLM-as-judge sampling. Key metrics list.
- `06-scaling-optimization.md` — 100+ concurrent: async workers + a task queue (Celery/RQ or a managed queue) fronting the graph; horizontal API replicas behind a load balancer; **intelligent cache** (semantic/product-key cache, TTL by volatility); LLM cost (cache plan/synthesis, batch, cheaper model routing, prompt compression); parallelize (already fan-out sentiment/trend; parallelize across products via the queue).
- `07-continuous-improvement.md` — LLM-as-judge for automatic quality scoring; prompt A/B via versioned prompts (`agent_configs.prompt_version`) with traffic split + metric comparison; user feedback loop (thumbs + comment stored against `analysis_id`, fed into eval set); capability evolution (add tools behind `BaseTool`, expand the graph, regression eval set).

- [ ] **Step 3: Write `docs/architecture.md`**

Living architecture description: the three layers, the graph diagram, the request lifecycle (UI → API → graph → tools → report → cache), and where each responsibility lives. Cross-link the ADRs and theory docs.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture.md docs/decisions/ docs/theory/
git commit -m "docs: ADRs, theory answers (steps 4-7), and architecture"
```

---

## Task 17: Sample report + README

**Files:**
- Create: `sample_reports/iphone-15.json`, `sample_reports/generate_sample.py`, `README.md`

**Interfaces:** none.

- [ ] **Step 1: Create `sample_reports/generate_sample.py`** (reproducible sample generator)

```python
"""Generate a committed sample report without needing a live LLM.

Run: python sample_reports/generate_sample.py
"""
import json
from unittest.mock import patch

from app.agent import nodes
from app.agent.graph import run_analysis


def _fake(system, user):
    if "normalized_product" in system:
        return {"normalized_product": "iPhone 15", "marketplace": "amazon", "focus": "premium phone"}
    return {
        "summary": "iPhone 15 holds a premium price with strong positive sentiment "
                   "driven by camera and build quality; the price trend is mildly upward.",
        "recommendations": [
            "Maintain premium positioning; sentiment supports the price.",
            "Highlight camera quality in marketing — the top positive theme.",
            "Watch competitor prices; two undercut the listed price.",
        ],
    }


if __name__ == "__main__":
    with patch.object(nodes, "complete_json", _fake):
        report = run_analysis("iPhone 15", "amazon")
    with open("sample_reports/iphone-15.json", "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2)
    print("wrote sample_reports/iphone-15.json")
```

- [ ] **Step 2: Generate the sample**

Run: `python sample_reports/generate_sample.py`
Expected: writes `sample_reports/iphone-15.json` (a valid MarketReport).

- [ ] **Step 3: Write `README.md`** — the primary deliverable. Sections:
  1. **What it is** — one paragraph + the graph diagram.
  2. **Architecture** — three layers; link `docs/architecture.md` and ADRs. Justify LangGraph + structured-graph choice (brief step 1).
  3. **Quickstart (Docker)** — copy `.env.example` → `.env`, add `DEEPSEEK_API_KEY`, `docker compose up`, open `http://localhost:8501` (UI) and `http://localhost:8000/docs` (API).
  4. **Quickstart (local Python)** — `pip install -e ".[dev]"`, run uvicorn + streamlit.
  5. **API examples** — `curl` for `/analyze`, `/analyses/{id}`, `/health`, with sample JSON.
  6. **Running tests** — `pytest -v`.
  7. **Sample report** — link `sample_reports/iphone-15.json`.
  8. **Deployment recommendations** — Render (blueprint via `render.yaml`), Railway (Docker), notes on env vars and the two-service topology; when to use a VPS.
  9. **Design choices** — short table linking each ADR.
  10. **Theory answers (steps 4–7)** — short summaries, each linking its `docs/theory/*.md`.
  11. **Project structure** — the tree.

- [ ] **Step 4: Run the full suite one final time**

Run: `pytest -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add sample_reports/ README.md
git commit -m "docs: README, deployment guide, and sample report"
```

---

## Self-Review Notes (for the plan author)

- **Spec coverage:** framework/orchestration (T10–12), 4 tools ≥3 required (T5–8), REST API (T13), Docker (T15), tests incl. tool/orchestration/error/output-validation (T3,5–8,11–13), UI (T14), knowledge layer/ADRs/theory (T16), sample report + README (T17), deploy Render/Railway (T15,17). All spec sections mapped.
- **Type consistency:** `MarketReport` shape identical across T2/T8/T12/T13; `ToolResult`/`BaseTool.run` used uniformly; `complete_json` patched at `app.agent.nodes.complete_json` in every test that needs it; `run_analysis(product, marketplace)` signature stable.
- **LLM isolation:** LLM only in `plan_node`/`synthesize_node`; all tests monkeypatch `complete_json` — no test hits the network.
- **Parallelism:** `scrape→sentiment`, `scrape→trend`, `sentiment→synthesize`, `trend→synthesize` gives fan-out/fan-in; `errors` uses `operator.add` reducer so concurrent appends merge.
