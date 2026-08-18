"""Encrypted connector storage for the Angelus browser control plane."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from . import storage
from .classes import RunConfig
from .storage import _safe_id



def _connector_key_paths() -> tuple[Path, Path]:
    """Return the per-store RSA private/public key paths."""
    key_directory = storage.CONNECTOR_INDEX.parent / ".connector-keys"
    return key_directory / "private.pem", key_directory / "public.pem"

def _ensure_connector_keypair() -> tuple[Path, Path]:
    """Create a local RSA-OAEP keypair with OS-user-only permissions."""
    private_key, public_key = _connector_key_paths()
    if private_key.exists() and public_key.exists():
        return private_key, public_key
    private_key.parent.mkdir(parents=True, exist_ok=True)
    try:
        private_key.parent.chmod(0o700)
    except OSError:
        pass
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:3072", "-out", str(private_key)],
        check=True, capture_output=True,
    )
    try:
        private_key.chmod(0o600)
    except OSError:
        pass
    subprocess.run(
        ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True, capture_output=True,
    )
    return private_key, public_key

def _encrypt_connector_key(secret: str) -> dict[str, str]:
    """Encrypt a normal-size API key with the local RSA public key."""
    if not secret:
        return {"algorithm": "RSA-OAEP-SHA256", "ciphertext": ""}
    _, public_key = _ensure_connector_keypair()
    try:
        encrypted = subprocess.run(
            ["openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", str(public_key), "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256"],
            input=secret.encode("utf-8"), check=True, capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise ValueError("API Key exceeds the RSA encryption limit or OpenSSL failed") from exc
    return {"algorithm": "RSA-OAEP-SHA256", "ciphertext": base64.b64encode(encrypted).decode("ascii")}

def _decrypt_connector_key(payload: Any) -> str:
    """Decrypt the encrypted connector key only inside the server process."""
    if not isinstance(payload, dict) or not payload.get("ciphertext"):
        return ""
    if payload.get("algorithm") != "RSA-OAEP-SHA256":
        raise ValueError("unsupported connector key encryption")
    private_key, _ = _ensure_connector_keypair()
    try:
        ciphertext = base64.b64decode(str(payload["ciphertext"]), validate=True)
        return subprocess.run(
            ["openssl", "pkeyutl", "-decrypt", "-inkey", str(private_key), "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256"],
            input=ciphertext, check=True, capture_output=True,
        ).stdout.decode("utf-8")
    except (ValueError, UnicodeDecodeError, subprocess.CalledProcessError) as exc:
        raise ValueError("cannot decrypt connector API key") from exc

def _read_connector_records() -> list[dict[str, Any]]:
    """Read encrypted connector records exactly as stored on disk."""
    if not storage.CONNECTOR_INDEX.exists():
        return []
    try:
        records = json.loads(storage.CONNECTOR_INDEX.read_text(encoding="utf-8"))
        return records if isinstance(records, list) else []
    except (OSError, json.JSONDecodeError):
        return []

def _read_connectors() -> list[dict[str, Any]]:
    """Load and decrypt saved connector records for internal server use."""
    records: list[dict[str, Any]] = []
    for stored in _read_connector_records():
        if not isinstance(stored, dict):
            continue
        record = dict(stored)
        encrypted = record.pop("api_key_encrypted", None)
        if encrypted is not None:
            record["api_key"] = _decrypt_connector_key(encrypted)
        # Legacy plaintext entries remain readable and are encrypted on their
        # next write; public APIs below never expose this field.
        records.append(record)
    return records

def _write_connectors(connectors: list[dict[str, Any]]) -> None:
    """Atomically persist connectors with RSA-OAEP encrypted credentials.

    Args:
        connectors: Complete connector collection replacing the prior store.

    Side Effects:
        Creates or replaces ``storage.CONNECTOR_INDEX`` and attempts to set mode 0600
        before the atomic replacement.
    """
    stored: list[dict[str, Any]] = []
    for connector in connectors:
        record = dict(connector)
        record["api_key_encrypted"] = _encrypt_connector_key(str(record.pop("api_key", "")))
        stored.append(record)
    temporary = storage.CONNECTOR_INDEX.with_suffix(".tmp")
    temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(storage.CONNECTOR_INDEX)

def _public_connector(record: dict[str, Any]) -> dict[str, Any]:
    """Return browser-safe connector metadata without its credential."""
    return {
        "id": str(record.get("id", "")),
        "name": str(record.get("name", "")),
        "provider": str(record.get("provider", "openai")),
        "model": str(record.get("model", "")),
        "api_url": str(record.get("api_url", "")),
        "has_api_key": bool(record.get("api_key", "")),
    }

def _resolve_connector_key(config: RunConfig) -> RunConfig:
    """Resolve a selected connector credential only for the impending run."""
    if not config.connector_id:
        return config
    connector_id = _safe_id(config.connector_id, "connector")
    connector = next((item for item in _read_connectors() if item.get("id") == connector_id), None)
    if connector is None:
        raise HTTPException(status_code=404, detail="选择的连接器不存在")
    return config.model_copy(update={"api_key": str(connector.get("api_key", ""))})

__all__ = [
    "_connector_key_paths",
    "_ensure_connector_keypair",
    "_encrypt_connector_key",
    "_decrypt_connector_key",
    "_read_connector_records",
    "_read_connectors",
    "_write_connectors",
    "_public_connector",
    "_resolve_connector_key",
]
