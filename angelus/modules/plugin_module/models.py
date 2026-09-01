"""Typed contracts for Angelus plugins and their persisted settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from llmfetcher import Tool

from ..tool_module import ToolPolicy


PluginKind = Literal["tool", "ui", "theme_pack"]
PluginSettingScalar = str | int | float | bool


@dataclass(frozen=True)
class PluginPermission:
    """One capability a plugin requests before its code can be loaded.

    Attributes:
        action: Named host capability such as ``network`` or ``fs.read``.
        scope: Narrow path, URL, or event scope granted for that action.
    """

    action: str
    scope: str


@dataclass(frozen=True)
class PluginSettingField:
    """One typed, non-secret field displayed in a plugin settings form.

    Attributes:
        key: Stable persisted setting key.
        value_type: One supported scalar kind.
        title: User-facing field label.
        description: Optional explanation shown beside the control.
        required: Whether the persisted settings must include this field.
        default: Optional scalar supplied when the record is first registered.
        choices: Optional finite list of permitted scalar values.
        minimum: Optional inclusive numeric lower bound.
        maximum: Optional inclusive numeric upper bound.
        value_format: Optional UI hint; only ``uri`` is currently supported.
    """

    key: str
    value_type: Literal["string", "integer", "number", "boolean"]
    title: str = ""
    description: str = ""
    required: bool = False
    default: PluginSettingScalar | None = None
    choices: tuple[PluginSettingScalar, ...] = ()
    minimum: int | float | None = None
    maximum: int | float | None = None
    value_format: Literal["uri"] | None = None


@dataclass(frozen=True)
class PluginTheme:
    """One CSS skin exposed by a theme-pack plugin.

    Attributes:
        id: Skin identifier unique inside its owning plugin.
        title: User-visible skin name.
        asset: Manifest-whitelisted CSS file relative to the plugin directory.
        mode: Preferred application color mode.
    """

    id: str
    title: str
    asset: str
    mode: Literal["dark", "light"]


@dataclass(frozen=True)
class PluginManifest:
    """Validated, declarative plugin package contract.

    Attributes:
        name: Filesystem-safe stable plugin name.
        display_name: Optional human-facing display name.
        version: Semantic package version.
        api_version: Host plugin API version.
        kind: Runtime capability class; theme packs never execute Python.
        entry: Optional Python entry-module path for executable plugins.
        description: Optional package description.
        permissions: Requested capabilities requiring explicit approval.
        assets: Static asset whitelist served by the host.
        settings_enabled: Whether this plugin owns a persisted settings form.
        settings_schema: Typed settings fields; empty enables legacy JSON-free defaults.
        themes: Named CSS skins published by a theme-pack.
    """

    name: str
    display_name: str
    version: str
    api_version: str
    kind: PluginKind
    entry: str | None
    description: str = ""
    permissions: tuple[PluginPermission, ...] = ()
    assets: tuple[str, ...] = ()
    settings_enabled: bool = False
    settings_schema: tuple[PluginSettingField, ...] = ()
    themes: tuple[PluginTheme, ...] = ()


@dataclass(frozen=True)
class PluginSettingValue:
    """One persisted scalar plugin setting.

    Attributes:
        key: Stable manifest-declared setting key.
        value: Validated non-secret scalar value.
    """

    key: str
    value: PluginSettingScalar


@dataclass(frozen=True)
class PluginRecord:
    """Durable local registration state for one discovered plugin.

    Attributes:
        id: Stable local plugin identity, currently equal to manifest name.
        name: Manifest name used for URL and module namespaces.
        package_path: Resolved package directory under the managed plugin root.
        enabled: Whether the package is approved for automatic restoration.
        permissions_granted: Explicit user-approved requested permissions.
        settings: Persisted non-secret scalar settings.
    """

    id: str
    name: str
    package_path: str
    enabled: bool = False
    permissions_granted: tuple[PluginPermission, ...] = ()
    settings: tuple[PluginSettingValue, ...] = ()


@dataclass(frozen=True)
class PluginToolCategory:
    """A plugin-owned user-visible tool category.

    Attributes:
        id: Package-local category ID.
        title: Human-readable category title.
        description: Explanation displayed by the host permission UI.
    """

    id: str
    title: str
    description: str


@dataclass(frozen=True)
class PluginToolDefinition:
    """A package-local Tool definition that the host namespaces on registration.

    Attributes:
        id: Package-local tool ID.
        category_id: Owning package-local category ID.
        title: User-facing Tool title.
        description: Safe Tool explanation.
        roles: Agent roles allowed to materialize this Tool.
    """

    id: str
    category_id: str
    title: str
    description: str
    roles: frozenset[str]


class PluginToolProvider(Protocol):
    """Plugin-owned factory for concrete llmfetcher tools."""

    def materialize(self, session_id: str, policy: ToolPolicy, role: str) -> list[Tool]:
        """Create concrete tools for one Session and Agent role.

        Args:
            session_id: Owning Session identity.
            policy: Current effective host tool policy.
            role: Receiving Agent role.

        Returns:
            Concrete tools whose names match their host-namespaced manifest IDs.
        """


@dataclass(frozen=True)
class PluginToolContribution:
    """One plugin tool-provider registration requested during ``setup``.

    Attributes:
        provider: Runtime factory for concrete Tools.
        categories: Package-local category definitions.
        definitions: Package-local Tool definitions.
    """

    provider: PluginToolProvider
    categories: tuple[PluginToolCategory, ...]
    definitions: tuple[PluginToolDefinition, ...]


@dataclass
class PluginRuntime:
    """Constrained host object supplied to one executing plugin's setup hook.

    Attributes:
        plugin: Manifest defining the executing plugin.
        settings: Persisted settings validated by the host.
        state_path: Plugin-private state directory under Angelus state.
        contributions: Tool providers accumulated before the host publishes them.
    """

    plugin: PluginManifest
    settings: tuple[PluginSettingValue, ...]
    state_path: str
    contributions: list[PluginToolContribution] = field(default_factory=list)

    def register_tool_provider(self, contribution: PluginToolContribution) -> None:
        """Stage one Tool contribution for atomic publication after setup.

        Args:
            contribution: Typed package-local provider, categories, and tools.

        Returns:
            None.
        """
        self.contributions.append(contribution)
