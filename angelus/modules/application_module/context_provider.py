"""Angelus-owned context sources shared by every runtime Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from llmfetcher.context_handlers import (
    ContextBlock,
    ContextPosition,
    ContextSnapshot,
)


class WorkspaceContextProvider:
    """Expose the bound project and Angelus state directories to an Agent.

    The project path is the directory where file and shell tools operate;
    the state path contains Angelus-managed checkpoints and must not be
    treated as a project artifact. Both are included so the model can
    distinguish user files from runtime persistence.
    """

    provider_id = "angelus.workspace"

    def __init__(self, project_path: Path | None, state_path: Path, agent_name: str) -> None:
        """Create a provider for one Session and one Agent identity."""
        self.project_path = project_path.resolve() if project_path is not None else None
        self.state_path = state_path.resolve()
        self.agent_name = agent_name

    @property
    def source_id(self) -> str:
        """Return the stable Composer source identity."""
        return self.provider_id

    def build_blocks(self, snapshot: ContextSnapshot) -> Sequence[ContextBlock]:
        """Build the durable workspace description for the next request."""
        project = str(self.project_path) if self.project_path is not None else "(not bound)"
        content = (
            "<angelus_workspace>\n"
            f"<agent>{self.agent_name}</agent>\n"
            f"<project_directory>{project}</project_directory>\n"
            f"<angelus_state_directory>{self.state_path}</angelus_state_directory>\n"
            "<project_directory_usage>File and shell tools target this directory.</project_directory_usage>\n"
            "<angelus_state_usage>Runtime checkpoints belong here; do not edit them as project files.</angelus_state_usage>\n"
            "</angelus_workspace>"
        )
        return [ContextBlock(
            role="system",
            content=content,
            source=self.source_id,
            position=ContextPosition.PERSISTENT,
            persistent=True,
            metadata={"project_path": project, "state_path": str(self.state_path)},
        )]


__all__ = ["WorkspaceContextProvider"]
