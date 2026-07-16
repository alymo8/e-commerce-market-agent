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
