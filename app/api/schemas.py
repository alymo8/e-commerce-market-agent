from pydantic import BaseModel, Field

from app.core.report import MarketReport

AnalyzeResponse = MarketReport


class AnalyzeRequest(BaseModel):
    product: str = Field(min_length=1, examples=["iPhone 15"])
    marketplace: str | None = Field(default=None, examples=["amazon"])
