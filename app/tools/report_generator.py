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
