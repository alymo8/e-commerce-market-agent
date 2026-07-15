import hashlib
import random
from datetime import date

_POSITIVE = [
    "Amazing build quality, worth every penny.",
    "The camera is fantastic and battery lasts all day.",
    "Fast shipping and works exactly as described.",
    "Best purchase this year, highly recommend.",
    "Great value, the design feels premium.",
]
_NEGATIVE = [
    "Too expensive for what you get.",
    "Stopped working after two weeks, disappointed.",
    "Customer support was slow and unhelpful.",
]
_NEUTRAL = [
    "It is okay, does the job but nothing special.",
    "Average product, matches the description.",
]
_COMPETITOR_NAMES = ["BestBuy", "Walmart", "eBay", "Newegg", "Target"]


def seeded_rng(product: str) -> random.Random:
    digest = hashlib.sha256(product.lower().encode()).hexdigest()
    return random.Random(int(digest[:8], 16))


def mock_price(product: str) -> tuple[float, str]:
    rng = seeded_rng(product)
    return round(rng.uniform(20, 1200), 2), "USD"


def mock_competitors(product: str) -> list[dict]:
    rng = seeded_rng(product)
    base, _ = mock_price(product)
    names = rng.sample(_COMPETITOR_NAMES, k=3)
    return [
        {"name": n, "price": round(base * rng.uniform(0.9, 1.1), 2)} for n in names
    ]


def mock_reviews(product: str) -> list[str]:
    rng = seeded_rng(product)
    reviews = _POSITIVE * 2 + _NEGATIVE + _NEUTRAL
    rng.shuffle(reviews)
    return reviews


def mock_series(product: str, months: int = 6) -> tuple[list[dict], list[dict]]:
    rng = seeded_rng(product)
    base, _ = mock_price(product)
    today = date.today()
    prices, popularity = [], []
    price = base
    pop = rng.uniform(40, 90)
    for i in range(months, 0, -1):
        # Month-index computation relies on Python floor-division/modulo for negative operands to roll back across year boundaries
        m = (today.month - i - 1) % 12 + 1
        y = today.year + ((today.month - i - 1) // 12)
        label = f"{y:04d}-{m:02d}"
        price = round(price * rng.uniform(0.97, 1.03), 2)
        pop = round(min(100, max(0, pop + rng.uniform(-8, 8))), 1)
        prices.append({"month": label, "price": price})
        popularity.append({"month": label, "value": pop})
    return prices, popularity
