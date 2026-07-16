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
