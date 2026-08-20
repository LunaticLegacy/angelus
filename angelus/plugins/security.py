"""Plugin security: permission gate + integrity checksum (S10).

Two responsibilities (spec ``docs/plugin-swarm-execution.md`` §4-S10,
acceptance §5-S10; contract ``docs/plugin-api.md`` §3):

1. **Permission gate** — before a plugin tool/hook/route/connector call
   crosses into a host capability, the S4–S7 bridge layers call
   :func:`check_permission` against ``plugins.json``
   ``permissions_granted`` (``"action:scope"`` strings).  Anything not
   explicitly granted is **denied and logged** — never silently allowed.

2. **Integrity checksum** — the installer records a sha256 checksum
   (``sha256:<hex>``) over the plugin's installed payload; the manager
   re-verifies **before import/setup** that neither the manifest nor the
   entry file changed by a single byte.

Design constraints:

* The module imports nothing from ``angelus`` at import time, so it can be
  loaded standalone (and the registry layer is imported lazily, mirroring
  ``angelus/plugins/manager.py``).
* Every denial path logs a structured ``PERMISSION_DENIED`` /
  ``INTEGRITY_DENIED`` line on the ``angelus.plugins.security`` logger.
* ``registry`` parameters are injectable: bridge/manager/CLI callers may
  pass any object exposing the S2 ``plugin_registry`` interface
  (``get_plugin``/``list_plugins``/``grant_permissions``); ``None`` uses the
  real ``angelus.plugin_registry`` module.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from pathlib import Path
from typing import Any

__all__ = [
    "PERMISSION_ACTIONS",
    "CHECKSUM_PATTERN",
    "MAX_SCOPE_LEN",
    "check_permission",
    "compute_checksum",
    "compute_plugin_integrity",
    "declared_permissions",
    "format_grant",
    "get_logger",
    "grant_permission",
    "granted_permissions",
    "redact_connector",
    "require_permission",
    "verify_checksum",
    "verify_plugin_integrity",
]

#: The nine permission actions of the v1 contract (docs/plugin-api.md §3).
#: Every action requires a scope string (1..512 chars).
PERMISSION_ACTIONS: tuple[str, ...] = (
    "shell",
    "network",
    "fs.read",
    "fs.write",
    "env",
    "http",
    "connector.read",
    "connector.write",
    "event.subscribe",
)

#: ``manifest.checksum`` / ``plugins.json[].checksum`` wire format.
CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

MAX_SCOPE_LEN = 512

_LOGGER_NAME = "angelus.plugins.security"
_logger: logging.Logger | None = None

#: Secrets never exposed through the public connector view (S7 boundary).
_SECRET_HINTS = ("key", "secret", "token", "password", "credential")


def get_logger() -> logging.Logger:
    """Return the module logger (``angelus.plugins.security``)."""
    global _logger
    if _logger is None:
        _logger = logging.getLogger(_LOGGER_NAME)
    return _logger


def _default_registry() -> Any:
    """Lazily import the real S2 registry module (importable standalone)."""
    import angelus.plugin_registry  # noqa: PLC0415

    return angelus.plugin_registry


def _audit(level: int, event: str, **fields: Any) -> None:
    """Emit a structured audit line: ``SECURITY <EVENT> k=v k=v ...``."""
    detail = " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
    get_logger().log(level, "SECURITY %s %s", event, detail)


# ---------------------------------------------------------------------------
# permission gate
# ---------------------------------------------------------------------------
def format_grant(action: str, scope: str) -> str:
    """Render a grant as the canonical ``"action:scope"`` string."""
    return f"{action}:{scope}"


def declared_permissions(manifest: dict[str, Any]) -> frozenset[str]:
    """Return the ``"action:scope"`` set a manifest *declares*.

    Declaring a permission is not granting it — runtime access is decided
    solely by ``permissions_granted`` in ``plugins.json``.  This helper is
    used by the install flow to build the confirmation prompt.
    """
    declared: set[str] = set()
    if not isinstance(manifest, dict):
        return frozenset()
    for item in manifest.get("permissions") or []:
        if not isinstance(item, dict):
            continue
        action = item.get("action")
        scope = item.get("scope")
        if isinstance(action, str) and action in PERMISSION_ACTIONS and isinstance(scope, str) and scope:
            declared.add(format_grant(action, scope))
    return frozenset(declared)


def granted_permissions(plugin_id: str, registry: Any = None) -> frozenset[str]:
    """Return the ``permissions_granted`` set for a plugin record.

    Args:
        plugin_id: The 32-hex registry id (or manifest name).
        registry: Injectable registry; ``None`` uses ``angelus.plugin_registry``.
    """
    record = _lookup_record(plugin_id, registry)
    if record is None:
        return frozenset()
    granted = record.get("permissions_granted")
    if not isinstance(granted, list):
        return frozenset()
    return frozenset(str(item) for item in granted if isinstance(item, str))


def _lookup_record(plugin_id: str, registry: Any = None) -> dict[str, Any] | None:
    """Resolve a plugin record by id, falling back to a name scan.

    Registry failures never crash the gate — they surface as ``None`` so the
    caller denies and logs (fail closed).
    """
    reg = registry
    if reg is None:
        try:
            reg = _default_registry()
        except Exception as exc:  # registry layer not available -> fail closed
            _audit(
                logging.ERROR,
                "REGISTRY_UNUSABLE",
                plugin=str(plugin_id),
                reason="registry-unavailable",
                error=str(exc),
            )
            return None
    get_plugin = getattr(reg, "get_plugin", None)
    if callable(get_plugin):
        try:
            record = get_plugin(plugin_id)
            if isinstance(record, dict):
                return record
        except Exception as exc:  # registry must not crash the gate
            _audit(logging.ERROR, "REGISTRY_LOOKUP_FAILED", plugin=plugin_id, error=str(exc))
            return None
    list_plugins = getattr(reg, "list_plugins", None)
    if not callable(list_plugins):
        _audit(logging.ERROR, "REGISTRY_UNUSABLE", plugin=plugin_id, reason="no list_plugins")
        return None
    try:
        for item in list_plugins():
            if not isinstance(item, dict):
                continue
            if item.get("id") == plugin_id or item.get("name") == plugin_id:
                return item
    except Exception as exc:
        _audit(logging.ERROR, "REGISTRY_LOOKUP_FAILED", plugin=plugin_id, error=str(exc))
    return None


def check_permission(
    plugin_id: str,
    action: str,
    scope: str,
    registry: Any = None,
) -> bool:
    """Gate one plugin capability call against ``permissions_granted``.

    Denies (and logs) when:

    * ``action`` is not one of the nine :data:`PERMISSION_ACTIONS`;
    * ``scope`` is not a string of 1..512 characters;
    * the plugin is not installed in the registry, or is disabled;
    * the exact ``"action:scope"`` grant is absent from
      ``permissions_granted`` (declaring a permission is *not* granting it).

    Bridge layers must call this immediately before the capability is
    exercised (e.g. ``shell`` → subprocess spawn, ``fs.read`` → open,
    ``event.subscribe`` → hook registration).  Never silently allow.
    """
    if action not in PERMISSION_ACTIONS:
        _audit(
            logging.ERROR,
            "PERMISSION_DENIED",
            plugin=plugin_id,
            action=str(action),
            scope=str(scope),
            reason="unknown-action",
            allowed=",".join(PERMISSION_ACTIONS),
        )
        return False
    if not isinstance(scope, str) or not scope or len(scope) > MAX_SCOPE_LEN:
        _audit(
            logging.ERROR,
            "PERMISSION_DENIED",
            plugin=plugin_id,
            action=action,
            scope=str(scope),
            reason="invalid-scope",
            rule=f"scope must be a string of 1..{MAX_SCOPE_LEN} characters",
        )
        return False

    record = _lookup_record(plugin_id, registry)
    if record is None:
        _audit(
            logging.WARNING,
            "PERMISSION_DENIED",
            plugin=plugin_id,
            action=action,
            scope=scope,
            reason="not-installed",
        )
        return False
    if record.get("enabled") is not True:
        _audit(
            logging.WARNING,
            "PERMISSION_DENIED",
            plugin=plugin_id,
            action=action,
            scope=scope,
            reason="plugin-disabled",
        )
        return False

    granted = record.get("permissions_granted")
    requested = format_grant(action, scope)
    if isinstance(granted, list) and requested in granted:
        _audit(logging.DEBUG, "PERMISSION_GRANTED", plugin=plugin_id, action=action, scope=scope)
        return True

    _audit(
        logging.WARNING,
        "PERMISSION_DENIED",
        plugin=plugin_id,
        action=action,
        scope=scope,
        reason="not-granted",
        granted=",".join(granted) if isinstance(granted, list) else "<none>",
        hint="declare in manifest.permissions and grant at install/enable time",
    )
    return False


def require_permission(
    plugin_id: str,
    action: str,
    scope: str,
    registry: Any = None,
) -> None:
    """Like :func:`check_permission` but raises ``PermissionError`` on denial.

    Useful for bridges that prefer exception semantics (e.g. hook
    registration rejecting a non-whitelisted event).
    """
    if not check_permission(plugin_id, action, scope, registry=registry):
        raise PermissionError(
            f"plugin {plugin_id!r} lacks permission {format_grant(action, scope)}"
        )


def grant_permission(
    plugin_id: str,
    action: str,
    scope: str,
    registry: Any = None,
) -> dict[str, Any] | None:
    """Validate and persist one ``"action:scope"`` grant.

    Validation mirrors :func:`check_permission` (action ∈ 9 enum, scope
    1..512).  Delegates persistence to the registry's
    ``grant_permissions(plugin_id, [grant])`` so existing grants are merged,
    never overwritten.  Returns the updated record, or ``None`` when the
    plugin is not installed.
    """
    if action not in PERMISSION_ACTIONS:
        raise ValueError(f"unknown permission action {action!r}; allowed: {', '.join(PERMISSION_ACTIONS)}")
    if not isinstance(scope, str) or not scope or len(scope) > MAX_SCOPE_LEN:
        raise ValueError(f"scope must be a string of 1..{MAX_SCOPE_LEN} characters")

    reg = registry
    if reg is None:
        try:
            reg = _default_registry()
        except Exception as exc:
            raise RuntimeError("plugin registry is unavailable") from exc
    grant_fn = getattr(reg, "grant_permissions", None)
    if not callable(grant_fn):
        raise TypeError("registry does not expose grant_permissions()")
    record = grant_fn(plugin_id, [format_grant(action, scope)])
    if isinstance(record, dict):
        _audit(logging.INFO, "PERMISSION_GRANTED", plugin=plugin_id, action=action, scope=scope)
    return record


# ---------------------------------------------------------------------------
# integrity checksum
# ---------------------------------------------------------------------------
def compute_checksum(path: Path | str) -> str:
    """Return ``"sha256:<hex>"`` of a single file's bytes."""
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"sha256:{digest}"


