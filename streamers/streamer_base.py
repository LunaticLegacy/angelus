from __future__ import annotations

import sys
from abc import ABC, abstractmethod

GRAY = "\033[90m"
WHITE = "\033[97m"
CYAN = "\033[96m"
RESET = "\033[0m"


class Streamer(ABC):
    START = "<think>"
    END = "</think>"
    TOOL_START = "<tool_call>"
    TOOL_END = "</tool_call>"

    def __init__(self) -> None:
        self.mode = "text"
        self.buffer = ""
        self.token_counter: int = 0

    @abstractmethod
    def __call__(self, msg: str) -> bool:
        self.feed(msg)
        return False

    def feed(self, msg: str) -> None:
        self.buffer += msg

        while self.buffer:
            if self.mode == "think":
                marker = self.END
                idx = self.buffer.find(marker)
                if idx != -1:
                    self._emit(self.buffer[:idx])
                    self.buffer = self.buffer[idx + len(marker):]
                    self.mode = "text"
                    continue
                keep = self._possible_marker_prefix_len(self.buffer, marker)
            elif self.mode == "tool":
                marker = self.TOOL_END
                idx = self.buffer.find(marker)
                if idx != -1:
                    self._emit(self.buffer[:idx])
                    self.buffer = self.buffer[idx + len(marker):]
                    self.mode = "text"
                    continue
                keep = self._possible_marker_prefix_len(self.buffer, marker)
            else:
                think_idx = self.buffer.find(self.START)
                tool_idx = self.buffer.find(self.TOOL_START)
                next_marker = None

                if think_idx != -1 and (tool_idx == -1 or think_idx < tool_idx):
                    idx = think_idx
                    next_marker = self.START
                    next_mode = "think"
                elif tool_idx != -1:
                    idx = tool_idx
                    next_marker = self.TOOL_START
                    next_mode = "tool"
                else:
                    idx = -1
                    next_mode = "text"

                if idx != -1:
                    self._emit(self.buffer[:idx])
                    self.buffer = self.buffer[idx + len(next_marker):]
                    self.mode = next_mode
                    continue

                keep = self._possible_marker_prefix_len(self.buffer, self.START, self.TOOL_START)
            if keep == len(self.buffer):
                return

            emit_text = self.buffer[:-keep] if keep > 0 else self.buffer
            self.buffer = self.buffer[-keep:] if keep > 0 else ""
            self._emit(emit_text)

    def finish(self) -> None:
        if self.buffer:
            self.token_counter += 1
            self._emit(self.buffer)
            self.buffer = ""

        sys.stdout.write(RESET + "\n")
        sys.stdout.flush()

    def _emit(self, text: str) -> None:
        self.token_counter += 1

        if not text:
            return

        if self.mode == "think":
            color = GRAY
        elif self.mode == "tool":
            color = CYAN
        else:
            color = WHITE
        sys.stdout.write(color + text + RESET)
        sys.stdout.flush()

    @staticmethod
    def _possible_marker_prefix_len(text: str, *markers: str) -> int:
        keep = 0
        for marker in markers:
            max_len = min(len(text), len(marker) - 1)
            for n in range(max_len, 0, -1):
                if marker.startswith(text[-n:]):
                    keep = max(keep, n)
                    break
        return keep

    def get_tokens(self) -> int:
        return self.token_counter
