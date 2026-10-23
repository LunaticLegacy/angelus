"""Composer source for bounded active Session and Project notes."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from llmfetcher.context_handlers import (
    ContextBlock,
    ContextPosition,
    ContextProvider,
    ContextSnapshot,
)

from ..context_module import ContextProviderRegistration, ContextProviderRequest
from .store import NoteStore


class NoteContextProvider:
    provider_id = "angelus.notes"

    def __init__(self, store: NoteStore, *, max_notes: int = 24, max_characters: int = 24_000) -> None:
        self.store = store
        self.max_notes = max(1, max_notes)
        self.max_characters = max(1_000, max_characters)

    @property
    def source_id(self) -> str:
        return self.provider_id

    def build_blocks(self, snapshot: ContextSnapshot) -> Sequence[ContextBlock]:
        notes = self.store.list("project", limit=self.max_notes) if self.store.project_db else []
        notes += self.store.list("session", limit=self.max_notes)
        notes.sort(key=lambda note: note.updated_at, reverse=True)
        chunks: list[str] = []
        used = 0
        for note in notes[: self.max_notes]:
            chunk = f'<note id="{note.note_id}" scope="{note.scope}" title="{note.title}">\n{note.content}\n</note>'
            if used + len(chunk) > self.max_characters:
                break
            chunks.append(chunk)
            used += len(chunk)
        if not chunks:
            return []
        return [ContextBlock(
            role="system",
            content="<angelus_notes>\n" + "\n".join(chunks) + "\n</angelus_notes>",
            source=self.source_id,
            position=ContextPosition.CUSTOM,
            persistent=True,
            metadata={"note_count": len(chunks)},
        )]


class NoteContextFactory:
    """Materialize the active-note source for one Agent."""

    def __init__(self, state_root: Path) -> None:
        """Retain the Angelus state root locating Project note databases.

        Args:
            state_root: Application-owned durable state root.
        """
        self._state_root = state_root

    def build(self, request: ContextProviderRequest) -> Sequence[ContextProvider]:
        """Return the note source bound to this Agent's Session and Project.

        Args:
            request: Live Session whose workspace paths scope the notes.

        Returns:
            One always-on note source.
        """
        return (NoteContextProvider(NoteStore(
            request.workspace.state_path,
            NoteStore.project_root(self._state_root, request.workspace.project_path),
        )),)


def note_context_registration(state_root: Path) -> ContextProviderRegistration:
    """Return the note source registration for the process registry."""
    return ContextProviderRegistration(
        id=NoteContextProvider.provider_id,
        factory=NoteContextFactory(state_root),
    )


