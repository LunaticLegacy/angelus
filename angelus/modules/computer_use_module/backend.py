"""Small platform boundary for screenshots and input events."""
from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Protocol


class ComputerUseUnavailable(RuntimeError):
    """Raised when the host cannot provide desktop interaction."""


@dataclass(frozen=True)
class ScreenCapture:
    png_bytes: bytes
    width: int
    height: int
    scale: float = 1.0


class ComputerBackend(Protocol):
    def screenshot(self) -> ScreenCapture: ...
    def screen_size(self) -> tuple[int, int]: ...
    def click(self, x: int, y: int, button: str = "left") -> None: ...
    def double_click(self, x: int, y: int, button: str = "left") -> None: ...
    def type_text(self, text: str) -> None: ...
    def press_key(self, key: str) -> None: ...
    def scroll(self, dx: int = 0, dy: int = 0) -> None: ...


def backend_for_host() -> ComputerBackend:
    if sys.platform == "win32":
        from .windows_backend import WindowsComputerBackend

        return WindowsComputerBackend()
    return _UnavailableBackend()


class _UnavailableBackend:
    def _raise(self) -> None:
        raise ComputerUseUnavailable("Computer Use is currently implemented for Windows only")

    screenshot = screen_size = click = double_click = type_text = press_key = scroll = _raise
