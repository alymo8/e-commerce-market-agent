from app.agent.prompts import PLAN_SYSTEM, SYNTHESIS_SYSTEM
from app.core.logging import get_logger
from app.llm.deepseek import complete_json
from app.tools.report_generator import ReportGeneratorTool
from app.tools.sentiment_analyzer import SentimentAnalyzerTool
from app.tools.trend_analyzer import TrendAnalyzerTool
from app.tools.web_scraper import WebScraperTool

logger = get_logger("agent.nodes")

_scraper = WebScraperTool()
_sentiment = SentimentAnalyzerTool()
_trend = TrendAnalyzerTool()
_report = ReportGeneratorTool()


def _err(tool: str, message: str) -> dict:
    return {"tool": tool, "error": message}


def plan_node(state: dict) -> dict:
    product = state["product"]
    marketplace = state.get("marketplace")
    try:
        plan = complete_json(PLAN_SYSTEM, f"Product: {product}\nMarketplace: {marketplace}")
    except Exception as exc:  # noqa: BLE001 - planning is best-effort
        logger.warning("plan failed: %s", exc)
        plan = {"normalized_product": product, "marketplace": marketplace, "focus": ""}
        return {"plan": plan, "product": product, "marketplace": marketplace,
                "errors": [_err("planner", str(exc))]}
    plan_marketplace = plan.get("marketplace")
    resolved_marketplace = plan_marketplace if plan_marketplace not in (None, "null", "") else marketplace
    return {
        "plan": plan,
        "product": plan.get("normalized_product") or product,
        "marketplace": resolved_marketplace,
    }


def scrape_node(state: dict) -> dict:
    result = _scraper.run(product=state["product"], marketplace=state.get("marketplace"))
    if result.ok:
        return {"scrape": result.data}
    fallback = {"price": 0.0, "currency": "USD", "source": "mock", "competitors": []}
    return {"scrape": fallback, "errors": [_err("web_scraper", result.error)]}


def sentiment_node(state: dict) -> dict:
    result = _sentiment.run(product=state["product"])
    if result.ok:
        return {"sentiment": result.data}
    fallback = {"positive": 0, "neutral": 0, "negative": 0, "total": 0,
                "top_positive_themes": [], "top_negative_themes": []}
    return {"sentiment": fallback, "errors": [_err("sentiment_analyzer", result.error)]}


def trend_node(state: dict) -> dict:
    result = _trend.run(product=state["product"])
    if result.ok:
        return {"trend": result.data}
    fallback = {"direction": "stable", "price_change_pct": 0.0,
                "price_history": [], "popularity": []}
    return {"trend": fallback, "errors": [_err("trend_analyzer", result.error)]}


def synthesize_node(state: dict) -> dict:
    user = (
        f"Product: {state['product']}\n"
        f"Price data: {state['scrape']}\n"
        f"Sentiment: {state['sentiment']}\n"
        f"Trend: {state['trend']}"
    )
    try:
        synthesis = complete_json(SYNTHESIS_SYSTEM, user)
        if "summary" not in synthesis or "recommendations" not in synthesis:
            raise ValueError("synthesis missing required keys")
        return {"synthesis": synthesis}
    except Exception as exc:  # noqa: BLE001 - degrade to a safe default summary
        logger.warning("synthesis failed: %s", exc)
        fallback = {
            "summary": f"Automated analysis for {state['product']} "
                       "(LLM synthesis unavailable; showing collected data).",
            "recommendations": ["Review collected price, sentiment, and trend data manually."],
        }
        return {"synthesis": fallback, "errors": [_err("synthesizer", str(exc))]}


def report_node(state: dict) -> dict:
    warnings = [f"{e['tool']}: {e['error']}" for e in state.get("errors", [])]
    result = _report.run(
        product=state["product"],
        marketplace=state.get("marketplace"),
        scrape=state["scrape"],
        sentiment=state["sentiment"],
        trend=state["trend"],
        synthesis=state["synthesis"],
        warnings=warnings,
    )
    if result.ok:
        return {"report": result.data}
    return {"report": None, "errors": [_err("report_generator", result.error)]}
