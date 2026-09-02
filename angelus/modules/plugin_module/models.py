"""Typed contracts for Angelus plugins and their persisted settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol

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
        value_format: Optional UI hint: ``uri``, ``path``, or ``textarea``.
        placeholder: Optional bounded input hint shown before the user enters a
            value; it is never persisted as a parameter value.
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
    value_format: Literal["uri", "path", "textarea"] | None = None
    placeholder: str = ""


@dataclass(frozen=True)
class PluginPanelField:
    """One typed transient field displayed in a host-rendered plugin panel.

    Attributes:
        key: Stable panel-local input key.
        value_type: One supported scalar kind.
        title: User-facing field label.
        description: Optional explanation rendered beside the control.
        required: Whether the submitted action requires this input.
        default: Optional non-sensitive scalar applied when omitted.
        choices: Optional permitted scalar values.
        minimum: Optional inclusive numeric lower bound.
        maximum: Optional inclusive numeric upper bound.
        value_format: Optional renderer hint including ``password`` for a
            sensitive transient input.
        placeholder: Optional bounded input hint which is never persisted.
        sensitive: Whether the host must treat this value as transient secret
            input. Sensitive fields cannot declare defaults or settings.
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
    value_format: Literal["uri", "path", "textarea", "password"] | None = None
    placeholder: str = ""
    sensitive: bool = False


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
class PluginPanel:
    """One declarative plugin function panel rendered by the host.

    Attributes:
        id: Plugin-local stable panel identity.
        title: User-facing panel title.
        description: Optional explanation rendered above the form.
        action: Runtime action identifier invoked when the user submits.
        submit_label: User-facing label for the action button.
        fields: Typed transient input controls; values are not persisted.
    """

    id: str
    title: str
    description: str
    action: str
    submit_label: str
    fields: tuple[PluginPanelField, ...]


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
        panels: Declarative transient-input function panels rendered by the host.
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
    panels: tuple[PluginPanel, ...] = ()


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
class PluginUiActionRequest:
    """Validated transient user input delivered to one plugin action.

    Attributes:
        panel_id: Manifest panel that submitted the action.
        values: Field values validated against that panel's schema.
    """

    panel_id: str
    values: tuple[PluginSettingValue, ...]

    def value(
        self,
        key: str,
        default: PluginSettingScalar | None = None,
    ) -> PluginSettingScalar | None:
        """Return one validated transient field value.

        Args:
            key: Manifest-declared panel field key to read.
            default: Value returned when the request omitted an optional field.

        Returns:
            Validated scalar value, or ``default`` when no value was supplied.
        """
        return next((item.value for item in self.values if item.key == key), default)


@dataclass(frozen=True)
class PluginUiActionResult:
    """Safe textual result rendered by the host after a plugin UI action.

    Attributes:
        title: Optional short result heading.
        content: Plain text or Markdown-like content rendered as text by the
            generic panel to prevent plugin-supplied DOM injection.
        tone: Visual outcome class for neutral, successful, or failed actions.
    """

    title: str
    content: str
    tone: Literal["info", "success", "error"] = "info"


@dataclass(frozen=True)
class PluginUiActionRegistration:
    """One action handler explicitly registered during plugin setup.

    Attributes:
        id: Plugin-local action identity declared by a manifest panel.
        handler: Callable receiving validated transient fields and returning a
            host-renderable textual result.
    """

    id: str
    handler: Callable[[PluginUiActionRequest], PluginUiActionResult]


@dataclass(frozen=True)
class PluginRecord:
    """Durable local registration state for one discovered plugin.

    Attributes:
        id: Stable local plugin identity, currently equal to manifest name.
        name: Manifest name used for URL and module namespaces.
        package_path: Resolved package directory below an approved managed or
            local development discovery root.
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
        settings: Persisted user parameters validated by the host.
        state_path: Plugin-private state directory under Angelus state rather
            than the source or managed package directory.
        contributions: Tool providers accumulated before the host publishes them.
        ui_actions: Transient UI action handlers accumulated before activation.
    """

    plugin: PluginManifest
    settings: tuple[PluginSettingValue, ...]
    state_path: str
    contributions: list[PluginToolContribution] = field(default_factory=list)
    ui_actions: list[PluginUiActionRegistration] = field(default_factory=list)

    def register_tool_provider(self, contribution: PluginToolContribution) -> None:
        """Stage one Tool contribution for atomic publication after setup.

        Args:
            contribution: Typed package-local provider, categories, and tools.

        Returns:
            None.
        """
        self.contributions.append(contribution)

    def register_ui_action(
        self,
        action_id: str,
        handler: Callable[[PluginUiActionRequest], PluginUiActionResult],
    ) -> None:
        """Stage one manifest-declared user-interface action handler.

        Args:
            action_id: Plugin-local action ID referenced by a manifest panel.
            handler: Callable that consumes validated fields and returns a
                textual host-renderable action result.

        Returns:
            None.
        """
        self.ui_actions.append(PluginUiActionRegistration(action_id, handler))

    def setting(
        self,
        key: str,
        default: PluginSettingScalar | None = None,
    ) -> PluginSettingScalar | None:
        """Read one validated user-configured plugin parameter.

        Args:
            key: Manifest-declared setting key to look up.
            default: Value returned when the user has not persisted the key.

        Returns:
            Persisted typed scalar parameter, or ``default`` when absent.
        """
        return next((item.value for item in self.settings if item.key == key), default)
