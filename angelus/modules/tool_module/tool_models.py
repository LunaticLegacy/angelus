"""Typed records for the unified Agent-tool registry."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolCategory:
    """One user-visible group of registered Agent tools.

    Attributes:
        id: Stable category identity persisted in Session policy documents.
        title: Human-readable category title.
        description: Explanation displayed beside the category toggle.
    """

    id: str
    title: str
    description: str


@dataclass(frozen=True)
class ToolDefinition:
    """One stable tool capability independent of a frontend implementation.

    Attributes:
        id: Stable Tool name delivered to the model provider.
        category_id: Category that must be authorized with this Tool.
        title: Human-readable Tool title.
        description: Safe user-facing Tool explanation.
        provider_id: Registered provider that materializes this Tool at runtime.
        roles: Agent roles permitted to receive this Tool.
    """

    id: str
    category_id: str
    title: str
    description: str
    provider_id: str
    roles: frozenset[str]


@dataclass(frozen=True)
class ToolAvailability:
    """Current materialization state for one Tool.

    Attributes:
        tool_id: Stable Tool identity.
        available: Whether its provider can create it in the current Session.
        reason: User-safe reason when the Tool is unavailable.
    """

    tool_id: str
    available: bool
    reason: str = ""


@dataclass(frozen=True)
class ToolCatalogCategory:
    """One registry category and its concrete model-visible tool records.

    Attributes:
        id: Persisted category identity.
        title: User-facing category label.
        description: Safe explanation of the category.
        tools: Concrete registered tool definitions in this category.
    """

    id: str
    title: str
    description: str
    tools: tuple[ToolDefinition, ...]


@dataclass(frozen=True)
class ToolCatalog:
    """HTTP-safe snapshot of every currently registered tool capability.

    Attributes:
        categories: Ordered visible categories and their tool definitions.
    """

    categories: tuple[ToolCatalogCategory, ...]
