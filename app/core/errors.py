class ToolError(Exception):
    """Raised inside a tool's _execute; carries the tool name for tracing."""

    def __init__(self, tool: str, message: str) -> None:
        self.tool = tool
        self.message = message
        super().__init__(f"[{tool}] {message}")
