import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict):
    run_id: str
    product: str
    marketplace: str | None
    plan: dict | None
    scrape: dict | None
    sentiment: dict | None
    trend: dict | None
    synthesis: dict | None
    report: dict | None
    errors: Annotated[list[dict], operator.add]
