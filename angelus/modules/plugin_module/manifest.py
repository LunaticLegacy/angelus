"""Strict manifest decoding for non-executing plugin discovery."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import re

from .models import (
    PluginManifest,
    PluginPermission,
    PluginSettingField,
    PluginSettingScalar,
    PluginTheme,
)


_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_SETTING = re.compile(r"^[a-z][a-z0-9_-]{0,119}$")
_ASSET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_SENSITIVE = ("api_key", "apikey", "token", "password", "secret", "credential")


class ManifestError(ValueError):
    """Raised when a plugin package fails declarative manifest validation."""


def load_manifest(package_path: Path) -> PluginManifest:
    """Decode one package manifest without importing plugin code.

    Args:
        package_path: Managed plugin package directory containing
            ``manifest.json``.

    Returns:
        Fully typed manifest ready for safe discovery or later loading.

    Raises:
        ManifestError: If JSON is malformed or violates the v1 contract.
    """
    path = package_path / "manifest.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read manifest: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ManifestError("manifest must be a JSON object")
    return _decode_manifest(raw)


def _text(raw: Mapping[str, object], key: str, *, required: bool = False, maximum: int = 2_000) -> str:
    """Read one bounded manifest text field.

    Args:
        raw: Raw decoded manifest object.
        key: Field name to read.
        required: Whether an empty/missing value is invalid.
        maximum: Maximum accepted character count.

    Returns:
        Validated text, or an empty string for an optional absent field.

    Raises:
        ManifestError: If the field has the wrong type or length.
    """
    value = raw.get(key, "")
    if not isinstance(value, str) or len(value) > maximum or (required and not value):
        raise ManifestError(f"{key} must be {'a non-empty ' if required else 'a '}string of at most {maximum} characters")
    return value


def _decode_manifest(raw: Mapping[str, object]) -> PluginManifest:
    """Validate supported v1 fields and assemble the immutable manifest.

    Args:
        raw: Raw JSON object decoded from ``manifest.json``.

    Returns:
        Typed plugin manifest.

    Raises:
        ManifestError: If a supported field is invalid or unknown fields exist.
    """
    allowed = {"name", "display_name", "version", "api_version", "kind", "entry", "description", "permissions", "frontend", "settings_schema"}
    unknown = sorted(str(key) for key in raw if key not in allowed)
    if unknown:
        raise ManifestError(f"unknown manifest fields: {', '.join(unknown)}")
    name = _text(raw, "name", required=True, maximum=64)
    if not _NAME.fullmatch(name):
        raise ManifestError("name must match ^[a-z][a-z0-9_-]{1,63}$")
    version = _text(raw, "version", required=True, maximum=32)
    if not _VERSION.fullmatch(version):
        raise ManifestError("version must be semantic x.y.z")
    api_version = _text(raw, "api_version", required=True, maximum=16)
    if api_version != "1":
        raise ManifestError("api_version must be '1'")
    kind = raw.get("kind", "tool")
    if kind not in {"tool", "ui", "theme_pack"}:
        raise ManifestError("kind must be tool, ui, or theme_pack")
    entry = raw.get("entry")
    if kind == "tool":
        if not isinstance(entry, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entry):
            raise ManifestError("tool plugin entry must be a Python module name")
    elif entry is not None:
        raise ManifestError("only tool plugins may declare entry")
    frontend = raw.get("frontend", {})
    if not isinstance(frontend, Mapping):
        raise ManifestError("frontend must be an object")
    assets = _assets(frontend.get("assets", ()))
    themes = _themes(frontend.get("themes", ()), assets, kind)
    settings_enabled = frontend.get("settings", False)
    if not isinstance(settings_enabled, bool):
        raise ManifestError("frontend.settings must be boolean")
    schema = _settings(raw.get("settings_schema", ()))
    if schema and not settings_enabled:
        raise ManifestError("settings_schema requires frontend.settings=true")
    return PluginManifest(
        name=name,
        display_name=_text(raw, "display_name", maximum=120) or name,
        version=version,
        api_version=api_version,
        kind=kind,
        entry=entry if isinstance(entry, str) else None,
        description=_text(raw, "description", maximum=2_000),
        permissions=_permissions(raw.get("permissions", ())),
        assets=assets,
        settings_enabled=settings_enabled,
        settings_schema=schema,
        themes=themes,
    )


def _permissions(value: object) -> tuple[PluginPermission, ...]:
    """Decode requested capability pairs.

    Args:
        value: Raw JSON permissions array.

    Returns:
        Immutable requested permissions.

    Raises:
        ManifestError: If an item is not a bounded action/scope pair.
    """
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ManifestError("permissions must be an array")
    result: list[PluginPermission] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ManifestError("every permission must be an object")
        action, scope = item.get("action"), item.get("scope")
        if not isinstance(action, str) or not action or len(action) > 80 or not isinstance(scope, str) or not scope or len(scope) > 500:
            raise ManifestError("permission action and scope must be bounded strings")
        result.append(PluginPermission(action, scope))
    return tuple(result)


def _assets(value: object) -> tuple[str, ...]:
    """Validate static assets that may be served by the host.

    Args:
        value: Raw asset list.

    Returns:
        Normalized immutable relative asset paths.

    Raises:
        ManifestError: If an asset escapes its package or is duplicated.
    """
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ManifestError("frontend.assets must be an array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not _ASSET.fullmatch(item) or item.startswith("/") or ".." in Path(item).parts:
            raise ManifestError("frontend asset must be a safe relative path")
        if item in result:
            raise ManifestError("frontend assets must be unique")
        result.append(item)
    return tuple(result)


def _themes(value: object, assets: tuple[str, ...], kind: object) -> tuple[PluginTheme, ...]:
    """Decode a theme-pack's named CSS variants.

    Args:
        value: Raw theme definitions.
        assets: Validated static whitelist.
        kind: Declared plugin kind.

    Returns:
        Typed skins for the plugin.

    Raises:
        ManifestError: If skins are invalid or inconsistent with package kind.
    """
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ManifestError("frontend.themes must be an array")
    result: list[PluginTheme] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ManifestError("every theme must be an object")
        theme_id, title, asset, mode = item.get("id"), item.get("title"), item.get("asset"), item.get("mode")
        if not isinstance(theme_id, str) or not _NAME.fullmatch(theme_id) or not isinstance(title, str) or not title or len(title) > 120:
            raise ManifestError("theme id and title are invalid")
        if not isinstance(asset, str) or asset not in assets or not asset.endswith(".css"):
            raise ManifestError("theme asset must be a whitelisted CSS file")
        if mode not in {"dark", "light"}:
            raise ManifestError("theme mode must be dark or light")
        if any(theme.id == theme_id for theme in result):
            raise ManifestError("theme ids must be unique")
        result.append(PluginTheme(theme_id, title, asset, mode))
    if kind == "theme_pack" and not result:
        raise ManifestError("theme_pack requires at least one frontend theme")
    if kind != "theme_pack" and result:
        raise ManifestError("only theme_pack may declare frontend themes")
    return tuple(result)


def _settings(value: object) -> tuple[PluginSettingField, ...]:
    """Decode the restricted scalar settings schema.

    Args:
        value: Raw schema field list.

    Returns:
        Typed immutable schema fields.

    Raises:
        ManifestError: If a field is unknown, credential-shaped, or ill typed.
    """
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ManifestError("settings_schema must be an array")
    fields: list[PluginSettingField] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ManifestError("every settings_schema item must be an object")
        allowed = {"key", "type", "title", "description", "required", "default", "enum", "minimum", "maximum", "format"}
        if any(key not in allowed for key in raw):
            raise ManifestError("settings_schema contains an unknown field property")
        key, field_type = raw.get("key"), raw.get("type")
        if not isinstance(key, str) or not _SETTING.fullmatch(key) or any(token in key.replace("-", "_").lower() for token in _SENSITIVE):
            raise ManifestError("settings key is invalid or credential-shaped")
        if field_type not in {"string", "integer", "number", "boolean"}:
            raise ManifestError("settings type is invalid")
        default = raw.get("default")
        if "default" in raw and not _matches(default, field_type):
            raise ManifestError(f"settings default does not match {key} type")
        choices_raw = raw.get("enum", ())
        if not isinstance(choices_raw, Sequence) or isinstance(choices_raw, str) or any(not _matches(item, field_type) for item in choices_raw):
            raise ManifestError("settings enum must contain values of the declared type")
        choices = tuple(choices_raw)
        minimum, maximum = raw.get("minimum"), raw.get("maximum")
        if minimum is not None and (field_type not in {"integer", "number"} or not _matches(minimum, field_type)):
            raise ManifestError("settings minimum is numeric only")
        if maximum is not None and (field_type not in {"integer", "number"} or not _matches(maximum, field_type)):
            raise ManifestError("settings maximum is numeric only")
        if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)) and minimum > maximum:
            raise ManifestError("settings minimum must not exceed maximum")
        format_value = raw.get("format")
        if format_value is not None and (field_type != "string" or format_value != "uri"):
            raise ManifestError("settings format supports only string uri")
        if any(field.key == key for field in fields):
            raise ManifestError("settings keys must be unique")
        fields.append(PluginSettingField(
            key=key, value_type=field_type, title=_plain(raw.get("title"), 120),
            description=_plain(raw.get("description"), 1_000), required=raw.get("required", False) is True,
            default=default if "default" in raw else None, choices=choices,
            minimum=minimum if isinstance(minimum, (int, float)) else None,
            maximum=maximum if isinstance(maximum, (int, float)) else None,
            value_format=format_value if format_value == "uri" else None,
        ))
    return tuple(fields)


def _plain(value: object, maximum: int) -> str:
    """Return a bounded optional presentation string.

    Args:
        value: Raw optional field value.
        maximum: Maximum permitted character count.

    Returns:
        Empty string or the supplied presentation text.

    Raises:
        ManifestError: If a non-string or oversized text is supplied.
    """
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > maximum:
        raise ManifestError("settings presentation text is invalid")
    return value


def _matches(value: object, field_type: object) -> bool:
    """Check one raw scalar against a declared schema type.

    Args:
        value: Candidate scalar.
        field_type: Manifest scalar type name.

    Returns:
        Whether the candidate matches the exact supported scalar type.
    """
    if field_type == "string":
        return isinstance(value, str)
    if field_type == "boolean":
        return isinstance(value, bool)
    if field_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, (int, float)) and not isinstance(value, bool)
