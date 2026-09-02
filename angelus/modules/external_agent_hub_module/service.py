"""Application-facing lifecycle service for External Agent Hub definitions."""

from __future__ import annotations

import re

from .adapter import ExternalAgentAdapterRegistry
from .discovery import ExternalAgentProcessDiscovery
from .models import ContextPage, ContextPackage, ContextTransferResult, ExternalAgentAdapterKind, ExternalAgentCandidate, ExternalAgentCapability, ExternalAgentDefinition, ExternalAgentHealth, ExternalAgentSession
from .store import ExternalAgentHubStore


_ID = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_KINDS = {"codex_app_server", "claude_sdk", "coze", "opencode", "workbuddy", "custom"}


class ExternalAgentHubService:
    """Validate and project phase-one external Agent configuration state."""

    def __init__(
        self,
        store: ExternalAgentHubStore,
        adapters: ExternalAgentAdapterRegistry,
        process_discovery: ExternalAgentProcessDiscovery | None = None,
    ) -> None:
        """Create one service with durable storage and protocol adapters.

        Args:
            store: Durable owner of credential-free Agent definitions.
            adapters: Process-local protocol adapter registry.
            process_discovery: Read-only local-process scanner. When omitted,
                the service builds the standard procfs scanner.

        Returns:
            None.
        """
        self._store = store
        self._adapters = adapters
        self._process_discovery = process_discovery or ExternalAgentProcessDiscovery()

    def discover_local_processes(self) -> tuple[ExternalAgentCandidate, ...]:
        """Find currently running known Agent processes without attaching.

        Returns:
            Ephemeral local process candidates that require an explicit user
            confirmation before any Hub definition is created.
        """
        return self._process_discovery.discover()

    def list(self) -> tuple[ExternalAgentDefinition, ...]:
        """Return all configured external Agent definitions.

        Returns:
            Immutable durable definition snapshot.
        """
        return self._store.list()

    def get(self, agent_id: str) -> ExternalAgentDefinition:
        """Return one configured definition.

        Args:
            agent_id: Stable external Agent identifier.

        Returns:
            Matching configured definition.

        Raises:
            KeyError: If no definition has the supplied identifier.
        """
        definition = self._store.get(agent_id)
        if definition is None:
            raise KeyError(agent_id)
        return definition

    def create(self, definition: ExternalAgentDefinition) -> ExternalAgentDefinition:
        """Validate and persist a new external Agent definition.

        Args:
            definition: Candidate credential-free Agent declaration.

        Returns:
            Persisted definition.

        Raises:
            ValueError: If the candidate is invalid or its identifier exists.
        """
        self._validate(definition)
        if self._store.get(definition.id) is not None:
            raise ValueError("external Agent identifier already exists")
        return self._store.put(definition)

    def replace(self, agent_id: str, definition: ExternalAgentDefinition) -> ExternalAgentDefinition:
        """Replace one definition while preserving its stable identifier.

        Args:
            agent_id: Existing external Agent identifier from the route.
            definition: Full replacement credential-free declaration.

        Returns:
            Persisted replacement definition.

        Raises:
            KeyError: If no existing definition has the supplied identifier.
            ValueError: If the route and body identifiers differ or fields fail
                validation.
        """
        if agent_id != definition.id:
            raise ValueError("external Agent identifier cannot be changed")
        self.get(agent_id)
        self._validate(definition)
        return self._store.put(definition)

    def remove(self, agent_id: str) -> None:
        """Delete one idle definition without deleting connector credentials.

        Args:
            agent_id: External Agent identifier to remove.

        Returns:
            None.

        Raises:
            KeyError: If no definition has the supplied identifier.
        """
        if not self._store.remove(agent_id):
            raise KeyError(agent_id)

    def health(self, agent_id: str) -> ExternalAgentHealth:
        """Return a non-executing protocol health observation.

        Args:
            agent_id: External Agent identifier to probe.

        Returns:
            Current normalized health observation.

        Raises:
            KeyError: If no definition has the supplied identifier.
        """
        return self._adapters.health(self.get(agent_id))

    def capabilities(self, agent_id: str) -> tuple[ExternalAgentCapability, ...]:
        """Return declared capabilities without dispatching remote work.

        Args:
            agent_id: External Agent identifier to inspect.

        Returns:
            Immutable remote capability snapshot.

        Raises:
            KeyError: If no definition has the supplied identifier.
        """
        return self._adapters.capabilities(self.get(agent_id))

    def sessions(self, agent_id: str, limit: int) -> tuple[ExternalAgentSession, ...]:
        """Return bounded external session summaries without importing them.

        Args:
            agent_id: External Agent identifier to inspect.
            limit: Maximum number of newest summaries to return, from 1 to 200.

        Returns:
            Immutable external session summaries.

        Raises:
            KeyError: If no definition has the supplied identifier.
            ValueError: If the requested page size is out of bounds.
        """
        if not 1 <= limit <= 200:
            raise ValueError("external session limit must be between 1 and 200")
        return self._adapters.sessions(self.get(agent_id), limit)

    def contexts(self, agent_id: str, cursor: str | None, limit: int) -> ContextPage:
        """Return one bounded external context descriptor page.

        Args:
            agent_id: External Agent identifier to inspect.
            cursor: Opaque older-page cursor from the preceding result.
            limit: Requested descriptor count from 1 through 200.

        Returns:
            Typed bounded context descriptor page.

        Raises:
            KeyError: If no definition has the supplied identifier.
            ValueError: If the requested page size is out of bounds.
            ExternalAgentAdapterFailure: If the product cannot list contexts.
        """
        if not 1 <= limit <= 200:
            raise ValueError("external context limit must be between 1 and 200")
        return self._adapters.contexts(self.get(agent_id), cursor, limit)

    def read_context(self, agent_id: str, context_id: str) -> ContextPackage:
        """Read one selected external context into a portable package.

        Args:
            agent_id: External Agent identifier to inspect.
            context_id: Adapter-local context selected explicitly by the user.

        Returns:
            Credential-redacted portable context package.

        Raises:
            KeyError: If no definition has the supplied identifier.
            ValueError: If the selected context identifier is blank.
            ExternalAgentAdapterFailure: If the product cannot export context.
        """
        if not context_id.strip():
            raise ValueError("external context id must not be blank")
        return self._adapters.read_context(self.get(agent_id), context_id)

    def write_context(self, agent_id: str, package: ContextPackage) -> ContextTransferResult:
        """Write one portable package through an audited external adapter.

        Args:
            agent_id: External Agent identifier selected as the destination.
            package: Credential-redacted package selected for export.

        Returns:
            Target acknowledgement including accepted record counts.

        Raises:
            KeyError: If no definition has the supplied identifier.
            ExternalAgentAdapterFailure: If the product cannot import context.
        """
        return self._adapters.write_context(self.get(agent_id), package)

    def _validate(self, definition: ExternalAgentDefinition) -> None:
        """Validate bounded public configuration before persistence.

        Args:
            definition: Candidate external Agent declaration.

        Returns:
            None.

        Raises:
            ValueError: If an identity, adapter, or public text field is invalid.
        """
        if not _ID.fullmatch(definition.id):
            raise ValueError("external Agent id must match ^[a-z][a-z0-9_-]{1,63}$")
        if definition.adapter_kind not in _KINDS:
            raise ValueError("unsupported external Agent adapter kind")
        if not definition.title or len(definition.title) > 120:
            raise ValueError("external Agent title must be a non-empty string of at most 120 characters")
        if any(len(value) > 2_000 for value in (definition.endpoint, definition.connector_id, definition.description)):
            raise ValueError("external Agent text fields must be at most 2,000 characters")
