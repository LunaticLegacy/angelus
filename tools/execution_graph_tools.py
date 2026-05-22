"""将 ExecutionGraph 的操作封装为 Tool，供 Agent 在运行时动态修改图结构。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..agent import Agent
from ..tool import Tool

if TYPE_CHECKING:
    from ..swarm.execution_graph import ExecutionGraph


def create_execution_graph_tools(graph: ExecutionGraph) -> List[Tool]:
    """创建一组工具，让 Agent 能在运行时动态增删节点、工具和修改提示词。

    注意：
    - add_agent_node 依赖 graph._llm_fetcher 来创建新 Agent。
    - add_tool_to_agent / add_tool_node 依赖 graph._tool_pool 中的工具。
    """

    async def _add_agent_node(**kwargs: Any) -> str:
        """在执行图中动态添加一个 Agent 节点。"""
        system_prompt = kwargs["system_prompt"]
        node_id = kwargs.get("node_id")
        tool_names = kwargs.get("tool_names", [])
        max_turns = kwargs.get("max_turns", 3)

        if graph._llm_fetcher is None:
            return "Error: ExecutionGraph has no llm_fetcher, cannot create agent."

        agent = Agent(
            llm_handler=graph._llm_fetcher,
            system_prompt=system_prompt,
        )
        for name in tool_names:
            if name in graph.tool_pool:
                agent.add_tool(graph.tool_pool[name])

        nid = graph.add_agent_node(agent, node_id=node_id, max_turns=max_turns)
        return f"Agent node created: {nid}"

    async def _remove_node(**kwargs: Any) -> str:
        """删除执行图中的指定节点（连带清理相关边）。"""
        node_id = kwargs["node_id"]
        graph.remove_node(node_id)
        return f"Node {node_id} removed."

    async def _connect_nodes(**kwargs: Any) -> str:
        """连接两个节点，可选路由标签。"""
        source_id = kwargs["source_id"]
        target_id = kwargs["target_id"]
        label = kwargs.get("label")
        graph.connect(source_id, target_id, label)
        if label:
            return f"Connected {source_id} --[{label}]--> {target_id}"
        return f"Connected {source_id} --> {target_id}"

    async def _disconnect_nodes(**kwargs: Any) -> str:
        """断开两个节点之间的连接。"""
        source_id = kwargs["source_id"]
        target_id = kwargs["target_id"]
        label = kwargs.get("label")
        graph.disconnect(source_id, target_id, label)
        return f"Disconnected {source_id} -> {target_id}"

    async def _update_agent_prompt(**kwargs: Any) -> str:
        """运行时修改指定 Agent 节点的系统提示词。"""
        node_id = kwargs["node_id"]
        system_prompt = kwargs["system_prompt"]
        graph.update_agent_prompt(node_id, system_prompt)
        return f"Updated system prompt for agent node {node_id}."

    async def _add_tool_to_agent(**kwargs: Any) -> str:
        """从全局工具池选取工具，添加到指定 Agent 节点。"""
        node_id = kwargs["node_id"]
        tool_name = kwargs["tool_name"]
        graph.add_tool_to_agent(node_id, tool_name)
        return f"Added tool '{tool_name}' to agent node {node_id}."

    async def _remove_tool_from_agent(**kwargs: Any) -> str:
        """从指定 Agent 节点移除一个工具。"""
        node_id = kwargs["node_id"]
        tool_name = kwargs["tool_name"]
        graph.remove_tool_from_agent(node_id, tool_name)
        return f"Removed tool '{tool_name}' from agent node {node_id}."

    async def _add_tool_node(**kwargs: Any) -> str:
        """将全局工具池中的工具作为节点加入执行图。"""
        tool_name = kwargs["tool_name"]
        node_id = kwargs.get("node_id")
        tool = graph.tool_pool.get(tool_name)
        if tool is None:
            return f"Error: Tool '{tool_name}' not found in global pool."
        nid = graph.add_tool_node(tool, node_id=node_id)
        return f"Tool node created: {nid} (tool={tool_name})"

    async def _set_node_timeout(**kwargs: Any) -> str:
        """为指定节点设置执行超时。"""
        node_id = kwargs["node_id"]
        timeout = kwargs["timeout"]
        graph.set_node_timeout(node_id, timeout)
        return f"Set timeout={timeout}s for node {node_id}."

    async def _get_graph_info(**kwargs: Any) -> str:
        """获取当前执行图的结构概览。"""
        data = graph.to_dict()
        lines = [
            "ExecutionGraph 概览",
            f"  节点数: {len(data['nodes'])}",
            f"  边数:   {len(data['edges'])}",
            f"  工具池: {list(graph.tool_pool.keys())}",
            f"  并发限制: {graph._semaphore._value if graph._semaphore else '无'}",
            "",
            "--- 节点 ---",
        ]
        for nid, info in data["nodes"].items():
            lines.append(f"  [{info['type']}] {nid}")
        if data["edges"]:
            lines.append("\n--- 边 ---")
            for e in data["edges"]:
                label = f" --[{e['label']}]--> " if e["label"] else " --> "
                lines.append(f"  {e['source']}{label}{e['target']}")
        return "\n".join(lines)

    return [
        Tool(
            name="execution_graph_add_agent",
            description="在执行图中动态添加一个 Agent 节点。需要 system_prompt；如需预装工具，传入 tool_names（从全局工具池选取）。",
            parameters={
                "type": "object",
                "properties": {
                    "system_prompt": {"type": "string", "description": "Agent 的系统提示词"},
                    "node_id": {"type": "string", "description": "可选的自定义节点 ID"},
                    "tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "预装工具名称列表（来自全局工具池）",
                    },
                    "max_turns": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 3,
                        "description": "该 Agent 节点运行时允许的最大 LLM/tool 轮次",
                    },
                },
                "required": ["system_prompt"],
            },
            handler=_add_agent_node,
        ),
        Tool(
            name="execution_graph_remove_node",
            description="删除执行图中的指定节点，连带清理相关边。",
            parameters={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "要删除的节点 ID"},
                },
                "required": ["node_id"],
            },
            handler=_remove_node,
        ),
        Tool(
            name="execution_graph_connect",
            description="连接两个节点。label 用于 RouterNode 的条件分支匹配。",
            parameters={
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "target_id": {"type": "string"},
                    "label": {"type": "string", "description": "可选的路由标签"},
                },
                "required": ["source_id", "target_id"],
            },
            handler=_connect_nodes,
        ),
        Tool(
            name="execution_graph_disconnect",
            description="断开两个节点之间的连接。",
            parameters={
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "target_id": {"type": "string"},
                    "label": {"type": "string", "description": "可选：仅断开指定标签的边"},
                },
                "required": ["source_id", "target_id"],
            },
            handler=_disconnect_nodes,
        ),
        Tool(
            name="execution_graph_update_agent_prompt",
            description="运行时修改指定 Agent 节点的系统提示词。",
            parameters={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "system_prompt": {"type": "string"},
                },
                "required": ["node_id", "system_prompt"],
            },
            handler=_update_agent_prompt,
        ),
        Tool(
            name="execution_graph_add_tool_to_agent",
            description="从全局工具池选取工具，添加到指定 Agent 节点。",
            parameters={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "tool_name": {"type": "string"},
                },
                "required": ["node_id", "tool_name"],
            },
            handler=_add_tool_to_agent,
        ),
        Tool(
            name="execution_graph_remove_tool_from_agent",
            description="从指定 Agent 节点移除一个工具。",
            parameters={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "tool_name": {"type": "string"},
                },
                "required": ["node_id", "tool_name"],
            },
            handler=_remove_tool_from_agent,
        ),
        Tool(
            name="execution_graph_add_tool_node",
            description="将全局工具池中的工具包装为执行图节点加入图中。",
            parameters={
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string"},
                    "node_id": {"type": "string", "description": "可选的自定义节点 ID"},
                },
                "required": ["tool_name"],
            },
            handler=_add_tool_node,
        ),
        Tool(
            name="execution_graph_set_node_timeout",
            description="为指定节点设置执行超时（秒）。超时时节点会返回 error 结果，不会导致整图崩溃。",
            parameters={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "timeout": {"type": "number", "description": "超时秒数"},
                },
                "required": ["node_id", "timeout"],
            },
            handler=_set_node_timeout,
        ),
        Tool(
            name="execution_graph_get_info",
            description="获取当前执行图的结构概览、节点列表、边列表和工具池状态。",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=_get_graph_info,
        ),
    ]
