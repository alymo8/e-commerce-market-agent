from app.tools.base import BaseTool
from app.tools.mockdata import mock_reviews

_POSITIVE_WORDS = ("amazing", "best", "fantastic", "fast", "great", "premium", "recommend", "worth")
_NEGATIVE_WORDS = ("disappointed", "expensive", "slow", "stopped", "too", "unhelpful")


def _classify(review: str) -> str:
    text = review.lower()
    pos = sum(w in text for w in _POSITIVE_WORDS)
    neg = sum(w in text for w in _NEGATIVE_WORDS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _themes(reviews: list[str], words: tuple[str, ...]) -> list[str]:
    hits = [w for r in reviews for w in words if w in r.lower()]
    seen = []
    for w in hits:
        if w not in seen:
            seen.append(w)
    return seen[:3]


class SentimentAnalyzerTool(BaseTool):
    """Classify a mock review corpus with deterministic keyword rules."""

    name = "sentiment_analyzer"

    def _execute(self, product: str) -> dict:
        reviews = mock_reviews(product)
        labels = [_classify(r) for r in reviews]
        pos = labels.count("positive")
        neg = labels.count("negative")
        neu = labels.count("neutral")
        return {
            "positive": pos,
            "neutral": neu,
            "negative": neg,
            "total": len(reviews),
            "top_positive_themes": _themes(reviews, _POSITIVE_WORDS),
            "top_negative_themes": _themes(reviews, _NEGATIVE_WORDS),
            "sample_reviews": reviews[:3],
        }
