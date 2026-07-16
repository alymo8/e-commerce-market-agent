from pydantic import BaseModel, Field


class PriceInfo(BaseModel):
    price: float
    currency: str
    source: str  # "live" | "mock"


class Competitor(BaseModel):
    name: str
    price: float


class SentimentBreakdown(BaseModel):
    positive: int
    neutral: int
    negative: int
    total: int
    top_positive_themes: list[str]
    top_negative_themes: list[str]


class TrendPoint(BaseModel):
    month: str
    price: float


class PopularityPoint(BaseModel):
    month: str
    value: float


class TrendInfo(BaseModel):
    direction: str  # "up" | "down" | "stable"
    price_change_pct: float
    price_history: list[TrendPoint]
    popularity: list[PopularityPoint]


class MarketReport(BaseModel):
    product: str
    marketplace: str | None = None
    price: PriceInfo
    competitors: list[Competitor]
    sentiment: SentimentBreakdown
    trend: TrendInfo
    summary: str
    recommendations: list[str]
    warnings: list[str] = Field(default_factory=list)
    generated_at: str
