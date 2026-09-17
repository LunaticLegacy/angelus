"""MCP metadata, private credentials, and Session-local bindings."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..settings_module.json_store import read_json, write_json
from ..session_module import validate_session_id
from .bridge import MCPServer, MCPToolError

_SECRET_FIELDS = {"bearer_token", "oauth_client_secret", "oauth_token", "oauth_refresh_token"}
_TEMPLATE = "${project_root}"


class MCPStore:
    def __init__(self, state_root: Path) -> None:
        self._catalog = state_root / "settings" / "mcp-servers.json"
        self._secrets = state_root / "secrets" / "mcp"
        self._sessions = state_root / "sessions"

    def list(self) -> tuple[dict[str, Any], ...]: return tuple(self.public(item) for item in self._records())
    def internal(self) -> list[dict[str, Any]]: return [self._with_secrets(item) for item in self._records()]

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        record, secrets = self._normalize(payload)
        records = self._records()
        if any(x["name"] == record["name"] for x in records): raise MCPToolError("MCP server name already exists")
        records.append(record); self._write(records); self._write_secret(record["id"], secrets)
        return self.public(self._with_secrets(record))

    def replace(self, server_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        records = self._records(); index = self._index(records, server_id); existing = self._with_secrets(records[index])
        merged = dict(payload)
        for field in _SECRET_FIELDS:
            if not merged.get(field): merged[field] = existing.get(field, "")
        for field in ("headers", "env"):
            submitted = merged.get(field)
            if not submitted: merged[field] = existing.get(field, {})
            elif isinstance(submitted, dict): merged[field] = {k: existing.get(field, {}).get(k, "") if v == "" else v for k,v in submitted.items()}
        record, secrets = self._normalize(merged, server_id); records[index] = record
        self._write(records); self._write_secret(server_id, secrets); return self.public({**record, **secrets})

    def remove(self, server_id: str) -> None:
        records = self._records(); records.pop(self._index(records, server_id)); self._write(records)
        try: (self._secrets / f"{server_id}.json").unlink()
        except FileNotFoundError: pass
        for root in self._sessions.iterdir() if self._sessions.is_dir() else ():
            if root.is_dir(): self.write_bindings(root.name, [x for x in self.read_bindings(root.name) if x["server_id"] != server_id])

    def set_probe(self, server_id: str, probe: dict[str, Any], capabilities: dict[str, Any]) -> dict[str, Any]:
        records = self._records(); index = self._index(records, server_id); records[index]["probe"] = probe; records[index]["capabilities"] = capabilities; records[index]["updated_at"] = time.time(); self._write(records)
        return self.public(self._with_secrets(records[index]))

    def get_internal(self, server_id: str) -> dict[str, Any]:
        records = self._records(); return self._with_secrets(records[self._index(records, server_id)])

    def update_credentials(self, server_id: str, **values: Any) -> dict[str, Any]:
        """Replace selected private OAuth fields without exposing them."""
        records = self._records(); index = self._index(records, server_id); current = self._with_secrets(records[index])
        for key, value in values.items():
            if key not in _SECRET_FIELDS | {"oauth_expires_at"}: raise MCPToolError("unsupported MCP credential field")
            if key == "oauth_expires_at": records[index][key] = float(value or 0)
            else: current[key] = str(value or "")
        records[index]["updated_at"] = time.time()
        secrets = {key: current.get(key, "") for key in _SECRET_FIELDS} | {"headers": current.get("headers", {}), "env": current.get("env", {})}
        self._write(records); self._write_secret(server_id, secrets)
        return self.public({**records[index], **secrets})

    def public(self, record: dict[str, Any]) -> dict[str, Any]:
        return {k:v for k,v in record.items() if k not in _SECRET_FIELDS | {"headers", "env"}} | {
            "headers": sorted(record.get("headers", {})), "env": sorted(record.get("env", {})),
            "has_bearer_token": bool(record.get("bearer_token")), "oauth_connected": bool(record.get("oauth_token")),
            "credentials_configured": bool(record.get("headers") or record.get("env") or record.get("bearer_token") or record.get("oauth_token"))}

    def read_bindings(self, session_id: str) -> list[dict[str, Any]]:
        value = read_json(self._binding_path(session_id), {"schema_version": 1, "bindings": []})
        return [dict(x) for x in value.get("bindings", []) if isinstance(x, dict)] if isinstance(value, dict) else []

    def write_bindings(self, session_id: str, bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        server_ids = {x["id"] for x in self._records()}; normalized = []
        for item in bindings:
            server_id = str(item.get("server_id", "")); roles = sorted({str(x) for x in item.get("roles", []) if x in {"coordinator", "worker"}}); tools = sorted({str(x) for x in item.get("tools", []) if str(x)})
            if server_id not in server_ids or not roles: raise MCPToolError("Each MCP binding needs an existing server and at least one role")
            normalized.append({"server_id": server_id, "roles": roles, "tools": tools})
        write_json(self._binding_path(session_id), {"schema_version": 1, "bindings": normalized}); return normalized

    def resolve(self, session_id: str, project_root: Path, role: str) -> list[dict[str, Any]]:
        servers = {x["id"]: x for x in self.internal()}; result = []
        for binding in self.read_bindings(session_id):
            record = dict(servers.get(binding["server_id"], {}))
            if not record or role not in binding["roles"] or not record.get("probe", {}).get("ok"): continue
            record["args"] = [x.replace(_TEMPLATE, str(project_root)) for x in record["args"]]
            record["cwd"] = record["cwd"].replace(_TEMPLATE, str(project_root)); record["tool_allowlist"] = binding["tools"]; record["_project_root"] = str(project_root); result.append(record)
        return result

    def _records(self) -> list[dict[str, Any]]:
        value = read_json(self._catalog, {"schema_version": 1, "servers": []})
        if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("servers"), list): raise MCPToolError("invalid MCP catalog")
        return [dict(x) for x in value["servers"] if isinstance(x, dict)]
    def _write(self, records: list[dict[str, Any]]) -> None: write_json(self._catalog, {"schema_version": 1, "servers": records})
    def _write_secret(self, server_id: str, value: dict[str, Any]) -> None:
        write_json(self._secrets / f"{server_id}.json", {"schema_version": 1, **value})
        try: (self._secrets / f"{server_id}.json").chmod(0o600)
        except OSError: pass
    def _with_secrets(self, record: dict[str, Any]) -> dict[str, Any]:
        value = read_json(self._secrets / f"{record['id']}.json", {})
        return {**record, **({k:v for k,v in value.items() if k != "schema_version"} if isinstance(value, dict) else {})}
    def _binding_path(self, session_id: str) -> Path: return self._sessions / validate_session_id(session_id) / "mcp-bindings.json"
    @staticmethod
    def _index(records: list[dict[str, Any]], server_id: str) -> int:
        try: return next(i for i,x in enumerate(records) if x.get("id") == server_id)
        except StopIteration as exc: raise KeyError(server_id) from exc

    def _normalize(self, payload: dict[str, Any], server_id: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(payload, dict): raise MCPToolError("MCP server must be an object")
        transport = str(payload.get("transport", "stdio")).lower(); name = str(payload.get("name", "")).strip()
        args, headers, env = payload.get("args") or [], payload.get("headers") or {}, payload.get("env") or {}
        if not isinstance(args, list) or not all(isinstance(value, str) for value in args): raise MCPToolError("MCP args must be a string array")
        if not isinstance(headers, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in headers.items()): raise MCPToolError("MCP headers must be a string mapping")
        if not isinstance(env, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in env.items()): raise MCPToolError("MCP env must be a string mapping")
        candidate = {"name":name,"transport":transport,"command":str(payload.get("command","")).strip(),"args":args,"cwd":str(payload.get("cwd","")).strip(),"url":str(payload.get("url","")).strip(),"headers":headers,"env":env}
        forbidden=[candidate["command"],candidate["url"],str(payload.get("oauth_authorize_url","")),str(payload.get("oauth_token_url","")),str(payload.get("oauth_client_id","")),*headers.values(),*env.values(),*(str(payload.get(k,"")) for k in _SECRET_FIELDS)]
        if any(_TEMPLATE in str(x) for x in forbidden): raise MCPToolError("${project_root} is allowed only in stdio args and cwd")
        MCPServer.from_config(candidate)
        secrets = {k:str(payload.get(k,"")) for k in _SECRET_FIELDS} | {"headers":headers,"env":env}
        record = {"id":server_id or uuid4().hex, **{k:v for k,v in candidate.items() if k not in {"headers","env"}},
                  "auth_type":str(payload.get("auth_type","none")), "oauth_authorize_url":str(payload.get("oauth_authorize_url","")), "oauth_token_url":str(payload.get("oauth_token_url","")), "oauth_client_id":str(payload.get("oauth_client_id","")), "oauth_scopes":str(payload.get("oauth_scopes","")), "oauth_expires_at":float(payload.get("oauth_expires_at",0) or 0), "capabilities":payload.get("capabilities",{}) if isinstance(payload.get("capabilities",{}),dict) else {}, "probe":payload.get("probe",{}) if isinstance(payload.get("probe",{}),dict) else {}, "updated_at":time.time()}
        return record, secrets
