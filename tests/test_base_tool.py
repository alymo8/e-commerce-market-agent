from app.tools.base import BaseTool, ToolResult


class OkTool(BaseTool):
    name = "ok_tool"

    def _execute(self, **kwargs) -> dict:
        return {"value": kwargs["x"] * 2}


class BoomTool(BaseTool):
    name = "boom_tool"

    def _execute(self, **kwargs) -> dict:
        raise ValueError("kaboom")


def test_run_returns_ok_result_with_timing():
    result = OkTool().run(x=21)
    assert isinstance(result, ToolResult)
    assert result.ok is True
    assert result.data == {"value": 42}
    assert result.duration_ms >= 0


def test_run_captures_exception_as_failed_result():
    result = BoomTool().run()
    assert result.ok is False
    assert result.data is None
    assert "kaboom" in result.error
    assert result.tool == "boom_tool"
