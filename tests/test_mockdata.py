import datetime as _dt

from app.tools import mockdata


def test_price_is_deterministic():
    assert mockdata.mock_price("iPhone 15") == mockdata.mock_price("iPhone 15")


def test_different_products_differ():
    assert mockdata.mock_price("iPhone 15") != mockdata.mock_price("Nike Air Max")


def test_reviews_and_series_shape():
    reviews = mockdata.mock_reviews("iPhone 15")
    assert len(reviews) >= 8
    prices, popularity = mockdata.mock_series("iPhone 15", months=6)
    assert len(prices) == 6 and len(popularity) == 6
    assert set(prices[0]) == {"month", "price"}


def test_mock_series_labels_cross_year_boundary(monkeypatch):
    class _FixedDate(_dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 1, 15)  # January -> months must roll back into 2025

    monkeypatch.setattr(mockdata, "date", _FixedDate)
    prices, popularity = mockdata.mock_series("iPhone 15", months=6)
    labels = [p["month"] for p in prices]
    assert labels == ["2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12"]
    assert [p["month"] for p in popularity] == labels
    assert labels == sorted(labels)  # monotonic non-decreasing
