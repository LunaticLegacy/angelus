from __future__ import annotations

import asyncio
import dataclasses
import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from ..agent import Agent
from ..prompt import AGENT_START_PROMPT, ROUTER_SELECTION_PROMPT_TEMPLATE
from ..tool import Tool


# ---------------------------------------------------------------------------
# 边定义
# ---------------------------------------------------------------------------

@dataclass
class Edge:

    source_id: str      # 源
    target_id: str      # 目标
    label: Optional[str] = None  # 路由标签，用于条件分支


@dataclass
class ExecutionStopState:
    """ExecutionGraph 的运行时停止状态。"""

    soft_requested: bool = False
    hard_requested: bool = False
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# 执行上下文
# ---------------------------------------------------------------------------

class GraphContext:

    def __init__(self, graph: ExecutionGraph):
        self.graph = graph                              # 图本身
        self.node_inputs: Dict[str, List[Any]] = {}     # 节点进入便
        self.node_outputs: Dict[str, Any] = {}          # 节点输出
        self.executed: Set[str] = set()                 # 执行了多少？
        self.metadata: Dict[str, Any] = {
            "stop_state": None,
        }

    def get_output(self, node_id: str) -> Any:
        return self.node_outputs.get(node_id)

    def get_inputs(self, node_id: str) -> List[Any]:
        return self.node_inputs.get(node_id, [])


# ---------------------------------------------------------------------------
# 节点基类与实现
# ---------------------------------------------------------------------------

class ExecutionNode(ABC):
    """
    执行图节点的抽象基类。
    对于该类，必须实现 `run` 方法。
    """

    def __init__(self, node_id: str, node_type: str):
        self.node_id = node_id
        self.node_type = node_type

    @abstractmethod
    async def run(self, ctx: GraphContext, inputs: List[Any]) -> Any:
        ...


class AgentNode(ExecutionNode):

    def __init__(self, node_id: str, agent: Agent, max_turns: int = 3):
        super().__init__(node_id, "agent")
        self.agent = agent
        self.max_turns = max(1, int(max_turns))

    async def run(self, ctx: GraphContext, inputs: List[Any]) -> str:
        if not inputs:
            msg = AGENT_START_PROMPT
        elif len(inputs) == 1:
            msg = str(inputs[0])
        else:
            parts = [f"[输入 {i + 1}]\n{str(inp)}" for i, inp in enumerate(inputs)]
            msg = "\n\n".join(parts)
        return await self.agent.run_agent_round(msg, max_turns=self.max_turns)


class ToolNode(ExecutionNode):

    def __init__(self, node_id: str, tool: Tool):
        super().__init__(node_id, "tool")
        self.tool = tool

    async def run(self, ctx: GraphContext, inputs: List[Any]) -> Any:
        if len(inputs) == 1 and isinstance(inputs[0], dict):
            args = inputs[0]
        elif len(inputs) == 1:
            args = {"input": inputs[0]}
        else:
            args = {"inputs": inputs}
        try:
            return await self.tool.execute(**args)
        except Exception as exc:
            return {"error": str(exc), "tool": self.tool.name}


class RouterNode(ExecutionNode):

    def __init__(
        self,
        node_id: str,
        routes: Dict[str, str],
        agent: Optional[Agent] = None,
        default_route: Optional[str] = None,
    ):
        super().__init__(node_id, "router")
        self.routes = routes
        self.agent = agent
        self.default_route = default_route or (list(routes.keys())[0] if routes else None)

    async def run(self, ctx: GraphContext, inputs: List[Any]) -> Dict[str, Any]:
        content = "\n\n".join(str(i) for i in inputs)

        if self.agent and len(self.routes) > 1:
            routes_desc = "\n".join(f"- {k}: {v}" for k, v in self.routes.items())
            prompt = ROUTER_SELECTION_PROMPT_TEMPLATE.format(
                routes_desc=routes_desc,
                content=content,
                route_labels=list(self.routes.keys()),
            )
            result = await self.agent.run_agent_round(prompt, max_turns=1)
            selected_routes = [label for label in self.routes if label in result]
            if not selected_routes and self.default_route is not None:
                selected_routes = [self.default_route]

            route_value: Any = selected_routes[0] if len(selected_routes) == 1 else selected_routes
            return {"route": route_value, "routes": selected_routes, "raw": result, "input": content}

        default_routes = [self.default_route] if self.default_route is not None else []
        return {"route": self.default_route, "routes": default_routes, "input": content}


