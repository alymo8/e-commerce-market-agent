from app.agent.state import AgentState
from app.agent import prompts


def test_state_keys_present():
    keys = AgentState.__annotations__
    for k in ["run_id", "product", "marketplace", "plan", "scrape",
              "sentiment", "trend", "synthesis", "report", "errors"]:
        assert k in keys


def test_prompts_nonempty():
    assert "JSON" in prompts.PLAN_SYSTEM
    assert "JSON" in prompts.SYNTHESIS_SYSTEM
