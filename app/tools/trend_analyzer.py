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
