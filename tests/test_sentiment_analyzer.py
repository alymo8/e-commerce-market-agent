from app.tools.sentiment_analyzer import SentimentAnalyzerTool


def test_sentiment_counts_sum_to_total():
    result = SentimentAnalyzerTool().run(product="iPhone 15")
    d = result.data
    assert result.ok is True
    assert d["positive"] + d["neutral"] + d["negative"] == d["total"]
    assert d["total"] >= 8
    assert isinstance(d["top_positive_themes"], list)
    assert len(d["sample_reviews"]) >= 1