class InputNode(ExecutionNode):
    """
    入口节点。
    该节点需要保持什么？
    """

    def __init__(self, node_id: str):
        super().__init__(node_id, "input")

    async def run(self, ctx: GraphContext, inputs: List[Any]) -> Any:
        return inputs[0] if inputs else None


class OutputNode(ExecutionNode):

    def __init__(self, node_id: str, collector: Optional[Callable] = None):
        super().__init__(node_id, "output")
        self.collector = collector or (lambda x: x)

    async def run(self, ctx: GraphContext, inputs: List[Any]) -> Any:
        return self.collector(inputs)


class JoinNode(ExecutionNode):

    def __init__(self, node_id: str, strategy: str = "all"):
        super().__init__(node_id, "join")
        self.strategy = strategy  # "all", "first"

    async def run(self, ctx: GraphContext, inputs: List[Any]) -> Dict[str, Any]:
        if self.strategy == "first":
            return {"result": inputs[0] if inputs else None, "inputs": inputs}
        return {"results": inputs, "count": len(inputs)}


# ---------------------------------------------------------------------------
# 执行图本体
# ---------------------------------------------------------------------------

class ExecutionGraph:
    """Agent Swarm 的执行图，支持运行时动态增删节点、工具与修改提示词。

    调度策略（事件驱动）：
    - 节点一旦就绪（所有上游已执行完毕）立即启动，不需要等待整层完成。
    - 并发控制：可通过 max_concurrency 限制同时运行的节点数。
    - 超时控制：可为单个节点设置 timeout。
    - 并行：DAG 天然支持并行分支，多个无依赖的节点会同时启动。
    """

    def __init__(
        self,
        llm_fetcher: Optional[Any] = None,
        max_concurrency: Optional[int] = None,
    ):
        """

        Args:
            llm_fetcher: 用于获取 llm 工具的东西。
            max_concurrency: 最大并发数，即最大可同时运行节点数。
        """
        self._nodes: Dict[str, ExecutionNode] = {}
        self._edges: List[Edge] = []
        self._lock = asyncio.Lock()
        self._node_counter = 0

        # 用于运行时动态创建 Agent
        self._llm_fetcher = llm_fetcher

        # 全局工具池
        self._tool_pool: Dict[str, Tool] = {}

        # 并发控制
        self._semaphore = asyncio.Semaphore(max_concurrency) if max_concurrency else None

        # 节点超时配置
        self._node_timeouts: Dict[str, float] = {}

        # 版本：每次图结构变更时自增
        self._version = 0

        # 运行时停止控制
        self._stop_state = ExecutionStopState()
        self._active_run_tasks: Dict[str, asyncio.Task] = {}
        self._active_run_task: Optional[asyncio.Task] = None
        self._active_run_ctx: Optional[GraphContext] = None

    # --- 版本管理 ---

    def _bump_version(self, action: str, **detail: Any) -> None:
        """Increment the graph version on every mutation."""
        self._version += 1

    @property
    def version(self) -> int:
        """Current graph version. Increments on every structural change."""
        return self._version

    @property
    def stop_state(self) -> Dict[str, Any]:
        """当前停止状态的只读快照。"""
        return dataclasses.asdict(self._stop_state)

    def request_soft_stop(self, reason: Optional[str] = None) -> None:
        """请求软停止：允许当前节点完成，但不再推进下游。"""
        self._stop_state.soft_requested = True
        if reason is not None:
            self._stop_state.reason = reason

    def request_hard_stop(self, reason: Optional[str] = None) -> None:
        """请求硬停止：立即取消当前运行中的一切任务。"""
        self._stop_state.soft_requested = True
        self._stop_state.hard_requested = True
        if reason is not None:
            self._stop_state.reason = reason
        for task in list(self._active_run_tasks.values()):
            task.cancel()
        if self._active_run_task is not None:
            self._active_run_task.cancel()

    def clear_stop_requests(self) -> None:
        """清空停止状态。"""
        self._stop_state = ExecutionStopState()

    # --- 内部辅助 ---

    def _alloc_id(self, prefix: str = "node") -> str:
        """
        获取节点 id
        """
        self._node_counter += 1
        return f"{prefix}_{self._node_counter}"

    def _upstream_of(self, node_id: str) -> Set[str]:
        """
        获取某节点的上游节点。
        """
        return {e.source_id for e in self._edges if e.target_id == node_id}

    def _downstream_of(self, node_id: str) -> List[Edge]:
        """
        获取某节点的下游节点。
        """
        return [e for e in self._edges if e.source_id == node_id]

    def _find_entry_nodes(self) -> List[str]:
        return [nid for nid in self._nodes if not self._upstream_of(nid)]

    # --- 工具池 ---

    def register_tool(self, tool: Tool) -> None:
        """
        向全局工具池注册一个工具。
        """
        self._tool_pool[tool.name] = tool

    def unregister_tool(self, tool_name: str) -> Tool:
        """
        从全局工具池移除一个工具。
        Args:
            tool_name: 工具名。

        Raises:
            KeyError: 如果该工具不在工具内则报错。
        """
        if tool_name not in self._tool_pool:
            raise KeyError(f"Tool '{tool_name}' not in pool")
        return self._tool_pool.pop(tool_name)

    def get_tool(self, tool_name: str) -> Tool:
        """
        获取一个工具。只读。
        Args:
            tool_name: 工具名。
        """
        return self._tool_pool[tool_name]

    @property
    def tool_pool(self) -> Dict[str, Tool]:
        return dict(self._tool_pool)

    # --- 节点生命周期（动态增删） ---

    def add_agent_node(
        self,
        agent: Agent,
        node_id: Optional[str] = None,
        max_turns: int = 3,
    ) -> str:
        """
        加入一个智能体节点。
        Args:
            agent: 智能体。
            node_id: 节点 ID。

        """
        nid = node_id or self._alloc_id("agent")
        self._nodes[nid] = AgentNode(nid, agent, max_turns=max_turns)
        self._bump_version("add_agent_node", node_id=nid, max_turns=max_turns)
        return nid

    def add_tool_node(
        self,
        tool: Tool,
        node_id: Optional[str] = None,
    ) -> str:
        nid = node_id or self._alloc_id("tool")
        self._nodes[nid] = ToolNode(nid, tool)
        self._bump_version("add_tool_node", node_id=nid)
        return nid

    def add_router_node(
        self,
        routes: Dict[str, str],
        agent: Optional[Agent] = None,
        default_route: Optional[str] = None,
        node_id: Optional[str] = None,
    ) -> str:
        nid = node_id or self._alloc_id("router")
        self._nodes[nid] = RouterNode(nid, routes, agent, default_route)
        self._bump_version("add_router_node", node_id=nid)
        return nid

    def add_input_node(self, node_id: Optional[str] = None) -> str:
        nid = node_id or self._alloc_id("input")
        self._nodes[nid] = InputNode(nid)
        self._bump_version("add_input_node", node_id=nid)
        return nid

    def add_output_node(
        self,
        collector: Optional[Callable] = None,
        node_id: Optional[str] = None,
    ) -> str:
        nid = node_id or self._alloc_id("output")
        self._nodes[nid] = OutputNode(nid, collector)
        self._bump_version("add_output_node", node_id=nid)
        return nid

    def add_join_node(
        self,
        strategy: str = "all",
        node_id: Optional[str] = None,
    ) -> str:
        nid = node_id or self._alloc_id("join")
        self._nodes[nid] = JoinNode(nid, strategy)
        self._bump_version("add_join_node", node_id=nid)
        return nid

    def remove_node(self, node_id: str) -> None:
        if node_id not in self._nodes:
            raise KeyError(f"Node {node_id} not found")
        del self._nodes[node_id]
        self._bump_version("remove_node", node_id=node_id)
        self._edges = [
            e
            for e in self._edges
            if e.source_id != node_id and e.target_id != node_id
        ]
        self._node_timeouts.pop(node_id, None)

    def get_node(self, node_id: str) -> ExecutionNode:
        return self._nodes[node_id]

    @property
    def nodes(self) -> Dict[str, ExecutionNode]:
        return dict(self._nodes)

    @property
    def edges(self) -> List[Edge]:
        return list(self._edges)

    # --- 边管理 ---

    def connect(
        self,
        source_id: str,
        target_id: str,
        label: Optional[str] = None,
    ) -> None:
        """
        将两个节点之间连接起来。
        Args:
            source_id:
            target_id:
            label:
        Raises:
            KeyError: 如果有任意一个节点不存在，则报错。
        """
        if source_id not in self._nodes:
            raise KeyError(f"Source node {source_id} not found")
        if target_id not in self._nodes:
            raise KeyError(f"Target node {target_id} not found")
        self._edges.append(Edge(source_id, target_id, label))
        self._bump_version("connect", source_id=source_id, target_id=target_id, label=label)

    def disconnect(
        self,
        source_id: str,
        target_id: str,
        label: Optional[str] = None,
    ) -> None:
        self._edges = [
            e
            for e in self._edges
            if not (
                e.source_id == source_id
                and e.target_id == target_id
                and (label is None or e.label == label)
            )
        ]
        self._bump_version("disconnect", source_id=source_id, target_id=target_id, label=label)

    # --- 动态修改 Agent 配置 ---

    def update_agent_prompt(self, node_id: str, system_prompt: str) -> None:
        node = self._nodes.get(node_id)
        if not isinstance(node, AgentNode):
            raise TypeError(f"Node {node_id} is not an agent node")
        node.agent.update_system_prompt(system_prompt)
        self._bump_version("update_agent_prompt", node_id=node_id)

    def add_tool_to_agent(self, node_id: str, tool_name: str) -> None:
        node = self._nodes.get(node_id)
        if not isinstance(node, AgentNode):
            raise TypeError(f"Node {node_id} is not an agent node")
        tool = self._tool_pool.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool '{tool_name}' not found in global pool")
        node.agent.add_tool(tool)
        self._bump_version("add_tool_to_agent", node_id=node_id, tool_name=tool_name)

    def remove_tool_from_agent(self, node_id: str, tool_name: str) -> None:
        node = self._nodes.get(node_id)
        if not isinstance(node, AgentNode):
            raise TypeError(f"Node {node_id} is not an agent node")
        node.agent.remove_tool(tool_name)
        self._bump_version("remove_tool_from_agent", node_id=node_id, tool_name=tool_name)

    def set_node_timeout(self, node_id: str, timeout: float) -> None:
        if node_id not in self._nodes:
            raise KeyError(f"Node {node_id} not found")
        self._node_timeouts[node_id] = timeout
        self._bump_version("set_node_timeout", node_id=node_id, timeout=timeout)

    # --- 执行：事件驱动调度 ---

    async def run(
        self,
        initial_input: Any = None,
        entry_node_id: Optional[str] = None,
        event_hook: Optional[Callable[[str, Dict[str, Any]], Awaitable[None] | None]] = None,
    ) -> GraphContext:
        ctx = GraphContext(self)
        self._active_run_ctx = ctx
        self._active_run_task = asyncio.current_task()
        self._active_run_tasks = {}
        ctx.metadata["stop_state"] = self.stop_state

        async def emit(event: str, payload: Optional[Dict[str, Any]] = None) -> None:
            if event_hook is None:
                return
            result = event_hook(event, payload or {})
            if inspect.isawaitable(result):
                await result

        def summarize_output() -> Any:
            node_outputs = dict(ctx.node_outputs)
            if node_outputs:
                for node_id, value in node_outputs.items():
                    if "output" in str(node_id).lower():
                        return value
                return list(node_outputs.values())[-1]
            return None

        if self._stop_state.hard_requested:
            reason = self._stop_state.reason or "ExecutionGraph hard stop requested before run started"
            self._active_run_ctx = None
            self._active_run_task = None
            self.clear_stop_requests()
            raise asyncio.CancelledError(reason)

        entry = entry_node_id
        if entry is None:
            entries = self._find_entry_nodes()
            if not entries:
                raise ValueError("No entry node found in graph")
            entry = entries[0]

        if initial_input is not None:
            ctx.node_inputs[entry] = [initial_input]

        await emit(
            "run.started",
            {
                "entry_node_id": entry,
                "initial_input": initial_input,
            },
        )

        completed_queue: asyncio.Queue[str] = asyncio.Queue()
        running: Set[str] = set()

        # 工人。
        async def worker(nid: str):
            result: Any = None
            cancelled = False
            failed = False
            try:
                await emit(
                    "node.started",
                    {
                        "node_id": nid,
                        "node_type": self._nodes[nid].node_type,
                        "inputs": list(ctx.node_inputs.get(nid, [])),
                    },
                )
                sem = self._semaphore
                if sem:
                    async with sem:
                        result = await self._run_node_with_timeout(nid, ctx)
                else:
                    result = await self._run_node_with_timeout(nid, ctx)
            except asyncio.TimeoutError:
                result = {
                    "error": "Node execution timed out",
                    "node_id": nid,
                    "node_type": self._nodes[nid].node_type,
                }
                failed = True
            except asyncio.CancelledError:
                cancelled = True
                result = {
                    "error": "Node execution cancelled",
                    "node_id": nid,
                    "node_type": self._nodes[nid].node_type,
                }
                failed = True
            except Exception as exc:
                result = {
                    "error": str(exc),
                    "node_id": nid,
                    "node_type": self._nodes[nid].node_type,
                }
                failed = True

            # 保存结果，但在停止模式下不再推进下游。
            ctx.node_outputs[nid] = result
            ctx.executed.add(nid)
            running.discard(nid)
            self._active_run_tasks.pop(nid, None)

            if failed:
                await emit(
                    "node.failed",
                    {
                        "node_id": nid,
                        "node_type": self._nodes[nid].node_type,
                        "error": result,
                    },
                )
            else:
                await emit(
                    "node.completed",
                    {
                        "node_id": nid,
                        "node_type": self._nodes[nid].node_type,
                        "output": result,
                    },
                )

            if not self._stop_state.soft_requested and not self._stop_state.hard_requested:
                for edge in self._downstream_of(nid):
                    if edge.label is not None:
                        routes = self._extract_routes(result)
                        if edge.label not in routes:
                            continue
                    await emit(
                        "branch.started",
                        {
                            "source_node_id": nid,
                            "target_node_id": edge.target_id,
                            "label": edge.label,
                            "route": self._extract_route(result),
                            "routes": self._extract_routes(result),
                        },
                    )
                    ctx.node_inputs.setdefault(edge.target_id, []).append(result)

            await completed_queue.put(nid)
            if cancelled and self._stop_state.hard_requested:
                return

        def try_start(nid: str) -> bool:
            if nid in ctx.executed or nid in running:
                return False
            if self._stop_state.soft_requested or self._stop_state.hard_requested:
                return False
            upstream = self._upstream_of(nid)
            if upstream and not all(u in ctx.executed for u in upstream):
                return False
            if not upstream and nid not in ctx.node_inputs:
                return False
            running.add(nid)
            task = asyncio.create_task(worker(nid))
            self._active_run_tasks[nid] = task
            return True

        try:
            # 启动初始就绪节点
            for nid in list(self._nodes.keys()):
                try_start(nid)

            # 事件驱动主循环：节点完成 → 尝试启动新就绪节点
            while running:
                if self._stop_state.hard_requested:
                    raise asyncio.CancelledError(
                        self._stop_state.reason or "ExecutionGraph hard stop requested"
                    )

                completed_nid = await completed_queue.get()
                ctx.metadata["last_completed_node"] = completed_nid

                if self._stop_state.hard_requested:
                    raise asyncio.CancelledError(
                        self._stop_state.reason or "ExecutionGraph hard stop requested"
                    )

                if self._stop_state.soft_requested:
                    continue

                for candidate in list(self._nodes.keys()):
                    try_start(candidate)

            await emit(
                "run.completed",
                {
                    "executed": list(ctx.executed),
                    "last_completed_node": ctx.metadata.get("last_completed_node"),
                    "output": summarize_output(),
                    "trace": ctx.to_dict() if hasattr(ctx, "to_dict") else None,
                },
            )
            return ctx
        except asyncio.CancelledError as exc:
            await emit(
                "run.failed",
                {
                    "detail": str(exc) or "ExecutionGraph cancelled",
                    "stop_state": self.stop_state,
                    "trace": ctx.to_dict() if hasattr(ctx, "to_dict") else None,
                },
            )
            raise
        except Exception as exc:
            await emit(
                "run.failed",
                {
                    "detail": str(exc),
                    "trace": ctx.to_dict() if hasattr(ctx, "to_dict") else None,
                },
            )
            raise
        finally:
            pending_tasks = list(self._active_run_tasks.values())
            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)
            self._active_run_tasks.clear()
            self._active_run_task = None
            self._active_run_ctx = None
            self.clear_stop_requests()

    async def _run_node_with_timeout(self, nid: str, ctx: GraphContext) -> Any:
        node = self._nodes[nid]
        inputs = ctx.node_inputs.get(nid, [])
        timeout = self._node_timeouts.get(nid)

        coro = node.run(ctx, inputs)
        if timeout is not None:
            return await asyncio.wait_for(coro, timeout=timeout)
        return await coro

    def _extract_routes(self, result: Any) -> List[str]:
        if isinstance(result, dict):
            routes = result.get("routes")
            if isinstance(routes, list):
                return [str(route) for route in routes if route is not None]
            route = result.get("route")
            if isinstance(route, list):
                return [str(item) for item in route if item is not None]
            if route is not None:
                return [str(route)]
        return []

    def _extract_route(self, result: Any) -> Optional[Any]:
        routes = self._extract_routes(result)
        if not routes:
            return None
        return routes[0] if len(routes) == 1 else routes

    # --- Angelus compatibility ---

    def add_node(self, node: Any) -> None:
        """Add a node (angelus-compatible API)."""
        nid = str(getattr(node, "node_id", self._alloc_id()))
        node.node_id = nid
        self._nodes[nid] = node
        self._bump_version("add_node", node_id=nid)

    def add_edge(
        self,
        from_node_id: Any,
        to_node_id: Any,
        *,
        label: Optional[str] = None,
        condition: Optional[str] = None,
        priority: int = 0,
    ) -> None:
        """Add an edge (angelus-compatible API)."""
        src = str(from_node_id)
        tgt = str(to_node_id)
        if src not in self._nodes:
            raise KeyError(f"Unknown from_node_id: {from_node_id}")
        if tgt not in self._nodes:
            raise KeyError(f"Unknown to_node_id: {to_node_id}")
        if tgt not in getattr(self._nodes[src], "next_node_ids", []):
            next_ids = getattr(self._nodes[src], "next_node_ids", None)
            if next_ids is not None:
                next_ids.append(to_node_id)
        self._edges.append(Edge(source_id=src, target_id=tgt, label=label))
        self._bump_version("add_edge", source_id=src, target_id=tgt, label=label)

    def set_entry(self, node_id: Any) -> None:
        """Set the entry node."""
        pass  # entry is auto-detected

    def set_exit(self, node_id: Any) -> None:
        """Set the exit node."""
        pass  # exit is auto-detected

    # --- 序列化 / 反序列化 ---

    def snapshot(self) -> Dict[str, Any]:
        """配置快照 — 保存图当前静态状态（拓扑 + 配置）。

        每次图结构变更后 version 自增，因此 snapshot 可用于判断
        两个图是否为同一版本。
        """
        nodes: Dict[str, Dict[str, Any]] = {}
        for nid, n in self._nodes.items():
            cfg: Dict[str, Any] = {"type": n.node_type}
            if isinstance(n, RouterNode):
                cfg["routes"] = dict(n.routes)
                cfg["default_route"] = n.default_route
                if n.agent is not None:
                    cfg["agent_id"] = nid  # best-effort: we only know the node id
            elif isinstance(n, JoinNode):
                cfg["strategy"] = n.strategy
            elif isinstance(n, ToolNode):
                cfg["tool_name"] = n.tool.name
            elif isinstance(n, AgentNode):
                cfg["agent_id"] = nid
                cfg["max_turns"] = n.max_turns
            elif isinstance(n, OutputNode):
                has_custom = not (
                    hasattr(n.collector, "__name__")
                    and n.collector.__name__ == "<lambda>"
                )
                cfg["has_collector"] = has_custom
            nodes[nid] = cfg

        return {
            "format": "execution-graph/config",
            "version": self._version,
            "schema_version": "1.0",
            "nodes": nodes,
            "edges": [
                {"source": e.source_id, "target": e.target_id, "label": e.label}
                for e in self._edges
            ],
            "node_timeouts": dict(self._node_timeouts),
            "tool_names": sorted(self._tool_pool.keys()),
        }

    @classmethod
    def restore(
        cls,
        data: Dict[str, Any],
        llm_fetcher: Optional[Any] = None,
        tool_pool: Optional[Dict[str, Tool]] = None,
        agent_map: Optional[Dict[str, Agent]] = None,
    ) -> "ExecutionGraph":
        """Restore an ExecutionGraph from a snapshot dict.

        Agent and tool nodes require external *live* objects (callables) that
        cannot be serialised.  Pass ``agent_map`` and ``tool_pool`` to re-link
        them.  Nodes whose dependencies are missing are silently skipped.
        """
        if data.get("schema_version") != "1.0":
            raise ValueError(
                f"Unsupported schema version: {data.get('schema_version')}"
            )

        graph = cls(llm_fetcher=llm_fetcher)
        graph._version = data.get("version", 0)

        tool_pool = tool_pool or {}
        agent_map = agent_map or {}

        for nid, cfg in data.get("nodes", {}).items():
            ntype = cfg.get("type")
            if ntype == "agent":
                agent = agent_map.get(nid)
                if agent:
                    graph._nodes[nid] = AgentNode(
                        nid,
                        agent,
                        max_turns=cfg.get("max_turns", 3),
                    )
            elif ntype == "tool":
                tool = tool_pool.get(cfg.get("tool_name", ""))
                if tool:
                    graph._nodes[nid] = ToolNode(nid, tool)
            elif ntype == "router":
                routes = dict(cfg.get("routes", {}))
                default_route = cfg.get("default_route")
                router_agent = agent_map.get(cfg.get("agent_id")) if cfg.get("agent_id") else None
                graph._nodes[nid] = RouterNode(nid, routes, router_agent, default_route)
            elif ntype == "input":
                graph._nodes[nid] = InputNode(nid)
            elif ntype == "output":
                graph._nodes[nid] = OutputNode(nid)
            elif ntype == "join":
                graph._nodes[nid] = JoinNode(nid, cfg.get("strategy", "all"))

        for e in data.get("edges", []):
            src, tgt = e["source"], e["target"]
            if src in graph._nodes and tgt in graph._nodes:
                graph._edges.append(Edge(src, tgt, e.get("label")))

        for nid, seconds in data.get("node_timeouts", {}).items():
            if nid in graph._nodes:
                graph._node_timeouts[nid] = seconds

        graph._tool_pool = dict(tool_pool)

        # Restore node counter so future _alloc_id calls do not collide
        import re
        max_counter = 0
        for nid in graph._nodes:
            m = re.search(r"_(\d+)$", nid)
            if m:
                max_counter = max(max_counter, int(m.group(1)))
        graph._node_counter = max_counter

        return graph

    def checkpoint(self, ctx: GraphContext) -> Dict[str, Any]:
        """运行时检查点 — 在 snapshot 基础上追加执行进度。

        包含已执行节点集合、节点输出、节点输入，用于从断点恢复。
        """

        def _serialize(val: Any) -> Any:
            try:
                return json.loads(json.dumps(val, ensure_ascii=False, default=str))
            except Exception:
                return str(val)

        return {
            "format": "execution-graph/checkpoint",
            "version": self._version,
            "schema_version": "1.0",
            "config": self.snapshot(),
            "executed": sorted(ctx.executed),
            "node_outputs": {k: _serialize(v) for k, v in ctx.node_outputs.items()},
            "node_inputs": {
                k: [_serialize(i) for i in v] for k, v in ctx.node_inputs.items()
            },
        }

    def resume(self, checkpoint: Dict[str, Any]) -> GraphContext:
        """从检查点恢复运行时状态。

        恢复后会得到一个已包含部分 executed / outputs / inputs 的
        GraphContext，后续 run() 可以直接从断点继续执行。

        Args:
            checkpoint: 由 :meth:`checkpoint` 产出的字典。

        Returns:
            恢复后的 GraphContext。
        """
        fmt = checkpoint.get("format", "")
        if not fmt.startswith("execution-graph/"):
            raise ValueError(f"Unsupported checkpoint format: {fmt}")
        if checkpoint.get("schema_version") != "1.0":
            raise ValueError(
                f"Unsupported schema version: {checkpoint.get('schema_version')}"
            )
        if checkpoint.get("version") != self._version:
            # 版本不匹配意味着图结构在 checkpoint 后发生了变化
            # 允许继续，但给出警告（调用方可自行决定是否拒绝）
            pass

        ctx = GraphContext(self)
        ctx.executed = set(checkpoint.get("executed", []))
        ctx.node_outputs = dict(checkpoint.get("node_outputs", {}))
        ctx.node_inputs = {
            k: list(v) for k, v in checkpoint.get("node_inputs", {}).items()
        }
        return ctx

    def to_dict(self) -> Dict[str, Any]:
        """Lightweight introspection dict (not round-trippable)."""
        return {
            "nodes": {
                nid: {
                    "type": n.node_type,
                    "id": nid,
                    **({"max_turns": n.max_turns} if isinstance(n, AgentNode) else {}),
                }
                for nid, n in self._nodes.items()
            },
            "edges": [
                {"source": e.source_id, "target": e.target_id, "label": e.label}
                for e in self._edges
            ],
            "version": self._version,
            "stop_state": self.stop_state,
        }
