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
