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
