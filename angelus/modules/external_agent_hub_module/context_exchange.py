"""Bounded, credential-safe exchange between Session and external contexts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from llmfetcher.llm_types import LLMContext

from ..execution_module import ExecutionState
from .models import ContextMessage, ContextPackage, ContextRole, ContextToolCall, ContextTransferResult

if TYPE_CHECKING:
    from ...core import AngelusCore


_SENSITIVE = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+|api[_-]?key\s*[:=]\s*|token\s*[:=]\s*|password\s*[:=]\s*)[^\s,;\]\}]+"
)


class ContextExchangeError(RuntimeError):
    """Raised when a bounded context exchange cannot safely proceed."""


class SessionContextExchangeService:
    """Export and append portable packages through Session-owned contexts.

    The service deliberately treats a package as historical data. Imported
    tool calls are retained only as text in the package and are never
    materialized into executable ToolInfo records.

    Args:
        core: Process composition root that owns Session and console services.
    """

    def __init__(self, core: "AngelusCore") -> None:
        """Bind the service to the only application-owned Session graph.

        Args:
            core: Process composition root owning all Sessions and services.

        Returns:
            None.
        """
        self._core = core

    def export_page(
        self,
        session_id: str,
        agent_name: str,
        before: int | None,
        limit: int,
    ) -> tuple[ContextPackage, int | None, bool]:
        """Export one durable context page without reading the full transcript.

        Args:
            session_id: Stable Session identity owning the source Agent.
            agent_name: Coordinator or worker identity whose history is read.
            before: Exclusive older-than timeline cursor from a prior page.
            limit: Maximum records in this package, from 1 through 200.

        Returns:
            Portable chronological page, continuation cursor, and whether an
            older page remains available.

        Raises:
            ContextExchangeError: If the Session context cannot be projected.
        """
        if not 1 <= limit <= 200:
            raise ContextExchangeError("context export limit must be between 1 and 200")
        try:
            page = self._core.console_service.messages(session_id, agent_name, before, limit)
        except Exception as exc:
            raise ContextExchangeError(f"cannot export Session context: {exc}") from exc
        raw_messages = page.get("messages")
        if not isinstance(raw_messages, list):
            raise ContextExchangeError("Session context projection is invalid")
        messages = tuple(self._message(item) for item in raw_messages if isinstance(item, Mapping))
        return (
            ContextPackage(
                format_version=1,
                source="angelus",
                source_session_id=session_id,
                source_agent=agent_name,
                messages=messages,
                redactions=("credential-like values are redacted before external transfer",),
            ),
            self._optional_int(page.get("next_cursor")),
            page.get("has_more") is True,
        )

    def append_package(
        self,
        session_id: str,
        agent_name: str,
        package: ContextPackage,
    ) -> ContextTransferResult:
        """Append portable historical records to one idle Session Agent.

        Args:
            session_id: Stable Session identity receiving the records.
            agent_name: Existing coordinator or worker identity receiving data.
            package: Credential-redacted package explicitly selected by a user.

        Returns:
            Import result with accepted and rejected record counts.

        Raises:
            ContextExchangeError: If the target is active, unavailable, or its
                context checkpoint cannot be safely persisted.
        """
        session = self._core.sessions.get(session_id)
        if session.execution is not None and session.execution.snapshot().state in {
            ExecutionState.RUNNING,
            ExecutionState.STOPPING,
            ExecutionState.FORCE_STOPPING,
        }:
            raise ContextExchangeError("context import is allowed only while the Session is idle")
        self._core.session_service.ensure_coordinator(session_id)
        session = self._core.sessions.get(session_id)
        agent = session.swarm.get_agent(agent_name)
        if agent is None:
            raise ContextExchangeError("target Agent is not materialized")
        path = self._context_path(session_id, agent_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = agent.context_handler
        if path.is_file() and not handler.load(path):
            raise ContextExchangeError("target Agent context cannot be loaded")
        linear = getattr(handler, "linear", handler)
        messages = getattr(linear, "messages", None)
        if not isinstance(messages, list):
            raise ContextExchangeError("target Agent context does not support append import")
        round_value = getattr(linear, "_round", 0)
        if not isinstance(round_value, int):
            raise ContextExchangeError("target Agent context timeline is invalid")
        accepted = 0
        rejected = 0
        for message in package.messages:
            if message.role not in {"system", "user", "assistant"}:
                rejected += 1
                continue
            round_value += 1
            messages.append(
                LLMContext(
                    role=message.role,
                    timeline=round_value,
                    content=self._redact(message.content),
                    content_reasoning=self._redact(message.reasoning),
                )
            )
            accepted += 1
        linear._round = round_value
        if not handler.save(path):
            raise ContextExchangeError("target Agent context could not be persisted")
        return ContextTransferResult(
            direction="import",
            agent_id=session_id,
            context_id=agent_name,
            accepted_messages=accepted,
            rejected_messages=rejected,
            detail="Imported records are historical context only; tool calls were not executed.",
        )

    def _message(self, raw: Mapping[object, object]) -> ContextMessage:
        """Convert one console message card into a portable record.

        Args:
            raw: JSON-safe console message card from the durable projection.

        Returns:
            Credential-redacted portable context record.
        """
        role = raw.get("role")
        normalized_role: ContextRole = role if role in {"system", "user", "assistant", "tool"} else "assistant"
        tools_raw = raw.get("tools")
        tools = tuple(
            ContextToolCall(
                name=str(tool.get("name", "")),
                arguments_json=self._redact(str(tool.get("arguments", ""))),
                result=self._redact(str(tool.get("result", ""))),
            )
            for tool in tools_raw
            if isinstance(tool, Mapping)
        ) if isinstance(tools_raw, list) else ()
        return ContextMessage(
            sequence=self._optional_int(raw.get("timeline")) or 0,
            role=normalized_role,
            content=self._redact(str(raw.get("content", ""))),
            reasoning=self._redact(str(raw.get("reasoning", ""))),
            tool_calls=tools,
        )

    def _context_path(self, session_id: str, agent_name: str) -> Path:
        """Return the durable pointer path for one valid Session Agent.

        Args:
            session_id: Stable Session identity owning the context checkpoint.
            agent_name: Existing Agent identity owning the context checkpoint.

        Returns:
            Agent context pointer path beneath Angelus state.
        """
        return self._core.workspaces.get(session_id).state_path / "agents" / agent_name / "context.json"

    @staticmethod
    def _redact(value: str) -> str:
        """Remove credential-like substrings from text copied across products.

        Args:
            value: Source text that may contain an accidental credential.

        Returns:
            Text with credential-looking value portions replaced.
        """
        return _SENSITIVE.sub(r"\1[REDACTED]", value)

    @staticmethod
    def _optional_int(value: object) -> int | None:
        """Return a non-boolean integer cursor when the value is valid.

        Args:
            value: Untrusted cursor value from a JSON-safe projection.

        Returns:
            Integer cursor or ``None`` when no valid integer exists.
        """
        return value if isinstance(value, int) and not isinstance(value, bool) else None
