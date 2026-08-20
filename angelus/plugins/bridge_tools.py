"""Plugin tools bridge: fold PluginManager's published tools into the agent chain (swarm S4).

Contract basis — ``docs/plugin-api.md``:

* §4 ``PluginRuntime.register_tool(name, schema, handler)``: a plugin tool is
  registered under its short name; the manager namespaces it automatically and
  publishes a :class:`~angelus.plugins.manager.ToolRegistration` whose live
  name is ``plugin.<plugin>.<tool>``.  The schema argument is a JSON-Schema
  style parameter declaration that the tools bridge maps onto the
  :class:`~llmfetcher.llm_types.ToolParameter` model
  (name/description/parameters).
* §5 event-whitelist context: tool wiring shares the agent execution surface
  with the hook bridge (``bridge_hooks.py``); this module only bridges tools
  and never touches ``llmfetcher/`` source.

Execution spec: ``docs/plugin-swarm-execution.md`` §5-S4 (acceptance: names
carry the ``plugin.<name>.`` prefix and cannot collide with built-in tools;
schema maps completely to ToolParameter).

The module mirrors the tool-factory aggregation pattern of
``llmfetcher/tools/__init__.py`` (``_LAZY_FACTORIES``): ``create_plugin_tools``
is the angelus-side factory that plugs into the same resolution chain as
``create_shell_tools``/``create_knowledge_tools``/...  Because ``llmfetcher``
is a submodule boundary, **no** llmfetcher file is modified — everything is
bridged here on the angelus side.

Mapping (per ``ToolRegistration``):

* ``Tool.name``      <- ``registration.full_name`` (``plugin.<plugin>.<tool>``;
  already namespaced by the manager — reused verbatim so plugin tools can
  never shadow a built-in tool).
* ``Tool.description`` <- ``registration.schema["description"]`` (fallback:
  generated from plugin/tool names when the plugin did not supply one).
* ``Tool.schemas``   <- :class:`ToolSchema` built from
  ``registration.schema["parameters"]`` — accepts both a JSON-Schema style
  object (``{"type", "properties", "required"}``) and a flat list of
  ToolParameter-style dicts (``{"name", "type", "description", ...}``).
* ``Tool.handler``   <- ``registration.handler``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from llmfetcher.llm_types import Tool, ToolParameter, ToolSchema

if TYPE_CHECKING:  # pragma: no cover - runtime-core merge-time dependency
    from .manager import ToolRegistration

__all__ = ["create_plugin_tools"]

_LOGGER = logging.getLogger(__name__)

#: Mandatory namespace prefix for every published plugin tool name.
PLUGIN_PREFIX = "plugin."


def create_plugin_tools(manager: Any | None = None) -> list[Tool]:
    """Create one :class:`~llmfetcher.llm_types.Tool` per published plugin tool.

    Reads the PluginManager's live registration table
    (:meth:`angelus.plugins.manager.PluginManager.get_tools`, a
    ``dict[str, ToolRegistration]`` keyed by the namespaced full name) and
    converts every entry into a llmfetcher ``Tool`` for the agent tool chain.

    Args:
        manager: A :class:`~angelus.plugins.manager.PluginManager` (or any
            object exposing ``get_tools() -> dict[str, ToolRegistration]``).
            ``None`` yields an empty list, mirroring the no-op behaviour of
            ``create_knowledge_tools`` without a knowledge base.

    Returns:
        List of ``Tool`` objects whose names carry the ``plugin.<name>.``
        prefix (``ToolRegistration.full_name`` reused verbatim), so they
        cannot collide with built-in tools.  Registration entries that are
        malformed or not namespaced are skipped with a warning rather than
        breaking the tool chain.

    Raises:
        TypeError: If the manager's ``get_tools()`` is not callable.
    """
    if manager is None:
        return []

    get_tools = getattr(manager, "get_tools", None)
    if not callable(get_tools):
        raise TypeError(
            "create_plugin_tools(manager) requires an object exposing "
            f"get_tools(); got {type(manager).__name__!r}"
        )

    registrations = get_tools()
    if not registrations:
        return []

    tools: list[Tool] = []
    for full_name, registration in registrations.items():
        tool = _registration_to_tool(registration, default_name=full_name)
        if tool is not None:
            tools.append(tool)
    return tools


def _registration_to_tool(
    registration: Any, *, default_name: str | None = None
) -> Tool | None:
    """Map one ``ToolRegistration`` onto a llmfetcher ``Tool`` (duck-typed).

    Attribute access keeps the bridge decoupled from the exact frozen
    dataclass while honouring its contract: ``plugin``/``name``/``schema``/
    ``handler`` fields plus the derived ``full_name`` property.

    Returns ``None`` (with a warning) when the registration is unusable so a
    single bad entry never breaks the whole tool chain.
    """
    full_name = getattr(registration, "full_name", None) or default_name
    if not full_name or not str(full_name).startswith(PLUGIN_PREFIX):
        _LOGGER.warning(
            "skipping tool registration %r: name %r is not namespaced under "
            "the %r prefix (would collide with built-in tools)",
            getattr(registration, "name", registration),
            full_name,
            PLUGIN_PREFIX,
        )
        return None

    schema = getattr(registration, "schema", None) or {}
    handler = getattr(registration, "handler", None)
    if not callable(handler):
        _LOGGER.warning(
            "skipping tool %r: handler is not callable (%r)",
            full_name,
            handler,
        )
        return None

    if not isinstance(schema, dict):
        _LOGGER.warning(
            "skipping tool %r: schema must be a dict, got %r",
            full_name,
            type(schema).__name__,
        )
        return None

    plugin = getattr(registration, "plugin", None) or ""
    short_name = getattr(registration, "name", None) or full_name
    description = schema.get("description") or (
        f"{short_name} tool provided by plugin {plugin}" if plugin else short_name
    )

    return Tool(
        name=full_name,
        description=str(description),
        schemas=_schema_to_tool_schema(schema),
        handler=handler,
    )


def _schema_to_tool_schema(schema: dict[str, Any]) -> ToolSchema:
    """Map a plugin ``register_tool`` schema onto :class:`ToolSchema`.

    Accepted ``parameters`` forms (falling back to the top-level schema when
    the ``parameters`` key is absent):

    1. JSON-Schema style object::

           {"type": "object",
            "properties": {"query": {"type": "string", "description": "..."}},
            "required": ["query"]}

    2. Flat ToolParameter-style list::

           [{"name": "query", "type": "string", "description": "...", "required": True}]

    Every property keeps ``name/type/description/required/enum/default`` so
    ``ToolSchema.to_dict()`` round-trips into a complete JSON Schema payload.
    """
    params = schema.get("parameters", schema)
    root_type = "object"

    if isinstance(params, dict):
        prop_map = params.get("properties", {})
        required_set = set(params.get("required") or [])
        root_type = str(params.get("type", "object"))
        if isinstance(prop_map, dict):
            properties = [
                _to_parameter(name, prop, name in required_set)
                for name, prop in prop_map.items()
            ]
        else:
            properties = []
        return ToolSchema(type=root_type, properties=properties)

    if isinstance(params, list):
        properties = []
        for item in params:
            if not isinstance(item, dict) or not item.get("name"):
                _LOGGER.warning(
                    "skipping malformed tool parameter in schema: %r", item
                )
                continue
            name = item["name"]
            properties.append(
                _to_parameter(name, item, bool(item.get("required", True)))
            )
        return ToolSchema(type=root_type, properties=properties)

    _LOGGER.warning(
        "unrecognised tool schema %r; exposing an empty parameter schema",
        type(schema.get("parameters")).__name__,
    )
    return ToolSchema(type=root_type, properties=[])


def _to_parameter(name: str, prop: dict[str, Any], required: bool) -> ToolParameter:
    """Build one :class:`ToolParameter` from a JSON-Schema property dict."""
    return ToolParameter(
        name=name,
        type=str(prop.get("type", "string")),
        description=str(prop.get("description", "")),
        required=required,
        enum=prop.get("enum"),
        default=prop.get("default"),
    )
