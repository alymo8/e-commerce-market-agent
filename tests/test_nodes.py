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
