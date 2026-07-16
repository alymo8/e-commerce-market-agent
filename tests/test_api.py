from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_root_returns_service_info():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["health"] == "/health"
    assert body["docs"] == "/docs"


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


def test_cache_hit_reuses_id_and_does_not_resave(fake_llm):
    from app.api import store

    # Clear any cache entry left by other tests so this test's first call is
    # deterministically a MISS regardless of test execution order (fake_llm
    # always normalizes to product="iPhone 15", marketplace="amazon").
    store._CACHE.clear()
    store._BY_ID.clear()

    payload = {"product": "iPhone 15", "marketplace": "amazon"}
    first = client.post("/analyze", json=payload)
    assert first.status_code == 200
    assert first.headers["X-Cache"] == "MISS"
    first_id = first.headers["X-Analysis-Id"]

    second = client.post("/analyze", json=payload)
    assert second.status_code == 200
    assert second.headers["X-Cache"] == "HIT"
    assert second.headers["X-Analysis-Id"] == first_id


def test_unknown_analysis_returns_404():
    assert client.get("/analyses/does-not-exist").status_code == 404


def test_cache_key_no_delimiter_collision():
    from app.api import store
    assert store._key("a::", "b") != store._key("a", "::b")
