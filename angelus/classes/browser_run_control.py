import queue
import threading

from llmfetcher.agent import AgentRunControl


class BrowserRunControl(AgentRunControl):
    """Thread-safe browser controls with cooperative and terminal stop modes.

    ``stop()`` is observed only at Agent safe boundaries.  ``force_stop()``
    additionally exposes ``force_stopped`` so the current model request can
    close its provider transport and the browser worker can end immediately.
    """

    def __init__(self) -> None:
        self._stopped = threading.Event()
        self._force_stopped = threading.Event()
        self._steers: queue.Queue[str] = queue.Queue()

    def should_stop(self) -> bool:
        return self._stopped.is_set()

    def drain_steers(self) -> list[str]:
        messages: list[str] = []
        while True:
            try:
                messages.append(self._steers.get_nowait())
            except queue.Empty:
                return messages

    def stop(self) -> None:
        self._stopped.set()

    def force_stop(self) -> None:
        self._force_stopped.set()
        self._stopped.set()

    @property
    def force_stopped(self) -> threading.Event:
        return self._force_stopped

    def steer(self, message: str) -> None:
        self._steers.put(message)
