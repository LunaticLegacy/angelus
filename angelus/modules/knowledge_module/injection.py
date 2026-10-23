"""Per-Agent durable knowledge pins injected into every request.

The Agent and the Session UI must never diverge: both mutate the same durable
document, and ``set_pins`` is the only writer. The Tool wrappers compose a new
list and call it; the HTTP surface sends the list it displays and calls it.

The kernel owns the pin document. The documents themselves come from a
host-supplied :class:`KnowledgeCorpus`, so the CTF product corpus is one
implementation rather than a hard dependency.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Sequence
from pathlib import Path

from ..settings_module.json_store import read_json, write_json
from .corpus import KnowledgeCorpus

MAX_PINS = 24
_AGENT = re.compile(r"[A-Za-z0-9_.-]{1,120}\Z")
_SCHEMA_VERSION = 1


class KnowledgeInjectionError(ValueError):
    """Rejected pin set or invalid Agent scope."""


class KnowledgeInjectionService:
    """Own the durable pin set of every (Session, Agent) pair.

    Args:
        state_root: Angelus state directory holding all Session state.
        corpus: Host-supplied document source used to validate and render pins.
    """

    def __init__(self, state_root: Path, corpus: KnowledgeCorpus | None = None) -> None:
        self._root = state_root / "sessions"
        self._corpus = corpus
        self._locks: dict[Path, threading.RLock] = {}
        self._guard = threading.Lock()

    @property
    def available(self) -> bool:
        """Whether a corpus is bound, so pins can be validated and rendered."""
        return self._corpus is not None

    @property
    def corpus(self) -> KnowledgeCorpus:
        """Return the bound corpus.

        Returns:
            The host-supplied document source.

        Raises:
            KnowledgeInjectionError: If the host did not bind one.
        """
        if self._corpus is None:
            raise KnowledgeInjectionError("knowledge corpus is unavailable")
        return self._corpus

    def _document(self, session_id: str) -> Path:
        """Return the session's knowledge directory without creating it."""
        return self._root / session_id / "knowledge" / "injection.json"

    def _lock(self, path: Path) -> threading.RLock:
        """Return the process-wide lock guarding one Session's pin file."""
        with self._guard:
            return self._locks.setdefault(path, threading.RLock())

    @staticmethod
    def _agent(value: object) -> str:
        """Validate one Agent scope name."""
        agent = value.strip() if isinstance(value, str) else ""
        if not _AGENT.fullmatch(agent):
            raise KnowledgeInjectionError("agent must contain 1-120 letters, numbers, dots, underscores, or hyphens")
        return agent

    def _targets(self, value: object) -> tuple[str, ...]:
        """Validate and normalize one complete pin list."""
        if not isinstance(value, (list, tuple)):
            raise KnowledgeInjectionError("pins must be an array of knowledge paths")
        if len(value) > MAX_PINS:
            raise KnowledgeInjectionError(f"at most {MAX_PINS} knowledge documents can be pinned")
        result: list[str] = []
        for item in value:
            path = item.strip() if isinstance(item, str) else ""
            if not path:
                raise KnowledgeInjectionError("pinned knowledge path must be a non-empty string")
            if path in result:
                continue
            result.append(path)
        corpus = self.corpus
        for path in result:
            try:
                corpus.read(path)
            except KeyError:
                raise KnowledgeInjectionError(f"unknown knowledge document: {path}") from None
            except ValueError as exc:
                raise KnowledgeInjectionError(str(exc)) from exc
        return tuple(result)

    def read(self, session_id: str, agent: str) -> tuple[str, ...]:
        """Return the pinned knowledge paths for one Agent."""
        document = self._document(session_id)
        scope = self._agent(agent)
        with self._lock(document):
            raw = read_json(document, {})
            agents = raw.get("agents") if isinstance(raw, dict) else None
            values = agents.get(scope) if isinstance(agents, dict) else None
            if not isinstance(values, list):
                return ()
            return tuple(item for item in values if isinstance(item, str))

    def set_pins(self, session_id: str, agent: str, pins: Sequence[object]) -> tuple[str, ...]:
        """Replace one Agent's pin list atomically.

        Args:
            session_id: Owning Session identity.
            agent: Receiving Agent identity.
            pins: Complete desired list of knowledge paths.

        Returns:
            The stored list, in the order supplied.

        Raises:
            KnowledgeInjectionError: If the Agent scope or a path is invalid.
        """
        document = self._document(session_id)
        scope = self._agent(agent)
        targets = self._targets(list(pins))
        with self._lock(document):
            raw = read_json(document, {})
            agents = raw.get("agents") if isinstance(raw, dict) else None
            stored: dict[str, list[str]] = {}
            if isinstance(agents, dict):
                for name, values in agents.items():
                    if isinstance(name, str) and isinstance(values, list):
                        stored[name] = [item for item in values if isinstance(item, str)]
            if targets:
                stored[scope] = list(targets)
            else:
                stored.pop(scope, None)
            write_json(document, {"schema_version": _SCHEMA_VERSION, "agents": stored})
        return targets

    def add(self, session_id: str, agent: str, path: str) -> tuple[str, ...]:
        """Append one path to the Agent's pin list through ``set_pins``."""
        document = self._document(session_id)
        with self._lock(document):
            return self.set_pins(session_id, agent, [*self.read(session_id, agent), path])

    def remove(self, session_id: str, agent: str, path: str) -> tuple[str, ...]:
        """Remove one path from the Agent's pin list through ``set_pins``."""
        document = self._document(session_id)
        with self._lock(document):
            return self.set_pins(
                session_id, agent,
                [item for item in self.read(session_id, agent) if item != path],
            )


__all__ = [
    "KnowledgeInjectionError",
    "KnowledgeInjectionService",
    "MAX_PINS",
]
