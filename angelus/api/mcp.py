"""Thin HTTP adapter for the core-owned managed MCP service."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request as URLRequest, urlopen
from fastapi import APIRouter, Body, HTTPException, Request, Response

from ..modules.mcp_module import MCPToolError

router = APIRouter()


def _service(request: Request): return request.app.state.angelus_core.mcp_service
def _pending_path(request: Request): return request.app.state.angelus_core.state_root / "secrets" / "mcp-oauth-pending.json"
def _pending(request: Request) -> dict[str, Any]:
    try:
        value=json.loads(_pending_path(request).read_text(encoding="utf-8")); return value if isinstance(value,dict) else {}
    except (OSError,json.JSONDecodeError): return {}
def _write_pending(request: Request, value: dict[str, Any]) -> None:
    from ..modules.settings_module.json_store import write_json
    path=_pending_path(request); write_json(path,value)
    try: path.chmod(0o600)
    except OSError: pass
def _call(operation):
    try: return operation()
    except KeyError as exc: raise HTTPException(404, "MCP server not found") from exc
    except (ValueError, MCPToolError) as exc: raise HTTPException(422, str(exc)) from exc


@router.get("/api/mcp/servers")
def list_servers(request: Request): return {"servers": list(_service(request).list_servers())}

@router.post("/api/mcp/servers", status_code=201)
def create_server(request: Request, payload: dict[str, Any] = Body(...)): return _call(lambda: _service(request).create_server(payload))

@router.put("/api/mcp/servers/{server_id}")
def replace_server(server_id: str, request: Request, payload: dict[str, Any] = Body(...)): return _call(lambda: _service(request).replace_server(server_id,payload))

@router.delete("/api/mcp/servers/{server_id}", status_code=204)
def remove_server(server_id: str, request: Request): _call(lambda: _service(request).remove_server(server_id)); return Response(status_code=204)

@router.post("/api/mcp/servers/{server_id}/probe")
def probe_server(server_id: str, request: Request): return _call(lambda: _service(request).probe(server_id))

@router.get("/api/mcp/servers/{server_id}/capabilities")
def capabilities(server_id: str, request: Request):
    record=_call(lambda:_service(request).store.get_internal(server_id)); return {"capabilities":record.get("capabilities",{}),"probe":record.get("probe",{})}

@router.get("/api/sessions/{session_id}/mcp-bindings")
def get_bindings(session_id: str, request: Request): return _call(lambda:{"bindings":_service(request).bindings(session_id)})

@router.put("/api/sessions/{session_id}/mcp-bindings")
def put_bindings(session_id: str, request: Request, payload: dict[str, Any] = Body(...)):
    bindings=payload.get("bindings",[])
    if not isinstance(bindings,list): raise HTTPException(422,"bindings must be an array")
    return _call(lambda:{"bindings":_service(request).replace_bindings(session_id,bindings)})

@router.post("/api/mcp/servers/{server_id}/oauth/connect")
def oauth_connect(server_id: str, request: Request, payload: dict[str, Any] = Body(...)):
    record=_call(lambda:_service(request).store.get_internal(server_id)); redirect_uri=str(payload.get("redirect_uri","")).strip()
    authorize_url=str(record.get("oauth_authorize_url","")); client_id=str(record.get("oauth_client_id",""))
    if not authorize_url.startswith(("https://","http://localhost","http://127.0.0.1")) or not client_id or not redirect_uri: raise HTTPException(422,"OAuth authorize URL, client ID, and redirect URI are required")
    state=secrets.token_urlsafe(32); verifier=secrets.token_urlsafe(64); challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    pending=_pending(request); pending[state]={"server_id":server_id,"verifier":verifier,"redirect_uri":redirect_uri,"created_at":time.time()}; _write_pending(request,pending)
    query=urlencode({"response_type":"code","client_id":client_id,"redirect_uri":redirect_uri,"scope":record.get("oauth_scopes",""),"state":state,"code_challenge":challenge,"code_challenge_method":"S256"})
    return {"authorization_url":f"{authorize_url}{'&' if '?' in authorize_url else '?'}{query}","state":state}

@router.get("/api/mcp/oauth/callback")
def oauth_callback(state: str, code: str, request: Request):
    pending=_pending(request); transaction=pending.pop(state,None); _write_pending(request,pending)
    if not transaction or time.time()-float(transaction.get("created_at",0))>300: raise HTTPException(400,"OAuth state is invalid or expired")
    record=_call(lambda:_service(request).store.get_internal(transaction["server_id"])); token_url=str(record.get("oauth_token_url",""))
    if not token_url.startswith(("https://","http://localhost","http://127.0.0.1")): raise HTTPException(422,"OAuth token URL is invalid")
    form={"grant_type":"authorization_code","code":code,"redirect_uri":transaction["redirect_uri"],"client_id":record.get("oauth_client_id",""),"code_verifier":transaction["verifier"]}
    if record.get("oauth_client_secret"): form["client_secret"]=record["oauth_client_secret"]
    try:
        with urlopen(URLRequest(token_url,data=urlencode(form).encode(),headers={"Content-Type":"application/x-www-form-urlencoded"}),timeout=30) as response: token=json.loads(response.read().decode())
    except Exception as exc: raise HTTPException(502,f"OAuth token exchange failed: {exc}") from exc
    if not token.get("access_token"): raise HTTPException(502,"OAuth response did not contain an access token")
    _service(request).invalidate(); return _service(request).store.update_credentials(record["id"],oauth_token=token["access_token"],oauth_refresh_token=token.get("refresh_token",""),oauth_expires_at=time.time()+float(token.get("expires_in",0) or 0))

@router.post("/api/mcp/servers/{server_id}/oauth/disconnect")
def oauth_disconnect(server_id: str, request: Request):
    _service(request).invalidate(); return _call(lambda:_service(request).store.update_credentials(server_id,oauth_token="",oauth_refresh_token="",oauth_expires_at=0))

@router.post("/api/mcp/servers/{server_id}/oauth/refresh")
def oauth_refresh(server_id: str, request: Request):
    record=_call(lambda:_service(request).store.get_internal(server_id)); refresh=str(record.get("oauth_refresh_token",""))
    if not refresh: raise HTTPException(409,"No OAuth refresh token is configured")
    form={"grant_type":"refresh_token","refresh_token":refresh,"client_id":record.get("oauth_client_id","")}
    if record.get("oauth_client_secret"): form["client_secret"]=record["oauth_client_secret"]
    try:
        with urlopen(URLRequest(str(record.get("oauth_token_url","")),data=urlencode(form).encode(),headers={"Content-Type":"application/x-www-form-urlencoded"}),timeout=30) as response: token=json.loads(response.read().decode())
    except Exception as exc: raise HTTPException(502,f"OAuth refresh failed: {exc}") from exc
    if not token.get("access_token"): raise HTTPException(502,"OAuth refresh did not return an access token")
    _service(request).invalidate(); return _service(request).store.update_credentials(server_id,oauth_token=token["access_token"],oauth_refresh_token=token.get("refresh_token",refresh),oauth_expires_at=time.time()+float(token.get("expires_in",0) or 0))

__all__=["router"]
