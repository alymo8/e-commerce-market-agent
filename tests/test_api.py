from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_analyze_returns_report_and_is_retrievable(fake_llm):
    resp = client.post("/analyze", json={"product": "iPhone 15", "marketplace": "amazon"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["product"]
    assert body["price"]["currency"] == "USD"
    analysis_id = resp.headers["X-Analysis-Id"]
    got = client.get(f"/analyses/{analysis_id}")
    assert got.status_code == 200
    assert got.json()["product"] == body["product"]


def test_unknown_analysis_returns_404():
    assert client.get("/analyses/does-not-exist").status_code == 404
