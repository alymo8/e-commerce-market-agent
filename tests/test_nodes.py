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


def test_synthesize_node_falls_back_on_malformed_shape(monkeypatch):
    monkeypatch.setattr(
        nodes, "complete_json",
        lambda system, user: {"summary": "ok", "recommendations": "not-a-list"},
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
    assert "synthesis" in update
    assert isinstance(update["synthesis"]["recommendations"], list)
    assert update["errors"]  # error recorded


def test_plan_node_preserves_marketplace_when_plan_returns_none(monkeypatch):
    monkeypatch.setattr(
        nodes, "complete_json",
        lambda system, user: {"normalized_product": "iPhone 15", "marketplace": None, "focus": ""},
    )
    update = nodes.plan_node({"product": "iPhone 15", "marketplace": "amazon", "errors": []})
    assert update["marketplace"] == "amazon"


def test_plan_node_preserves_marketplace_when_plan_returns_null_string(monkeypatch):
    monkeypatch.setattr(
        nodes, "complete_json",
        lambda system, user: {"normalized_product": "iPhone 15", "marketplace": "null", "focus": ""},
    )
    update = nodes.plan_node({"product": "iPhone 15", "marketplace": "amazon", "errors": []})
    assert update["marketplace"] == "amazon"


def test_plan_node_uses_plan_marketplace_when_present(monkeypatch):
    monkeypatch.setattr(
        nodes, "complete_json",
        lambda system, user: {"normalized_product": "iPhone 15", "marketplace": "ebay", "focus": ""},
    )
    update = nodes.plan_node({"product": "iPhone 15", "marketplace": "amazon", "errors": []})
    assert update["marketplace"] == "ebay"
