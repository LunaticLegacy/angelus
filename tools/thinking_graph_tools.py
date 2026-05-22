"""Expose ThinkingGraph operations as Tools so Agents can call them via tool_call."""

from typing import Any, Dict, List, Optional

from ..thinking_graph import ALLOWED_EDGE_SCHEMA, ThinkingEdgeType, ThinkingGraph, ThinkingNodeType
from ..tool import Tool


def create_thinking_graph_tools(graph: ThinkingGraph) -> List[Tool]:
    """
    将 ThinkingGraph 的核心操作封装为一组 Tool。
    Agent 可以通过 tool_call 间接操作图，无需直接耦合 ThinkingGraph。

    所有 handler 均通过 **kwargs 接收参数，确保工具调用统一使用参数字典解析。

    Args:
        graph: 要操作的 ThinkingGraph 实例。

    Returns:
        Tool 列表，可直接传入 Agent(tools=...)。
    """

    async def _add_node(**kwargs: Any) -> int:
        """添加节点。参数通过 kwargs 字典解析。"""
        return await graph.add_node(
            node_type=ThinkingNodeType(kwargs["node_type"]),
            info=kwargs["info"],
            tags=kwargs.get("tags") or [],
            confidence=kwargs.get("confidence", 1.0),
            description=kwargs.get("description", ""),
            payload=kwargs.get("payload") or {},
        )

    async def _add_edge(**kwargs: Any) -> int:
        """添加边。参数通过 kwargs 字典解析。"""
        return await graph.add_edge(
            edge_type=ThinkingEdgeType(kwargs["edge_type"]),
            source_id=kwargs["source_id"],
            target_id=kwargs["target_id"],
            strength=kwargs.get("strength", 1.0),
            description=kwargs.get("description", ""),
        )

    async def _validate_context(**kwargs: Any) -> str:
        """验证局部上下文。参数通过 kwargs 字典解析。"""
        await graph.validate_incremental_context(
            kwargs["node_id"],
            kwargs.get("max_hops", 1),
        )
        return f"Local context around node {kwargs['node_id']} is valid."

    async def _get_node_info(**kwargs: Any) -> str:
        """获取节点信息。参数通过 kwargs 字典解析。"""
        node_id = kwargs["node_id"]
        if node_id not in graph.node_dict:
            return f"Node {node_id} not found."
        node = graph.node_dict[node_id]
        return (
            f"Node {node.id}: type={node.node_type.value}, "
            f"info={node.info!r}, confidence={node.confidence}"
        )

    async def _get_usage(**kwargs: Any) -> str:
        """返回思考图用法说明。"""
        return (
            "ThinkingGraph 使用指南\n"
            "====================\n\n"
            "【节点类型】\n"
            "  goal: 总目标\n"
            "  question: 待解问题\n"
            "  claim: 主张 / 结论\n"
            "  hypothesis: 假设\n"
            "  evidence: 证据\n"
            "  assumption: 前提假设\n"
            "  plan: 计划\n"
            "  step: 计划步骤\n"
            "  action: 工具调用 / 行为\n"
            "  observation: 工具结果 / 外部反馈\n"
            "  critique: 批判 / 审查意见\n"
            "  decision: 决策\n"
            "  summary: 摘要\n"
            "  memory: 可沉淀记忆\n"
            "  artifact: 文件 / patch / 输出产物引用\n"
            "  error: 错误 / 失败原因\n\n"
            "【边类型】\n"
            "  supports: A 支持 B\n"
            "  opposes: A 反驳 B\n"
            "  leads_to: A 导致 / 推进到 B\n"
            "  derives_from: A 从 B 推导而来\n"
            "  requires: A 需要 B\n"
            "  answers: A 回答 B\n"
            "  refines: A 细化 / 改进 B\n"
            "  contradicts: A 与 B 存在硬冲突\n"
            "  blocks: A 阻塞 B\n"
            "  produces: A 产生 B\n"
            "  observes: A 观察 / 验证 B\n\n"
            "【使用流程】\n"
            "1. thinking_graph_add_node —— 添加节点记录观点\n"
            "2. thinking_graph_add_edge —— 连接节点建立关系\n"
            "3. thinking_graph_get_node_info —— 查询节点信息\n"
            "4. thinking_graph_get_schema —— 查询边类型允许的节点组合\n"
            "5. thinking_graph_validate_context —— 验证局部上下文一致性"
        )

    async def _get_schema(**kwargs: Any) -> str:
        """查询边类型的 schema 规则。参数通过 kwargs 字典解析。"""
        edge_type = kwargs.get("edge_type")
        if edge_type:
            et = ThinkingEdgeType(edge_type)
            pairs = ALLOWED_EDGE_SCHEMA.get(et, set())
            if not pairs:
                return (
                    f"边类型 '{edge_type}' 没有定义具体的 schema 限制"
                    f"（允许任意节点组合）。"
                )
            lines = [f"边类型 '{edge_type}' 允许的节点组合："]
            for src, tgt in sorted(pairs, key=lambda p: (p[0].value, p[1].value)):
                lines.append(f"  {src.value} -> {tgt.value}")
            return "\n".join(lines)

        # 未指定 edge_type，返回全部 schema
        lines = ["所有边类型的 schema 规则："]
        for et in ThinkingEdgeType:
            pairs = ALLOWED_EDGE_SCHEMA.get(et, set())
            lines.append(f"\n[{et.value}]")
            if pairs:
                for src, tgt in sorted(pairs, key=lambda p: (p[0].value, p[1].value)):
                    lines.append(f"  {src.value} -> {tgt.value}")
            else:
                lines.append("  （无限制，任意节点组合均允许）")
        return "\n".join(lines)

    async def _get_full_graph(**kwargs: Any) -> str:
        """全量读取思考图。参数通过 kwargs 字典解析。"""
        data = await graph.get_full_graph()
        # 返回精简的字符串摘要，避免 token 爆炸
        lines = [
            f"ThinkingGraph 全量快照 (version={data['version']}):",
            f"  节点数: {data['node_count']}",
            f"  边数: {data['edge_count']}",
            "",
            "--- 节点列表 ---",
        ]
        for nid, node in data["nodes"].items():
            lines.append(
                f"  [{node['node_type']}] id={nid}: {node['info'][:80]}..."
            )
        if data["edges"]:
            lines.append("\n--- 边列表 ---")
            for eid, edge in data["edges"].items():
                lines.append(
                    f"  [{edge['edge_type']}] {edge['source_id']} -> {edge['target_id']}"
                )
        return "\n".join(lines)

    return [
        Tool(
            name="thinking_graph_add_node",
            description="Add a node to the thinking graph. Returns the new node ID.",
            parameters={
                "type": "object",
                "properties": {
                    "node_type": {
                        "type": "string",
                        "enum": [t.value for t in ThinkingNodeType],
                        "description": "Node type",
                    },
                    "info": {"type": "string", "description": "Node content"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 1.0,
                    },
                    "description": {"type": "string", "default": ""},
                    "payload": {
                        "type": "object",
                        "description": "Optional structured metadata for this node.",
                        "default": {},
                    },
                },
                "required": ["node_type", "info"],
            },
            handler=_add_node,
        ),
        Tool(
            name="thinking_graph_add_edge",
            description="Add an edge between two existing nodes. Returns the new edge ID.",
            parameters={
                "type": "object",
                "properties": {
                    "edge_type": {
                        "type": "string",
                        "enum": [t.value for t in ThinkingEdgeType],
                        "description": "Edge type",
                    },
                    "source_id": {"type": "integer", "description": "Source node ID"},
                    "target_id": {"type": "integer", "description": "Target node ID"},
                    "strength": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 1.0,
                    },
                    "description": {"type": "string", "default": ""},
                },
                "required": ["edge_type", "source_id", "target_id"],
            },
            handler=_add_edge,
        ),
        Tool(
            name="thinking_graph_validate_context",
            description="Validate the local context around a node (incremental check).",
            parameters={
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer"},
                    "max_hops": {"type": "integer", "minimum": 0, "default": 1},
                },
                "required": ["node_id"],
            },
            handler=_validate_context,
        ),
        Tool(
            name="thinking_graph_get_node_info",
            description="Get basic info of a node by ID.",
            parameters={
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer"},
                },
                "required": ["node_id"],
            },
            handler=_get_node_info,
        ),
        Tool(
            name="thinking_graph_get_usage",
            description="Get the usage guide of ThinkingGraph, including all node types and edge types.",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=_get_usage,
        ),
        Tool(
            name="thinking_graph_get_schema",
            description=(
                "Query the schema rules of edge types. "
                "Pass edge_type to query a specific edge; omit it to get all rules."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "edge_type": {
                        "type": "string",
                        "enum": [t.value for t in ThinkingEdgeType],
                        "description": "Optional: specific edge type to query",
                    },
                },
                "required": [],
            },
            handler=_get_schema,
        ),
        Tool(
            name="thinking_graph_get_full_graph",
            description="Read the entire thinking graph. Returns a summary of all nodes and edges.",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=_get_full_graph,
        ),
    ]
