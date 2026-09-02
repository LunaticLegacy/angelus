"""Shared run-manifest loader for the pre-registered F1-F3 evaluators.

Every verdict row in the paper's evaluation must be traceable to one
run-manifest JSON produced by the §3 data-collection step
(``docs/paper/eval-data/{case1,case2}/run-manifest.json``).  This module
centralises the field contract so the three scripts cannot drift apart.

Schema (all timestamps in seconds since epoch unless noted):

- env: {head, date, model_profile, task_hash, dispatch_script_sha256}
- workspace_root: absolute path containing the swapped storage.WORKSPACE_ROOT
- workspace_id / session_id: identity used by _restore_swarm
- snapshot: absolute path of the preserved pre-kill swarm-runtime.json copy
- context_hashes: {agent_name: sha256_hex} captured pre-kill (F1/F2)
- metrics: F1/F3 fields (t_restore, t_redo, tokens_restore, tokens_redo,
  continue_rounds, final_status, snapshot_reload_ms, rebuild_ms)
- intervention: {timestamp, target_agent, reason} (F2)
- sibling_probe: {pre_hashes, post_hashes, control_rounds, actual_rounds,
  error_rate_pre, error_rate_post} (F2)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    """Raised when a run-manifest is missing or malformed."""


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Load and structurally validate one run manifest."""
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise ManifestError(f"manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ManifestError("manifest root must be a JSON object")
    for key in ("env", "workspace_root", "workspace_id", "session_id", "snapshot"):
        if key not in manifest:
            raise ManifestError(f"manifest missing required field: {key}")
    return manifest


def require(manifest: dict[str, Any], section: str, field: str) -> Any:
    """Return a manifest field or raise with the section/field name."""
    try:
        return manifest[section][field]
    except (KeyError, TypeError) as exc:
        raise ManifestError(f"manifest missing {section}.{field}") from exc


def resolve(root: str | Path, value: str) -> Path:
    """Resolve a manifest path against the repo root when relative."""
    path = Path(value)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[2] / path
