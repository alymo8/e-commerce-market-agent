from app.agent.graph import run_analysis
from app.core.report import MarketReport


def test_full_pipeline_produces_valid_report(fake_llm):
    report = run_analysis("iPhone 15", "amazon")
    assert isinstance(report, MarketReport)
    assert report.product
    assert report.price.currency == "USD"
    assert report.sentiment.total >= 8
    assert len(report.trend.price_history) == 6
    assert report.summary == "Executive summary."
    assert len(report.recommendations) == 2
    assert report.warnings == []


def test_pipeline_degrades_when_a_tool_fails(fake_llm, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("scraper exploded")
    monkeypatch.setattr("app.agent.nodes._scraper._execute", boom)
    report = run_analysis("iPhone 15", "amazon")
    assert isinstance(report, MarketReport)          # still returns a report
    assert any("web_scraper" in w for w in report.warnings)  # failure surfaced


def test_pipeline_returns_minimal_report_when_report_generator_fails(fake_llm, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("boom")
    monkeypatch.setattr("app.agent.nodes._report._execute", boom)
    report = run_analysis("iPhone 15", "amazon")
    assert isinstance(report, MarketReport)          # never crashes, no HTTP 500
    assert any("report_generator" in w for w in report.warnings)
