import time
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger("tools")


class ToolResult(BaseModel):
    tool: str
    ok: bool
    data: dict | None = None
    error: str | None = None
    duration_ms: float


class BaseTool(ABC):
    name: str = "base"

    @abstractmethod
    def _execute(self, **kwargs) -> dict:
        """Do the work. Raise on failure; the base class captures it."""

    def run(self, **kwargs) -> ToolResult:
        start = time.perf_counter()
        try:
            data = self._execute(**kwargs)
            duration = (time.perf_counter() - start) * 1000
            logger.info("tool=%s ok duration_ms=%.1f", self.name, duration)
            return ToolResult(tool=self.name, ok=True, data=data, duration_ms=duration)
        except Exception as exc:  # noqa: BLE001 - tools must never crash the graph
            duration = (time.perf_counter() - start) * 1000
            logger.warning("tool=%s failed: %s", self.name, exc)
            return ToolResult(
                tool=self.name, ok=False, error=str(exc), duration_ms=duration
            )
