import uuid

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    plan_node,
    report_node,
    scrape_node,
    sentiment_node,
    synthesize_node,
    trend_node,
)
from app.agent.state import AgentState
from app.core.report import MarketReport


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("plan", plan_node)
    g.add_node("scrape", scrape_node)
    g.add_node("sentiment", sentiment_node)
    g.add_node("trend", trend_node)
    g.add_node("synthesize", synthesize_node)
    g.add_node("report", report_node)

    g.add_edge(START, "plan")
    g.add_edge("plan", "scrape")
    # fan-out: sentiment and trend run in parallel after scrape
    g.add_edge("scrape", "sentiment")
    g.add_edge("scrape", "trend")
    # fan-in: synthesize waits for BOTH analysis nodes
    g.add_edge("sentiment", "synthesize")
    g.add_edge("trend", "synthesize")
    g.add_edge("synthesize", "report")
    g.add_edge("report", END)
    return g.compile()


_GRAPH = build_graph()


def run_analysis(product: str, marketplace: str | None = None) -> MarketReport:
    initial: AgentState = {
        "run_id": str(uuid.uuid4()),
        "product": product,
        "marketplace": marketplace,
        "plan": None, "scrape": None, "sentiment": None, "trend": None,
        "synthesis": None, "report": None, "errors": [],
    }
    final = _GRAPH.invoke(initial)
    return MarketReport.model_validate(final["report"])
