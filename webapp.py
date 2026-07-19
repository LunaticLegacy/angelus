"""Local browser UI for configuring and observing a single ``Agent`` run."""

from __future__ import annotations

import json
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import Agent, AgentRunControl, AgentRunStopped
from .events import ExecutionEvent
from .llm_fetcher import LLMBackendConfig, LLMFetcher
from .llm_types import LLMOutput
from .tools.shell_tools import create_shell_tools


APP_ROOT = Path(__file__).resolve().parent
STATE_ROOT = APP_ROOT / ".llmfetcher"
WORKSPACE_ROOT = STATE_ROOT / "workspaces"
WORKSPACE_INDEX = STATE_ROOT / "workspaces.json"
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)


class RunConfig(BaseModel):
    """Settings used to create the backend and Agent for a browser session."""

    provider: str = "openai"
    model: str
    api_key: str = ""
    api_url: str = ""
    system_prompt: str = "You are a helpful, precise assistant."
    temperature: float = Field(default=0.4, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=131072)
    max_rounds: int = Field(default=12, ge=1, le=100)
    enable_shell: bool = False


class RunRequest(BaseModel):
    """A message and its non-persisted browser-side configuration."""

    session_id: str
    workspace_id: str
    message: str = Field(min_length=1, max_length=100_000)
    config: RunConfig


class SteerRequest(BaseModel):
    """One instruction added at the next safe agent boundary."""

    message: str = Field(min_length=1, max_length=100_000)


class WorkspaceRequest(BaseModel):
    """A user-visible workspace name, stored only on the local machine."""

    name: str = Field(min_length=1, max_length=80)


class BrowserRunControl(AgentRunControl):
    """Thread-safe implementation of llmfetcher's cooperative run controls."""

    def __init__(self) -> None:
        self._stopped = threading.Event()
        self._steers: queue.Queue[str] = queue.Queue()

    def should_stop(self) -> bool:
        return self._stopped.is_set()

    def drain_steers(self) -> list[str]:
        messages: list[str] = []
        while True:
            try:
                messages.append(self._steers.get_nowait())
            except queue.Empty:
                return messages

    def stop(self) -> None:
        self._stopped.set()

    def steer(self, message: str) -> None:
        self._steers.put(message)


@dataclass
class ActiveRun:
    """Live work and its event queue, owned by one browser session."""

    control: BrowserRunControl
    events: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    done: threading.Event = field(default_factory=threading.Event)


@dataclass
class BrowserSession:
    """In-memory state that prevents concurrent runs in the same chat."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    active: ActiveRun | None = None


_sessions: dict[tuple[str, str], BrowserSession] = {}
_sessions_lock = threading.Lock()


def _safe_id(value: str, label: str) -> str:
    """Validate IDs before using them in a local storage path."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise HTTPException(status_code=400, detail=f"Invalid {label} id")
    return value


def _read_workspaces() -> list[dict[str, str]]:
    """Return the local workspace registry, repairing a missing registry."""
    if not WORKSPACE_INDEX.exists():
        default = [{"id": "default", "name": "默认工作空间"}]
        WORKSPACE_INDEX.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return default
    try:
        records = json.loads(WORKSPACE_INDEX.read_text(encoding="utf-8"))
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict) and "id" in item and "name" in item]
    except (OSError, json.JSONDecodeError):
        pass
    return [{"id": "default", "name": "默认工作空间"}]


