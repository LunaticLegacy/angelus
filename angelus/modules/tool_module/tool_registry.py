"""The one process-wide registry that materializes authorized Agent tools."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from llmfetcher import Tool

from .tool_models import ToolCatalog, ToolCatalogCategory, ToolCategory, ToolDefinition
from .tool_policy import ToolPolicy

if TYPE_CHECKING:
    from ..session_module.session_handler import Session


class ToolProvider(Protocol):
    """Materialize a registered family's concrete Tools for one Session."""

    def materialize(self, session: "Session", policy: ToolPolicy, role: str) -> list[Tool]:
        """Build only Tools this provider can safely expose.

        Args:
            session: Session owning runtime state and credentials.
            policy: Effective Session authorization policy.
            role: Receiving Agent role.

        Returns:
            Concrete provider-native Tool instances.
        """


@dataclass(frozen=True)
class ToolProviderRegistration:
    """One provider plus its categories and Tool definitions.

    Attributes:
        id: Stable provider identity.
        provider: Runtime materializer for the registered Tools.
        categories: Categories owned by the provider.
        definitions: Tool definitions owned by the provider.
    """

    id: str
    provider: ToolProvider
    categories: tuple[ToolCategory, ...]
    definitions: tuple[ToolDefinition, ...]


class ToolRegistry:
    """Validate unique registrations and materialize Tools from one policy."""

    def __init__(self) -> None:
        """Create an empty process-local registry."""
        self._providers: dict[str, ToolProviderRegistration] = {}
        self._categories: dict[str, ToolCategory] = {}
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, registration: ToolProviderRegistration) -> None:
        """Register one complete provider atomically after uniqueness checks.

        Args:
            registration: Provider, categories, and definitions to own.

        Returns:
            None.

        Raises:
            ValueError: If an ID is duplicated or a definition is malformed.
        """
        if registration.id in self._providers:
            raise ValueError(f"duplicate tool provider: {registration.id}")
        category_ids = {category.id for category in registration.categories}
        if len(category_ids) != len(registration.categories) or any(not item for item in category_ids):
            raise ValueError("tool provider has invalid category IDs")
        if any(category_id in self._categories for category_id in category_ids):
            raise ValueError("duplicate tool category")
        definition_ids = {definition.id for definition in registration.definitions}
        if len(definition_ids) != len(registration.definitions) or any(not item for item in definition_ids):
            raise ValueError("tool provider has invalid Tool IDs")
        if any(tool_id in self._definitions for tool_id in definition_ids):
            raise ValueError("duplicate Tool ID")
        for definition in registration.definitions:
            if definition.provider_id != registration.id or definition.category_id not in category_ids:
                raise ValueError("Tool definition does not belong to its provider")
        self._providers[registration.id] = registration
        self._categories.update({category.id: category for category in registration.categories})
        self._definitions.update({definition.id: definition for definition in registration.definitions})

    def materialize(self, session: "Session", policy: ToolPolicy, role: str) -> list[Tool]:
        """Build all authorized concrete Tools for one Agent role.

        Args:
            session: Session owning the target Agent.
            policy: Effective category-and-Tool grants.
            role: Agent role receiving Tools.

        Returns:
            Unique concrete Tools in provider registration order.
        """
        tools: list[Tool] = []
        seen: set[str] = set()
        for registration in self._providers.values():
            for tool in registration.provider.materialize(session, policy, role):
                if tool.name not in seen:
                    tools.append(tool)
                    seen.add(tool.name)
        return tools

    def definitions(self) -> tuple[ToolDefinition, ...]:
        """Return all registered Tool definitions in stable registration order.

        Returns:
            Immutable Tool-definition snapshot.
        """
        return tuple(self._definitions.values())

    def categories(self) -> tuple[ToolCategory, ...]:
        """Return registered user-visible categories in registration order.

        Returns:
            Immutable category snapshot used by HTTP and UI projections.
        """
        return tuple(self._categories.values())

    def catalog(self) -> ToolCatalog:
        """Build a typed public catalog from actual registrations only.

        Returns:
            Categories with their registered Tool definitions in stable order.
        """
        return ToolCatalog(tuple(
            ToolCatalogCategory(
                id=category.id,
                title=category.title,
                description=category.description,
                tools=tuple(item for item in self._definitions.values() if item.category_id == category.id),
            )
            for category in self._categories.values()
        ))
