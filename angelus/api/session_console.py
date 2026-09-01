"""Session console HTTP projection routes."""
from __future__ import annotations

from dataclasses import dataclass, field
from fastapi import APIRouter, HTTPException, Request
from ..core import AngelusCore
from ..modules.console_module import ConsoleDomainError

router = APIRouter(prefix="/api/sessions/{session_id}")

@dataclass
class AgentEdit:
    """Typed input for an idle graph worker edit.

    Args:
        name: Worker identity with Session graph naming constraints.
        system_prompt: Optional worker-only instructions, never a secret.
    """
    name: str
    system_prompt: str = ""

@dataclass
class ConnectionEdit:
    """Typed input for a directed dependency mutation.

    Args:
        source: Existing upstream Agent identity.
        target: Existing downstream Agent identity.
    """
    source: str
    target: str

@dataclass
class MapperEdit:
    """Typed input for a declarative input mapper.

    Args:
        agent: Existing Agent receiving predecessor results.
        mode: Supported mapper mode.
    """
    agent: str
    mode: str

@dataclass
class RouterEdit:
    """Typed input for a declarative dynamic router.

    Args:
        agent: Existing Agent whose completion invokes the router.
        targets: Existing successor identities selected by the router.
    """
    agent: str
    targets: list[str] = field(default_factory=list)


@dataclass
class RequestPreviewInput:
    """Typed input for one no-send next-request composition.

    Args:
        message: Hypothetical next user message added only to a detached
            in-memory context copy.
    """

    message: str

def _service(request: Request):
    """Resolve the installed console projection service.

    Args:
        request: Incoming FastAPI request carrying application state.

    Returns:
        The Session-console projection service.

    Raises:
        RuntimeError: If the application has no installed Angelus core.
    """
    core=getattr(request.app.state,"angelus_core",None)
    if not isinstance(core, AngelusCore): raise RuntimeError("AngelusCore is not installed")
    return core.console_service
def _call(fn):
    """Map console-domain failures raised by one deferred route action.

    Args:
        fn: Zero-argument route action that calls the projection service.

    Returns:
        JSON-safe service result.
    """
    try: return fn()
    except KeyError as exc: raise HTTPException(404, "Unknown session") from exc
    except ConsoleDomainError as exc: raise HTTPException(409, str(exc)) from exc
    except (ValueError, RuntimeError) as exc: raise HTTPException(422, str(exc)) from exc

@router.get("/agents")
def agents(session_id: str, request: Request):
    """Return safe metadata for all Session Agents.

    Args:
        session_id: Stable Session identity to inspect.
        request: Incoming request carrying the application core.

    Returns:
        JSON Agent metadata projection.
    """
    return _call(lambda:_service(request).agents(session_id))
@router.get("/graph")
def graph(session_id: str, request: Request):
    """Return the Session graph projection.

    Args:
        session_id: Stable Session identity to inspect.
        request: Incoming request carrying the application core.

    Returns:
        JSON-safe graph topology and state.
    """
    return _call(lambda:_service(request).graph(session_id))
@router.get("/graph/info")
def graph_info(session_id: str, request: Request):
    """Return compact graph counts and editability.

    Args:
        session_id: Stable Session identity to inspect.
        request: Incoming request carrying the application core.

    Returns:
        Graph count and run-state projection.
    """
    return _call(lambda:_service(request).graph_info(session_id))
@router.post("/graph/agents")
def add_agent(session_id: str, body: AgentEdit, request: Request):
    """Persist one worker and rebuild the idle graph.

    Args:
        session_id: Stable Session identity to modify.
        body: Validated worker name and instructions.
        request: Incoming request carrying the application core.

    Returns:
        Updated graph projection.
    """
    return _call(lambda:_service(request).add_worker(session_id, body.name, body.system_prompt))
@router.delete("/graph/agents/{name}")
def delete_agent(session_id: str, name: str, request: Request): return _call(lambda:_service(request).remove_worker(session_id, name))
@router.delete("/graph/agents")
def delete_agent_body(session_id: str, body: AgentEdit, request: Request): return _call(lambda:_service(request).remove_worker(session_id, body.name))
@router.post("/graph/connections")
def add_connection(session_id: str, body: ConnectionEdit, request: Request): return _call(lambda:_service(request).add_connection(session_id, body.source, body.target))
@router.delete("/graph/connections")
def delete_connection(session_id: str, body: ConnectionEdit, request: Request): return _call(lambda:_service(request).remove_connection(session_id, body.source, body.target))
@router.post("/graph/mapper")
def mapper(session_id: str, body: MapperEdit, request: Request): return _call(lambda:_service(request).set_mapper(session_id, body.agent, body.mode))
@router.post("/graph/router")
def router_edit(session_id: str, body: RouterEdit, request: Request): return _call(lambda:_service(request).set_router(session_id, body.agent, body.targets))
@router.get("/plan")
def plan(session_id: str, request: Request, agent: str | None = None): return _call(lambda:_service(request).plan(session_id, agent))
@router.get("/events")
def events(session_id: str, request: Request, cursor: int = 0, limit: int = 200): return _call(lambda:_service(request).events(session_id,cursor,limit))
@router.get("/usage")
def usage(session_id: str, request: Request): return _call(lambda:_service(request).usage(session_id))
@router.get("/agents/{agent}/context")
def context(session_id: str, agent: str, request: Request, before: int | None = None, limit: int = 200):
    """Return the newest context page or one older cursor page.

    Args:
        session_id: Stable Session identity owning the Agent.
        agent: Valid coordinator or worker identity.
        request: Incoming request carrying the application core.
        before: Exclusive older-than timeline cursor from the prior response.
        limit: Requested entry count, bounded by the durable reader to 200.

    Returns:
        Chronological context metadata page and older-page cursor.
    """
    return _call(lambda:_service(request).context(session_id, agent, before, limit))
@router.get("/agents/{agent}/context-graph")
def context_graph(session_id: str, agent: str, request: Request): return _call(lambda:_service(request).context_graph(session_id,agent))
@router.post("/agents/{agent}/context/request-preview")
def request_preview(session_id: str, agent: str, body: RequestPreviewInput, request: Request):
    """Compose the next dispatch-ready model request without sending it.

    Args:
        session_id: Stable Session identity owning the Agent context.
        agent: Valid coordinator or Worker identity.
        body: Hypothetical next user message for the detached preview.
        request: Incoming request carrying the application core.

    Returns:
        Credential-free model request snapshot and composition statistics.
    """
    return _call(lambda:_service(request).request_preview(session_id, agent, body.message))
@router.get("/agents/{agent}/context/compaction-input")
def compaction_input(session_id: str, agent: str, request: Request): return _call(lambda:_service(request).compaction_input(session_id,agent))

__all__=["router"]