def _write_workspaces(workspaces: list[dict[str, str]]) -> None:
    """Atomically replace the small local workspace registry."""
    temporary = WORKSPACE_INDEX.with_suffix(".tmp")
    temporary.write_text(json.dumps(workspaces, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(WORKSPACE_INDEX)


def _workspace_exists(workspace_id: str) -> bool:
    """Return whether a workspace is registered locally."""
    return any(item["id"] == workspace_id for item in _read_workspaces())


def _get_session(workspace_id: str, session_id: str) -> BrowserSession:
    """Get or create the in-memory holder for a validated browser session."""
    with _sessions_lock:
        return _sessions.setdefault((workspace_id, session_id), BrowserSession())


def _event_payload(event: ExecutionEvent) -> dict[str, Any]:
    """Convert library events to JSON values suitable for Server-Sent Events."""
    return {
        "type": event.event_type,
        "source": event.source,
        "agent": event.agent_name,
        "message": event.message,
        "data": event.data,
        "timestamp": event.timestamp,
    }


def _build_agent(config: RunConfig, workspace_id: str, session_id: str) -> Agent:
    """Create an Agent from current UI settings without persisting credentials."""
    workspace_path = WORKSPACE_ROOT / workspace_id
    workspace_path.mkdir(parents=True, exist_ok=True)
    backend = LLMBackendConfig(
        name="browser",
        provider=config.provider.strip(),
        model=config.model.strip(),
        api_key=config.api_key,
        api_url=config.api_url.strip() or None,
        timeout=120,
        max_retries=0,
    )
    agent = Agent(
        llm_fetcher=LLMFetcher([backend]),
        system_prompt=config.system_prompt,
        context_path=workspace_path / f"{session_id}.json",
        default_max_rounds=config.max_rounds,
        default_max_tokens=config.max_tokens,
    )
    if config.enable_shell:
        agent.add_tools(create_shell_tools(sandbox_cwd=str(Path.cwd())))
    return agent


app = FastAPI(title="llmfetcher Console", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=APP_ROOT / "web" / "static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the standalone chat console."""
    return FileResponse(APP_ROOT / "web" / "templates" / "index.html")


@app.get("/api/providers")
def providers() -> dict[str, list[str]]:
    """Expose the providers currently registered by the library."""
    return {"providers": list(LLMFetcher.list_available_backend_providers())}


@app.get("/api/workspaces")
def list_workspaces() -> dict[str, list[dict[str, str]]]:
    """List local workspaces available to the browser console."""
    return {"workspaces": _read_workspaces()}


@app.post("/api/workspaces", status_code=201)
def create_workspace(request: WorkspaceRequest) -> dict[str, str]:
    """Create a local workspace with an isolated context directory."""
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Workspace name is required")
    workspace_id = uuid.uuid4().hex
    with _sessions_lock:
        workspaces = _read_workspaces()
        record = {"id": workspace_id, "name": name}
        workspaces.append(record)
        _write_workspaces(workspaces)
    (WORKSPACE_ROOT / workspace_id).mkdir(parents=True, exist_ok=True)
    return record


@app.post("/api/runs")
def start_run(request: RunRequest) -> dict[str, str]:
    """Start one synchronous Agent in a worker thread and return its run ID."""
    session_id = _safe_id(request.session_id, "session")
    workspace_id = _safe_id(request.workspace_id, "workspace")
    if not _workspace_exists(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not request.config.model.strip():
        raise HTTPException(status_code=422, detail="Model is required")
    session = _get_session(workspace_id, session_id)
    with session.lock:
        if session.active and not session.active.done.is_set():
            raise HTTPException(status_code=409, detail="This chat already has an active run")
        active = ActiveRun(control=BrowserRunControl())
        session.active = active

    def execute() -> None:
        started = time.time()
        try:
            agent = _build_agent(request.config, workspace_id, session_id)
            agent.add_hook(lambda event: active.events.put({"event": "lifecycle", **_event_payload(event)}))
            output: LLMOutput = agent.run(
                request.message,
                temperature=request.config.temperature,
                control=active.control,
            )
            active.events.put({
                "event": "result",
                "content": output.content,
                "reasoning": output.reasoning_content,
                "provider": output.provider,
                "model": output.model,
                "usage": {
                    "input": agent.usage.input_tokens,
                    "output": agent.usage.output_tokens,
                    "total": agent.usage.total_tokens,
                },
                "duration_ms": round((time.time() - started) * 1000),
            })
        except AgentRunStopped:
            active.events.put({"event": "stopped", "message": "Run stopped after the current step."})
        except Exception as exc:
            active.events.put({"event": "error", "message": str(exc)})
        finally:
            active.done.set()
            active.events.put({"event": "done"})

    threading.Thread(target=execute, name=f"llmfetcher-{session_id}", daemon=True).start()
    return {"run_id": session_id, "workspace_id": workspace_id}


@app.get("/api/workspaces/{workspace_id}/runs/{session_id}/events")
def stream_events(workspace_id: str, session_id: str) -> StreamingResponse:
    """Stream queued lifecycle events as SSE until the active run completes."""
    session = _get_session(_safe_id(workspace_id, "workspace"), _safe_id(session_id, "session"))
    active = session.active
    if active is None:
        raise HTTPException(status_code=404, detail="No active run")

    def generate():
        while not (active.done.is_set() and active.events.empty()):
            try:
                payload = active.events.get(timeout=0.75)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except queue.Empty:
                yield ": keepalive\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/api/workspaces/{workspace_id}/runs/{session_id}/stop")
def stop_run(workspace_id: str, session_id: str) -> dict[str, bool]:
    """Request a stop at the next completed model-and-tool boundary."""
    session = _get_session(_safe_id(workspace_id, "workspace"), _safe_id(session_id, "session"))
    if not session.active or session.active.done.is_set():
        raise HTTPException(status_code=409, detail="No active run")
    session.active.control.stop()
    return {"ok": True}


@app.post("/api/workspaces/{workspace_id}/runs/{session_id}/steer")
def steer_run(workspace_id: str, session_id: str, request: SteerRequest) -> dict[str, bool]:
    """Queue a steering message that Agent.run applies at a safe boundary."""
    session = _get_session(_safe_id(workspace_id, "workspace"), _safe_id(session_id, "session"))
    if not session.active or session.active.done.is_set():
        raise HTTPException(status_code=409, detail="No active run")
    session.active.control.steer(request.message)
    return {"ok": True}


def main() -> None:
    """Run the local console with ``llmfetcher-web``."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
