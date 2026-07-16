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
