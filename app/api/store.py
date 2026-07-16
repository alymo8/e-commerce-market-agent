import time
import uuid

from app.core.config import get_settings
from app.core.report import MarketReport

_BY_ID: dict[str, MarketReport] = {}
_CACHE: dict[tuple[str, str], tuple[float, str]] = {}  # key -> (expires_at, analysis_id)

# In-memory demo store: not evicted, not synchronized, and per-process only
# (not safe across multiple uvicorn workers). Production persistence is covered
# as a design/theory answer, not implemented here.


def _key(product: str, marketplace: str | None) -> tuple[str, str]:
    return (product.lower().strip(), (marketplace or "").lower().strip())


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


def get_cached_with_id(product: str, marketplace: str | None) -> tuple[MarketReport, str] | None:
    entry = _CACHE.get(_key(product, marketplace))
    if not entry:
        return None
    expires_at, analysis_id = entry
    if time.time() > expires_at:
        return None
    report = _BY_ID.get(analysis_id)
    if report is None:
        return None
    return report, analysis_id
