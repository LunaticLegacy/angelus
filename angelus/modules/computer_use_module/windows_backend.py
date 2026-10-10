"""Windows desktop implementation using Pillow and user32."""
from __future__ import annotations

import ctypes
import io
from PIL import ImageGrab

from .backend import ComputerUseUnavailable, ScreenCapture


class WindowsComputerBackend:
    _BUTTON_FLAGS = {
        "left": (0x0002, 0x0004),
        "right": (0x0008, 0x0010),
        "middle": (0x0020, 0x0040),
    }
    _KEYS = {
        "ENTER": 0x0D, "ESC": 0x1B, "ESCAPE": 0x1B, "TAB": 0x09,
        "BACKSPACE": 0x08, "SPACE": 0x20, "UP": 0x26, "DOWN": 0x28,
        "LEFT": 0x25, "RIGHT": 0x27, "HOME": 0x24, "END": 0x23,
        "PAGEUP": 0x21, "PAGEDOWN": 0x22, "DELETE": 0x2E,
        "CTRL": 0x11, "SHIFT": 0x10, "ALT": 0x12,
    }

    def __init__(self) -> None:
        if not hasattr(ctypes, "windll"):
            raise ComputerUseUnavailable("Windows user32 is unavailable")
        self._user32 = ctypes.windll.user32

    def screenshot(self) -> ScreenCapture:
        try:
            image = ImageGrab.grab(all_screens=True)
        except Exception as exc:  # pragma: no cover - depends on desktop session
            raise ComputerUseUnavailable(f"Unable to capture the desktop: {exc}") from exc
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        return ScreenCapture(output.getvalue(), image.width, image.height)

    def screen_size(self) -> tuple[int, int]:
        return int(self._user32.GetSystemMetrics(78)), int(self._user32.GetSystemMetrics(79))

    def _move(self, x: int, y: int) -> None:
        if not self._user32.SetCursorPos(int(x), int(y)):
            raise ComputerUseUnavailable("Unable to move the mouse cursor")

    def click(self, x: int, y: int, button: str = "left") -> None:
        try:
            down, up = self._BUTTON_FLAGS[button.lower()]
        except KeyError as exc:
            raise ValueError("button must be left, right, or middle") from exc
        self._move(x, y)
        self._user32.mouse_event(down, 0, 0, 0, 0)
        self._user32.mouse_event(up, 0, 0, 0, 0)

    def double_click(self, x: int, y: int, button: str = "left") -> None:
        self.click(x, y, button)
        self.click(x, y, button)

    def type_text(self, text: str) -> None:
        if not isinstance(text, str) or not text:
            raise ValueError("text must be a non-empty string")
        for char in text:
            self._unicode_key(char, key_up=False)
            self._unicode_key(char, key_up=True)

    def _unicode_key(self, char: str, *, key_up: bool) -> None:
        # keybd_event handles Unicode input without requiring a clipboard.
        flags = 0x0004 | (0x0002 if key_up else 0)
        self._user32.keybd_event(0, ord(char), flags, 0)

    def press_key(self, key: str) -> None:
        normalized = key.upper().replace(" ", "")
        vk = self._KEYS.get(normalized)
        if vk is None and len(normalized) == 1:
            vk = ord(normalized)
        if vk is None:
            if normalized.startswith("F") and normalized[1:].isdigit() and 1 <= int(normalized[1:]) <= 24:
                vk = 0x70 + int(normalized[1:]) - 1
            else:
                raise ValueError(f"unsupported key: {key}")
        self._user32.keybd_event(vk, 0, 0, 0)
        self._user32.keybd_event(vk, 0, 0x0002, 0)

    def scroll(self, dx: int = 0, dy: int = 0) -> None:
        if dx:
            self._user32.mouse_event(0x01000, 0, 0, int(dx), 0)
        if dy:
            self._user32.mouse_event(0x0800, 0, 0, int(dy), 0)
