from app.core.config import get_settings
from app.core.errors import ToolError


def test_settings_have_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    s = get_settings()
    assert s.deepseek_api_key == "test-key"
    assert s.deepseek_base_url == "https://api.deepseek.com"
    assert s.deepseek_model == "deepseek-chat"
    assert s.enable_live_scrape is False


def test_tool_error_carries_tool_name():
    err = ToolError("web_scraper", "boom")
    assert err.tool == "web_scraper"
    assert "boom" in str(err)
