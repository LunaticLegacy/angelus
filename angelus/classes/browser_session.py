from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .active_run import ActiveRun


@dataclass
class BrowserSession:
    """In-memory state that prevents concurrent runs in the same chat."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    active: ActiveRun | None = None
