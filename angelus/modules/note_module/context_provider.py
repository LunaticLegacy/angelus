"""Composer source for bounded active Session and Project notes."""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Sequence

from llmfetcher.context_handlers import (
    ContextBlock,
    ContextPosition,
    ContextProvider,
    ContextSnapshot,
)

from ..context_module import ContextProviderRegistration, ContextProviderRequest
from .store import NoteError, NoteStore


class NoteContextProvider:
    provider_id = "angelus.notes"

    def __init__(self, store: NoteStore, agent_name: str, *, max_index_notes: int = 100,
                 max_index_characters: int = 12_000, max_pinned_notes: int = 24,
                 max_pinned_characters: int = 24_000) -> None:
        self.store = store
        self.agent_name = agent_name
        self.max_index_notes = max(1, max_index_notes)
        self.max_index_characters = max(1_000, max_index_characters)
        self.max_pinned_notes = max(1, max_pinned_notes)
        self.max_pinned_characters = max(1_000, max_pinned_characters)

    @property
    def source_id(self) -> str:
        return self.provider_id

    def build_blocks(self, snapshot: ContextSnapshot) -> Sequence[ContextBlock]:
        notes = self.store.list("project", limit=500) if self.store.project_db else []
        notes += self.store.list("session", limit=500)
        notes.sort(key=lambda note: note.updated_at, reverse=True)
        index = ["<angelus_note_index>", f"<agent>{escape(self.agent_name)}</agent>"]
        used = sum(len(line) + 1 for line in index)
        for note in notes[:self.max_index_notes]:
            tags = ",".join(escape(tag) for tag in note.tags)
            line = (f'<note id="{escape(note.note_id)}" scope="{escape(note.scope)}" '
                    f'title="{escape(note.title)}" tags="{tags}" />')
            if used + len(line) + len("</angelus_note_index>") + 1 > self.max_index_characters:
                break
            index.append(line)
            used += len(line) + 1
        if len(index) == 2:
            return []
        index.append("</angelus_note_index>")
        blocks = [ContextBlock(
            role="system", content="\n".join(index), source=self.source_id,
            position=ContextPosition.CUSTOM,
            persistent=True,
            metadata={"agent": self.agent_name, "note_count": len(index) - 3},
        )]
        chunks: list[str] = []
        used = 0
        for scope, note_id in self.store.pinned(self.agent_name)[:self.max_pinned_notes]:
            try:
                note = self.store.read(scope, note_id)
            except NoteError:
                continue
            if note.status != "active":
                continue
            chunk = (f'<note id="{escape(note.note_id)}" scope="{escape(note.scope)}" '
                     f'title="{escape(note.title)}">\n{escape(note.content)}\n</note>')
            if used + len(chunk) > self.max_pinned_characters:
                break
            chunks.append(chunk)
            used += len(chunk)
        if chunks:
            blocks.append(ContextBlock(
                role="system",
                content=(f'<angelus_pinned_notes agent="{escape(self.agent_name)}">\n'
                         + "\n".join(chunks) + "\n</angelus_pinned_notes>"),
                source=self.source_id, position=ContextPosition.CUSTOM,
                persistent=True, metadata={"agent": self.agent_name, "note_count": len(chunks)},
            ))
        return blocks


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
        ), request.agent_name),)


def note_context_registration(state_root: Path) -> ContextProviderRegistration:
    """Return the note source registration for the process registry."""
    return ContextProviderRegistration(
        id=NoteContextProvider.provider_id,
        factory=NoteContextFactory(state_root),
        gates=(("notes", "note_list"),),
    )


