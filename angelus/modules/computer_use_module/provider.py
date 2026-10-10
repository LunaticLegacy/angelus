"""Agent-facing composite ``computer`` tool."""
from __future__ import annotations

from typing import TYPE_CHECKING

from llmfetcher import Tool
from llmfetcher.llm_types import ToolParameter, ToolSchema
from llmfetcher.multimodal import ImageToolResult

from ..tool_module import ToolPolicy
from .backend import ComputerBackend, backend_for_host

if TYPE_CHECKING:
    from ...core import AngelusCore
    from ..session_module import Session


class ComputerUseProvider:
    def __init__(self, core: "AngelusCore", backend: ComputerBackend | None = None) -> None:
        self._core = core
        self._backend = backend

    def materialize(self, session: "Session", policy: ToolPolicy, role: str,
                    agent_name: str | None = None) -> list[Tool]:
        if role not in {"coordinator", "worker"} or not policy.allows("vision", "computer"):
            return []
        if session.attachments is None or session.execution is None:
            return []
        backend = self._backend or backend_for_host()
        store = session.attachments

        def computer(action: str = "screenshot", x: int = 0, y: int = 0,
                     text: str = "", key: str = "", button: str = "left",
                     dx: int = 0, dy: int = 0) -> ImageToolResult | str:
            action = action.lower().strip()
            if action in {"click", "double_click"}:
                self._validate_point(backend, x, y)
                (backend.click if action == "click" else backend.double_click)(x, y, button)
                return f"{action} completed at ({x}, {y})"
            if action == "type":
                backend.type_text(text)
                return "text input completed"
            if action == "key":
                backend.press_key(key)
                return f"key press completed: {key}"
            if action == "scroll":
                if not dx and not dy:
                    raise ValueError("scroll requires dx or dy")
                backend.scroll(dx, dy)
                return "scroll completed"
            if action == "screenshot":
                capture = backend.screenshot()
                metadata = store.put(capture.png_bytes, filename="computer-screenshot.png")
                ref = {"attachment_id": metadata["attachment_id"],
                       "media_type": metadata["media_type"], "detail": "auto"}
                return ImageToolResult(
                    text=f"Desktop screenshot {metadata['attachment_id']} "
                         f"({capture.width}x{capture.height}).",
                    images=[ref],
                )
            raise ValueError("action must be screenshot, click, double_click, type, key, or scroll")

        return [Tool(
            "computer",
            "Control the desktop through screenshots, mouse clicks, keyboard input, and scrolling.",
            ToolSchema(properties=[
                ToolParameter("action", description="Operation to perform", enum=["screenshot", "click", "double_click", "type", "key", "scroll"], default="screenshot", required=False),
                ToolParameter("x", type="integer", description="Screen x coordinate", required=False, default=0),
                ToolParameter("y", type="integer", description="Screen y coordinate", required=False, default=0),
                ToolParameter("text", description="Text to type", required=False, default=""),
                ToolParameter("key", description="Named key such as ENTER or CTRL", required=False, default=""),
                ToolParameter("button", description="Mouse button", enum=["left", "right", "middle"], required=False, default="left"),
                ToolParameter("dx", type="integer", description="Horizontal scroll amount", required=False, default=0),
                ToolParameter("dy", type="integer", description="Vertical scroll amount", required=False, default=0),
            ]), computer,
        )]

    @staticmethod
    def _validate_point(backend: ComputerBackend, x: int, y: int) -> None:
        if not isinstance(x, int) or not isinstance(y, int):
            raise ValueError("x and y must be integers")
        width, height = backend.screen_size()
        if x < 0 or y < 0 or x >= width or y >= height:
            raise ValueError(f"point ({x}, {y}) is outside the {width}x{height} screen")