def verify_checksum(path: Path | str, expected: str | None) -> bool:
    """Return ``True`` when the file's sha256 equals ``expected``.

    Malformed expectations and unreadable files return ``False`` (deny).
    """
    if not isinstance(expected, str) or not CHECKSUM_PATTERN.fullmatch(expected):
        return False
    try:
        actual = compute_checksum(path)
    except OSError:
        return False
    return hmac.compare_digest(actual, expected)


def _canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    """Canonical JSON bytes of the manifest with ``checksum`` excluded.

    The checksum field is excluded so the recorded value can live *inside*
    the manifest without circularity; whitespace and key order are
    normalised, so any value change (even one byte) alters these bytes.
    """
    payload = dict(manifest)
    payload.pop("checksum", None)
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _resolve_entry_path(
    plugin_dir: Path | str, manifest: dict[str, Any]
) -> Path | None:
    """Resolve ``manifest.entry`` to an existing file inside ``plugin_dir``.

    Handles ``module`` (``plugin`` / ``plugin.py``) and ``package``
    (``pkg/__init__.py``) entry forms, and guards against path traversal —
    the resolved file must stay within the plugin directory.
    """
    base = Path(plugin_dir).resolve()
    entry = manifest.get("entry")
    if not isinstance(entry, str) or not entry:
        return None
    entry_type = manifest.get("entry_type") or "module"
    raw = Path(entry)
    if entry_type == "package":
        candidates = [raw / "__init__.py", raw / "main.py"]
    else:
        candidates = [raw]
        if raw.suffix != ".py":
            candidates.append(Path(f"{entry}.py"))
        candidates.append(raw / "__init__.py")

    for candidate in candidates:
        try:
            resolved = (base / candidate).resolve()
        except OSError:
            continue
        if resolved != base and not resolved.is_relative_to(base):
            continue  # traversal attempt
        if resolved.is_file():
            return resolved
    return None


