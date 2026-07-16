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
