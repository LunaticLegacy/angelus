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

    def reset(self) -> None:
        """Clear terminal controls before the same session begins another run.

        This method is valid only after the prior run reached its terminal
        boundary. Keeping the control object itself stable lets persistent
        Swarm tool handlers retain their force-stop event reference across
        browser turns.

        Side Effects:
            Clears cooperative/force-stop flags and discards unapplied steer
            messages from the completed run.
        """
        self._stopped.clear()
        self._force_stopped.clear()
        while True:
            try:
                self._steers.get_nowait()
            except queue.Empty:
                return

    @property
    def force_stopped(self) -> threading.Event:
        return self._force_stopped

    def steer(self, message: str) -> None:
        self._steers.put(message)
