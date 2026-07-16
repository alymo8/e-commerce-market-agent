from app.tools.trend_analyzer import TrendAnalyzerTool


def test_trend_structure_and_direction():
    result = TrendAnalyzerTool().run(product="iPhone 15", months=6)
    d = result.data
    assert result.ok is True
    assert len(d["price_history"]) == 6
    assert len(d["popularity"]) == 6
    assert d["direction"] in {"up", "down", "stable"}
    assert isinstance(d["price_change_pct"], float)