def compute_plugin_integrity(
    plugin_dir: Path | str, manifest: dict[str, Any]
) -> str:
    """Compute the install-time integrity checksum for a plugin.

    The checksum covers the **installed payload**: canonical manifest bytes
    (``checksum`` field excluded) concatenated with the entry file bytes.
    A one-byte change to either the manifest or the entry therefore produces
    a different checksum.  The installer stores the returned
    ``"sha256:<hex>"`` in both ``manifest.checksum`` and
    ``plugins.json[].checksum``.

    Raises:
        ValueError: when the manifest has no usable ``entry`` or the entry
            file is missing inside ``plugin_dir``.
    """
    entry_path = _resolve_entry_path(plugin_dir, manifest)
    if entry_path is None:
        raise ValueError(
            f"cannot resolve entry {manifest.get('entry')!r} under {plugin_dir}"
        )
    blob = _canonical_manifest_bytes(manifest) + b"\n" + entry_path.read_bytes()
    return f"sha256:{hashlib.sha256(blob).hexdigest()}"


def verify_plugin_integrity(
    plugin_dir: Path | str,
    manifest: dict[str, Any],
    *,
    expected: str | None = None,
) -> tuple[bool, list[str]]:
    """Verify a plugin's manifest + entry are untouched since install.

    Called by the manager **before** ``import``/``setup`` and by the CLI at
    install/re-install time.  ``expected`` defaults to ``manifest.checksum``;
    callers that also hold the registry record may pass its ``checksum`` for
    cross-checking (defence in depth against registry-tampered plugins).

    Returns ``(ok, errors)``; on failure the rejection is logged at ERROR
    level (audit trail — denials are never silent).
    """
    errors: list[str] = []
    plugin_name = manifest.get("name") if isinstance(manifest, dict) else None

    if not isinstance(manifest, dict):
        errors.append("manifest must be a JSON object")
        _audit(
            logging.ERROR,
            "INTEGRITY_DENIED",
            plugin=str(plugin_name),
            plugin_dir=str(plugin_dir),
            reason="invalid-manifest",
        )
        return False, errors

    expected_value = expected if expected is not None else manifest.get("checksum")
    if not isinstance(expected_value, str) or not CHECKSUM_PATTERN.fullmatch(expected_value):
        errors.append(
            "no valid sha256 checksum recorded; refusing to load an un-checksummed plugin"
        )
        _audit(
            logging.ERROR,
            "INTEGRITY_DENIED",
            plugin=str(plugin_name),
            plugin_dir=str(plugin_dir),
            reason="missing-checksum",
            checksum=str(expected_value),
        )
        return False, errors

    entry_path = _resolve_entry_path(plugin_dir, manifest)
    if entry_path is None:
        errors.append(
            f"entry {manifest.get('entry')!r} does not resolve to a file under {plugin_dir}"
        )
        _audit(
            logging.ERROR,
            "INTEGRITY_DENIED",
            plugin=str(plugin_name),
            plugin_dir=str(plugin_dir),
            reason="entry-unresolvable",
            entry=str(manifest.get("entry")),
        )
        return False, errors

    try:
        recomputed = compute_plugin_integrity(plugin_dir, manifest)
    except (OSError, ValueError) as exc:
        errors.append(f"integrity check failed: {exc}")
        _audit(
            logging.ERROR,
            "INTEGRITY_DENIED",
            plugin=str(plugin_name),
            plugin_dir=str(plugin_dir),
            reason="read-error",
            error=str(exc),
        )
        return False, errors

    if not hmac.compare_digest(recomputed, expected_value):
        errors.append(
            "checksum mismatch: manifest or entry modified since install"
        )
        _audit(
            logging.ERROR,
            "INTEGRITY_DENIED",
            plugin=str(plugin_name),
            plugin_dir=str(plugin_dir),
            reason="checksum-mismatch",
            expected=expected_value,
            actual=recomputed,
            entry=str(entry_path),
        )
        return False, errors

    _audit(logging.INFO, "INTEGRITY_OK", plugin=str(plugin_name), plugin_dir=str(plugin_dir))
    return True, []


# ---------------------------------------------------------------------------
# connector redaction boundary (S7)
# ---------------------------------------------------------------------------
def redact_connector(record: dict[str, Any]) -> dict[str, Any]:
    """Return browser-safe connector metadata without credentials.

    The canonical redaction is ``angelus.connectors._public_connector``
    (RSA-OAEP-encrypted keys are never decrypted for the public view).  If
    that module is unavailable a local fallback strips any field whose name
    hints at a secret.  Plugin ``connector.read`` access must go through this
    boundary — plugin code never sees decrypted connector keys.
    """
    if isinstance(record, dict):
        try:
            from angelus.connectors import _public_connector  # noqa: PLC0415

            return _public_connector(record)
        except Exception:  # noqa: BLE001 - fall back to local redaction
            pass
        lowered = {str(key).lower(): key for key in record}
        return {
            key: value
            for key, value in dict(record).items()
            if not any(hint in str(key).lower() for hint in _SECRET_HINTS)
        }
    return {}
