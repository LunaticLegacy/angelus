"""The durable locations associated with one logical session."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    """Bind one session identity to its user project and Angelus state paths.

    ``project_path`` belongs to the user and is never deleted by this object.
    ``state_path`` is Angelus-owned durable state, containing execution
    journals, checkpoints, and future projections for this session.
    """

    session_id: str
    name: str
    project_path: Path | None
    state_path: Path
