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

    def to_json(self) -> dict[str, str | None]:
        """Return the stable registry representation without runtime state."""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "project_path": str(self.project_path) if self.project_path is not None else None,
            "state_path": str(self.state_path),
        }

    @classmethod
    def from_json(cls, value: dict[str, object]) -> "Workspace":
        """Recreate a workspace record previously written by the catalog."""
        return cls(
            session_id=str(value["session_id"]),
            name=str(value["name"]),
            project_path=(
                Path(str(value["project_path"]))
                if value.get("project_path") not in {None, ""}
                else None
            ),
            state_path=Path(str(value["state_path"])),
        )
