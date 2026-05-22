import asyncio
import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Tuple, Set, Optional, Any
from collections import defaultdict
from numbers import Real
import math
from datetime import datetime, timezone

class ThinkingNodeType(str, Enum):
    GOAL = "goal"                    # 总目标
    QUESTION = "question"            # 待解问题
    CLAIM = "claim"                  # 主张 / 结论
    HYPOTHESIS = "hypothesis"        # 假设
    EVIDENCE = "evidence"            # 证据
    ASSUMPTION = "assumption"        # 前提假设
    PLAN = "plan"                    # 计划
    STEP = "step"                    # 计划步骤
    ACTION = "action"                # 工具调用 / 行为
    OBSERVATION = "observation"      # 工具结果 / 外部反馈
    CRITIQUE = "critique"            # 批判 / 审查意见
    DECISION = "decision"            # 决策
    SUMMARY = "summary"              # 摘要
    MEMORY = "memory"                # 可沉淀记忆
    ARTIFACT = "artifact"            # 文件 / patch / 输出产物引用
    ERROR = "error"                  # 错误 / 失败原因

class ThinkingEdgeType(str, Enum):
    SUPPORTS = "supports"              # A 支持 B
    OPPOSES = "opposes"                # A 反驳 B
    LEADS_TO = "leads_to"              # A 导致 / 推进到 B
    DERIVES_FROM = "derives_from"      # A 从 B 推导而来
    REQUIRES = "requires"              # A 需要 B 才能成立 / 执行
    ANSWERS = "answers"                # A 回答 B
    REFINES = "refines"                # A 细化 / 改进 B
    CONTRADICTS = "contradicts"        # A 与 B 存在硬冲突
    BLOCKS = "blocks"                  # A 阻塞 B
    PRODUCES = "produces"              # A 产生 B
    OBSERVES = "observes"              # A 观察 / 验证 B


@dataclass(kw_only=True)
class ThinkingGraphObject:
    id: int                         # object ID
    created_by: str                 # 创建者
    description: str = ""           # 描述

@dataclass(kw_only=True)
class ThinkingGraphNode(ThinkingGraphObject):
    node_type: ThinkingNodeType     # 类型
    info: str                       # 信息
    tags: List[str]                  # 节点标签
    confidence: float               # 置信度
    payload: Dict[str, Any]         # 额外信息

@dataclass(kw_only=True)
class ThinkingGraphEdge(ThinkingGraphObject):
    edge_type: ThinkingEdgeType     # 类型
    source_id: int                   # 起始 ID
    target_id: int                     # 结束点 ID
    strength: float                 # 链接力度


@dataclass
class ThinkingGraphTransactionRecord:
    """单次思考图变更记录。"""

    transaction_id: int
    operation: str
    object_kind: str
    object_id: int
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    version_before: int = 0
    version_after: int = 0
    created_by: str = "system"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


# 边缘分组：规定某种边只允许连接特定类型的起点和终点。
ALLOWED_EDGE_SCHEMA: Dict[
    ThinkingEdgeType, Set[Tuple[ThinkingNodeType, ThinkingNodeType]]
] = {
    # A 支持 B：通常是证据、观察、主张支持另一个主张 / 假设 / 决策。
    ThinkingEdgeType.SUPPORTS: {
        (ThinkingNodeType.EVIDENCE, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.OBSERVATION, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.CLAIM),

        (ThinkingNodeType.EVIDENCE, ThinkingNodeType.HYPOTHESIS),
        (ThinkingNodeType.OBSERVATION, ThinkingNodeType.HYPOTHESIS),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.HYPOTHESIS),

        (ThinkingNodeType.EVIDENCE, ThinkingNodeType.DECISION),
        (ThinkingNodeType.OBSERVATION, ThinkingNodeType.DECISION),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.DECISION),

        (ThinkingNodeType.ASSUMPTION, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.ASSUMPTION, ThinkingNodeType.HYPOTHESIS),
        (ThinkingNodeType.ASSUMPTION, ThinkingNodeType.PLAN),

        (ThinkingNodeType.MEMORY, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.MEMORY, ThinkingNodeType.PLAN),
        (ThinkingNodeType.MEMORY, ThinkingNodeType.DECISION),
    },

    # A 反对 / 削弱 B：弱反驳，不一定硬矛盾。
    ThinkingEdgeType.OPPOSES: {
        (ThinkingNodeType.EVIDENCE, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.OBSERVATION, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.CLAIM),

        (ThinkingNodeType.EVIDENCE, ThinkingNodeType.HYPOTHESIS),
        (ThinkingNodeType.OBSERVATION, ThinkingNodeType.HYPOTHESIS),
        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.HYPOTHESIS),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.HYPOTHESIS),

        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.PLAN),
        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.STEP),
        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.ACTION),
        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.DECISION),

        (ThinkingNodeType.CLAIM, ThinkingNodeType.PLAN),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.DECISION),
        (ThinkingNodeType.ASSUMPTION, ThinkingNodeType.CLAIM),
    },

    # A 与 B 存在硬冲突：二者不能同时成立。
    ThinkingEdgeType.CONTRADICTS: {
        (ThinkingNodeType.CLAIM, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.HYPOTHESIS),
        (ThinkingNodeType.HYPOTHESIS, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.HYPOTHESIS, ThinkingNodeType.HYPOTHESIS),

        (ThinkingNodeType.EVIDENCE, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.OBSERVATION, ThinkingNodeType.CLAIM),

        (ThinkingNodeType.CLAIM, ThinkingNodeType.EVIDENCE),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.OBSERVATION),

        (ThinkingNodeType.ASSUMPTION, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.ASSUMPTION),
        (ThinkingNodeType.ASSUMPTION, ThinkingNodeType.ASSUMPTION),
    },

    # A 需要 B：静态依赖关系。
    ThinkingEdgeType.REQUIRES: {
        (ThinkingNodeType.GOAL, ThinkingNodeType.QUESTION),
        (ThinkingNodeType.QUESTION, ThinkingNodeType.ASSUMPTION),

        (ThinkingNodeType.HYPOTHESIS, ThinkingNodeType.ASSUMPTION),
        (ThinkingNodeType.HYPOTHESIS, ThinkingNodeType.EVIDENCE),

        (ThinkingNodeType.CLAIM, ThinkingNodeType.EVIDENCE),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.OBSERVATION),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.ASSUMPTION),

        (ThinkingNodeType.PLAN, ThinkingNodeType.STEP),
        (ThinkingNodeType.PLAN, ThinkingNodeType.ASSUMPTION),
        (ThinkingNodeType.PLAN, ThinkingNodeType.MEMORY),

        (ThinkingNodeType.STEP, ThinkingNodeType.ACTION),
        (ThinkingNodeType.STEP, ThinkingNodeType.ASSUMPTION),

        (ThinkingNodeType.ACTION, ThinkingNodeType.ARTIFACT),
        (ThinkingNodeType.ACTION, ThinkingNodeType.EVIDENCE),
        (ThinkingNodeType.ACTION, ThinkingNodeType.ASSUMPTION),
        (ThinkingNodeType.ACTION, ThinkingNodeType.MEMORY),

        (ThinkingNodeType.DECISION, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.DECISION, ThinkingNodeType.CRITIQUE),

        (ThinkingNodeType.SUMMARY, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.SUMMARY, ThinkingNodeType.OBSERVATION),
        (ThinkingNodeType.SUMMARY, ThinkingNodeType.DECISION),
    },

    # A 产生 B：产物 / 结果关系。
    ThinkingEdgeType.PRODUCES: {
        (ThinkingNodeType.PLAN, ThinkingNodeType.STEP),
        (ThinkingNodeType.STEP, ThinkingNodeType.ACTION),

        (ThinkingNodeType.ACTION, ThinkingNodeType.OBSERVATION),
        (ThinkingNodeType.ACTION, ThinkingNodeType.EVIDENCE),
        (ThinkingNodeType.ACTION, ThinkingNodeType.ARTIFACT),
        (ThinkingNodeType.ACTION, ThinkingNodeType.ERROR),

        (ThinkingNodeType.OBSERVATION, ThinkingNodeType.EVIDENCE),

        (ThinkingNodeType.CLAIM, ThinkingNodeType.SUMMARY),
        (ThinkingNodeType.DECISION, ThinkingNodeType.PLAN),
        (ThinkingNodeType.SUMMARY, ThinkingNodeType.MEMORY),
        (ThinkingNodeType.SUMMARY, ThinkingNodeType.ARTIFACT),
    },

    # A 阻塞 B：动态执行阻塞。
    ThinkingEdgeType.BLOCKS: {
        (ThinkingNodeType.ERROR, ThinkingNodeType.ACTION),
        (ThinkingNodeType.ERROR, ThinkingNodeType.STEP),
        (ThinkingNodeType.ERROR, ThinkingNodeType.PLAN),
        (ThinkingNodeType.ERROR, ThinkingNodeType.DECISION),

        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.ACTION),
        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.STEP),
        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.PLAN),
        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.DECISION),

        (ThinkingNodeType.CLAIM, ThinkingNodeType.DECISION),
    },

    # A 推进到 B：过程流 / 思考流。
    ThinkingEdgeType.LEADS_TO: {
        (ThinkingNodeType.GOAL, ThinkingNodeType.QUESTION),
        (ThinkingNodeType.GOAL, ThinkingNodeType.PLAN),

        (ThinkingNodeType.QUESTION, ThinkingNodeType.HYPOTHESIS),
        (ThinkingNodeType.QUESTION, ThinkingNodeType.PLAN),
        (ThinkingNodeType.QUESTION, ThinkingNodeType.CLAIM),

        (ThinkingNodeType.HYPOTHESIS, ThinkingNodeType.PLAN),
        (ThinkingNodeType.HYPOTHESIS, ThinkingNodeType.ACTION),

        (ThinkingNodeType.PLAN, ThinkingNodeType.STEP),
        (ThinkingNodeType.STEP, ThinkingNodeType.ACTION),
        (ThinkingNodeType.ACTION, ThinkingNodeType.OBSERVATION),

        (ThinkingNodeType.OBSERVATION, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.EVIDENCE, ThinkingNodeType.CLAIM),

        (ThinkingNodeType.CLAIM, ThinkingNodeType.DECISION),
        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.DECISION),
        (ThinkingNodeType.DECISION, ThinkingNodeType.PLAN),
        (ThinkingNodeType.DECISION, ThinkingNodeType.ACTION),

        (ThinkingNodeType.ERROR, ThinkingNodeType.CRITIQUE),
        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.PLAN),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.SUMMARY),
        (ThinkingNodeType.SUMMARY, ThinkingNodeType.MEMORY),
    },

    # A 从 B 推导而来：方向是“结论 -> 来源”。
    ThinkingEdgeType.DERIVES_FROM: {
        (ThinkingNodeType.CLAIM, ThinkingNodeType.EVIDENCE),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.OBSERVATION),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.ASSUMPTION),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.CLAIM),

        (ThinkingNodeType.HYPOTHESIS, ThinkingNodeType.EVIDENCE),
        (ThinkingNodeType.HYPOTHESIS, ThinkingNodeType.OBSERVATION),
        (ThinkingNodeType.HYPOTHESIS, ThinkingNodeType.ASSUMPTION),

        (ThinkingNodeType.DECISION, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.DECISION, ThinkingNodeType.CRITIQUE),

        (ThinkingNodeType.SUMMARY, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.SUMMARY, ThinkingNodeType.OBSERVATION),
        (ThinkingNodeType.SUMMARY, ThinkingNodeType.DECISION),
    },

    # A 回答 B：答案节点 -> 问题 / 目标。
    ThinkingEdgeType.ANSWERS: {
        (ThinkingNodeType.CLAIM, ThinkingNodeType.QUESTION),
        (ThinkingNodeType.SUMMARY, ThinkingNodeType.QUESTION),
        (ThinkingNodeType.DECISION, ThinkingNodeType.QUESTION),
        (ThinkingNodeType.PLAN, ThinkingNodeType.QUESTION),

        (ThinkingNodeType.PLAN, ThinkingNodeType.GOAL),
        (ThinkingNodeType.DECISION, ThinkingNodeType.GOAL),
        (ThinkingNodeType.SUMMARY, ThinkingNodeType.GOAL),
    },

    # A 细化 B：A 是 B 的更具体版本。
    ThinkingEdgeType.REFINES: {
        (ThinkingNodeType.QUESTION, ThinkingNodeType.QUESTION),
        (ThinkingNodeType.HYPOTHESIS, ThinkingNodeType.HYPOTHESIS),
        (ThinkingNodeType.CLAIM, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.PLAN, ThinkingNodeType.PLAN),
        (ThinkingNodeType.STEP, ThinkingNodeType.STEP),
        (ThinkingNodeType.ACTION, ThinkingNodeType.ACTION),
        (ThinkingNodeType.CRITIQUE, ThinkingNodeType.CRITIQUE),
        (ThinkingNodeType.SUMMARY, ThinkingNodeType.SUMMARY),

        (ThinkingNodeType.STEP, ThinkingNodeType.PLAN),
        (ThinkingNodeType.ACTION, ThinkingNodeType.STEP),
    },

    # A 观察 / 验证 B。
    ThinkingEdgeType.OBSERVES: {
        (ThinkingNodeType.OBSERVATION, ThinkingNodeType.ACTION),
        (ThinkingNodeType.OBSERVATION, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.OBSERVATION, ThinkingNodeType.HYPOTHESIS),
        (ThinkingNodeType.EVIDENCE, ThinkingNodeType.CLAIM),
        (ThinkingNodeType.EVIDENCE, ThinkingNodeType.HYPOTHESIS),
    },
}

class ThinkingGraph:
    """
    思考图实例。
    - agent swarm 内部全部 agent 共享。
    - 可随时提取出子图。
    - 该实例会受到多个 agent 的并发影响。
    
    需要保存：
    - 所有的边
    - 所有的节点
    """

    def __init__(self):
        # 在初始化时先检查 schema 是否有出问题。
        ThinkingGraph.validate_edge_schema()

        # 然后，创建类。
        self.edge_dict: Dict[int, ThinkingGraphEdge] = {}
        self.node_dict: Dict[int, ThinkingGraphNode] = {}

        self._next_object_id: int = 0

        # 图版本    
        self._version: int = 0
        self._transaction_id: int = 0
        self._transaction_log: List[ThinkingGraphTransactionRecord] = []

        # 锁
        self._lock = asyncio.Lock()

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if dataclasses.is_dataclass(value):
            return {
                field.name: ThinkingGraph._serialize_value(getattr(value, field.name))
                for field in dataclasses.fields(value)
            }
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {str(key): ThinkingGraph._serialize_value(val) for key, val in value.items()}
        if isinstance(value, list):
            return [ThinkingGraph._serialize_value(item) for item in value]
        if isinstance(value, tuple):
            return [ThinkingGraph._serialize_value(item) for item in value]
        if isinstance(value, set):
            return [ThinkingGraph._serialize_value(item) for item in sorted(value, key=repr)]
        return value

    @staticmethod
    def _deserialize_payload(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: ThinkingGraph._deserialize_payload(val) for key, val in value.items()}
        if isinstance(value, list):
            return [ThinkingGraph._deserialize_payload(item) for item in value]
        return value

    @staticmethod
    def _deserialize_node_type(value: Any) -> ThinkingNodeType:
        if isinstance(value, ThinkingNodeType):
            return value
        return ThinkingNodeType(str(value))

    @staticmethod
    def _deserialize_edge_type(value: Any) -> ThinkingEdgeType:
        if isinstance(value, ThinkingEdgeType):
            return value
        return ThinkingEdgeType(str(value))

    def _alloc_id(self) -> int:
        """
        得到一个 id。
        """
        obj_id = self._next_object_id
        self._next_object_id += 1
        return obj_id

    @property
    def version(self) -> int:
        """
        输出当前图版本。
        """
        return self._version

    @property
    def transaction_log(self) -> List[ThinkingGraphTransactionRecord]:
        """返回只读事务日志快照。"""
        return list(self._transaction_log)

    def serialize(self) -> Dict[str, Any]:
        """Return a JSON-safe snapshot of the thinking graph."""
        return {
            "format": "thinking-graph/config",
            "schema_version": "1.0",
            "version": self._version,
            "next_object_id": self._next_object_id,
            "transaction_id": self._transaction_id,
            "nodes": {
                str(nid): ThinkingGraph._serialize_value(node)
                for nid, node in self.node_dict.items()
            },
            "edges": {
                str(eid): ThinkingGraph._serialize_value(edge)
                for eid, edge in self.edge_dict.items()
            },
            "transaction_log": [
                ThinkingGraph._serialize_value(record)
                for record in self._transaction_log
            ],
            "node_count": len(self.node_dict),
            "edge_count": len(self.edge_dict),
            "transaction_count": len(self._transaction_log),
            "last_transaction_id": (
                self._transaction_log[-1].transaction_id if self._transaction_log else None
            ),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Backward-compatible alias for :meth:`serialize`."""
        return self.serialize()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThinkingGraph":
        """Restore a thinking graph from :meth:`serialize` output."""
        if not isinstance(data, dict):
            raise TypeError("ThinkingGraph.from_dict expects a dict.")
        schema_version = data.get("schema_version")
        if schema_version not in (None, "1.0"):
            raise ValueError(f"Unsupported thinking graph schema version: {schema_version}")

        graph = cls()
        graph._version = int(data.get("version", 0) or 0)
        graph._next_object_id = int(data.get("next_object_id", 0) or 0)
        graph._transaction_id = int(data.get("transaction_id", 0) or 0)

        graph.node_dict.clear()
        graph.edge_dict.clear()
        graph._transaction_log.clear()

        for raw_id, node_data in data.get("nodes", {}).items():
            node_id = int(raw_id)
            if not isinstance(node_data, dict):
                raise TypeError(f"Invalid node payload for id {raw_id!r}")
            graph.node_dict[node_id] = ThinkingGraphNode(
                id=int(node_data["id"]),
                node_type=cls._deserialize_node_type(node_data["node_type"]),
                info=str(node_data.get("info", "")),
                tags=[str(tag) for tag in (node_data.get("tags") or [])],
                created_by=str(node_data.get("created_by") or "system"),
                confidence=float(node_data.get("confidence", 1.0)),
                description=str(node_data.get("description", "")),
                payload=cls._deserialize_payload(dict(node_data.get("payload") or {})),
            )

        for raw_id, edge_data in data.get("edges", {}).items():
            edge_id = int(raw_id)
            if not isinstance(edge_data, dict):
                raise TypeError(f"Invalid edge payload for id {raw_id!r}")
            graph.edge_dict[edge_id] = ThinkingGraphEdge(
                id=int(edge_data["id"]),
                edge_type=cls._deserialize_edge_type(edge_data["edge_type"]),
                source_id=int(edge_data["source_id"]),
                target_id=int(edge_data["target_id"]),
                created_by=str(edge_data.get("created_by", "system")),
                description=str(edge_data.get("description", "")),
                strength=float(edge_data.get("strength", 1.0)),
            )

        for record_data in data.get("transaction_log", []):
            if not isinstance(record_data, dict):
                raise TypeError("Invalid transaction record payload.")
            graph._transaction_log.append(
                ThinkingGraphTransactionRecord(
                    transaction_id=int(record_data["transaction_id"]),
                    operation=str(record_data.get("operation", "")),
                    object_kind=str(record_data.get("object_kind", "")),
                    object_id=int(record_data.get("object_id", 0)),
                    before=cls._deserialize_payload(record_data.get("before")),
                    after=cls._deserialize_payload(record_data.get("after")),
                    version_before=int(record_data.get("version_before", 0)),
                    version_after=int(record_data.get("version_after", 0)),
                    created_by=str(record_data.get("created_by") or "system"),
                    timestamp=str(record_data.get("timestamp") or ""),
                    metadata=cls._deserialize_payload(dict(record_data.get("metadata") or {})),
                )
            )

        if graph._next_object_id <= 0:
            used_ids = list(graph.node_dict.keys()) + list(graph.edge_dict.keys())
            graph._next_object_id = (max(used_ids) + 1) if used_ids else 0

        if graph._transaction_id <= 0:
            graph._transaction_id = len(graph._transaction_log)

        return graph

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> "ThinkingGraph":
        """Alias for :meth:`from_dict`."""
        return cls.from_dict(data)

    async def get_full_graph(self) -> Dict[str, Any]:
        """
        全量读取图（线程安全）。
        返回包含所有节点、边及元信息的字典。
        """
        async with self._lock:
            return self.to_dict()

    @staticmethod
    def _snapshot_object(obj: Optional[Any]) -> Optional[Dict[str, Any]]:
        if obj is None:
            return None
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        if isinstance(obj, dict):
            return dict(obj)
        return {"value": obj}

    def _next_transaction_id(self) -> int:
        tx_id = self._transaction_id
        self._transaction_id += 1
        return tx_id

    def _record_transaction(
        self,
        *,
        operation: str,
        object_kind: str,
        object_id: int,
        before: Optional[Any],
        after: Optional[Any],
        created_by: str,
        version_before: int,
        version_after: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ThinkingGraphTransactionRecord:
        record = ThinkingGraphTransactionRecord(
            transaction_id=self._next_transaction_id(),
            operation=operation,
            object_kind=object_kind,
            object_id=object_id,
            before=self._snapshot_object(before),
            after=self._snapshot_object(after),
            version_before=version_before,
            version_after=version_after,
            created_by=created_by,
            metadata=dict(metadata or {}),
        )
        self._transaction_log.append(record)
        return record

    def clear_transaction_log(self) -> None:
        """清空事务日志。"""
        self._transaction_log.clear()

    def get_transaction_log(self) -> List[ThinkingGraphTransactionRecord]:
        """返回事务日志快照。"""
        return list(self._transaction_log)

    @staticmethod
    def validate_edge_schema() -> None:
        """
        检查 ALLOWED_EDGE_SCHEMA 自身是否合法。
        建议在模块加载后或 ThinkingGraph 初始化时调用一次。
        """
        missing_edges = set(ThinkingEdgeType) - set(ALLOWED_EDGE_SCHEMA.keys())
        extra_edges = set(ALLOWED_EDGE_SCHEMA.keys()) - set(ThinkingEdgeType)

        if missing_edges:
            raise ValueError(f"Missing edge schema for: {missing_edges}")

        if extra_edges:
            raise ValueError(f"Unknown edge schema keys: {extra_edges}")

        for edge_type, pairs in ALLOWED_EDGE_SCHEMA.items():
            if not isinstance(edge_type, ThinkingEdgeType):
                raise TypeError(f"Invalid edge type key: {edge_type!r}")

            if not isinstance(pairs, set):
                raise TypeError(f"Schema for {edge_type.value} must be a set.")

            for pair in pairs:
                if not isinstance(pair, tuple) or len(pair) != 2:
                    raise TypeError(
                        f"Invalid schema pair for {edge_type.value}: {pair!r}"
                    )

                source_type, target_type = pair

                if not isinstance(source_type, ThinkingNodeType):
                    raise TypeError(
                        f"Invalid source node type for {edge_type.value}: {source_type!r}"
                    )

                if not isinstance(target_type, ThinkingNodeType):
                    raise TypeError(
                        f"Invalid target node type for {edge_type.value}: {target_type!r}"
                    )


    async def add_node(
        self,
        *,
        node_type: ThinkingNodeType,
        info: str,
        tags: Optional[List[str]] = None,
        created_by: str = "system",
        confidence: float = 1.0,
        description: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        加入一个新的思考图节点。

        Args:
            node_type: 加入的节点类型。
            info: 加入的节点信息。
            tags: 加入的节点标签。
            created_by: 创建者。
            confidence: 置信度。
            description: 节点描述。
            payload: 额外信息。
        """
        # 保证信息不得为空。
        await self._validate_node_input(
            node_type=node_type,
            info=info.strip(),
            tags=list(tags or []),
            created_by=created_by,
            confidence=max(0.0, min(1.0, confidence)),
            payload=dict(payload or {}),
        )

        async with self._lock:

            version_before = self._version
            node_id = self._alloc_id()
            node = ThinkingGraphNode(
                id=node_id,
                node_type=node_type,
                info=info.strip(),
                tags=list(tags or []),
                created_by=created_by,
                confidence=max(0.0, min(1.0, confidence)),
                description=description,
                payload=dict(payload or {}),
            )

            # 添加节点。
            self.node_dict[node_id] = node
            self._version += 1
            self._record_transaction(
                operation="add_node",
                object_kind="node",
                object_id=node_id,
                before=None,
                after=node,
                created_by=created_by,
                version_before=version_before,
                version_after=self._version,
                metadata={
                    "node_type": node_type.value,
                },
            )
            return node_id

    async def _validate_node_input(
        self,
        *,
        node_type: ThinkingNodeType,
        info: str,
        tags: Optional[List[str]],
        created_by: str,
        confidence: float,
        payload: Optional[Dict[str, Any]],
    ) -> None:
        """
        检查节点输入合法性。

        Args:
            node_type: 加入的节点类型。
            info: 加入的节点信息。
            tags: 加入的节点标签。
            created_by: 创建者。
            description: 边缘描述。
            payload: 额外信息。
        """
        if not isinstance(node_type, ThinkingNodeType):
            raise TypeError(f"Invalid node_type: {node_type!r}")

        if not isinstance(info, str) or not info.strip():
            raise ValueError("Node info cannot be empty.")

        if not isinstance(created_by, str) or not created_by.strip():
            raise ValueError("created_by cannot be empty.")

        if tags is not None:
            if not isinstance(tags, list):
                raise TypeError("tags must be a list of strings.")

            for tag in tags:
                if not isinstance(tag, str) or not tag.strip():
                    raise ValueError(f"Invalid tag: {tag!r}")

        if not isinstance(confidence, Real) or isinstance(confidence, bool):
            raise TypeError("confidence must be a real number.")

        if not math.isfinite(float(confidence)):
            raise ValueError("confidence must be finite.")

        if payload is not None and not isinstance(payload, dict):
            raise TypeError("payload must be a dict.")
    
    async def add_edge(
        self,
        *,
        edge_type: ThinkingEdgeType,
        source_id: int,
        target_id: int,
        created_by: str = "system",
        description: str = "",
        strength: float = 1.0,
    ) -> int:
        """
        加入新连接。
        在写入前会检查 (source_type, target_type) 是否被 edge_type 的 schema 允许，
        不合法则直接拒绝，避免脏边进入图中。

        Args:
            edge_type: 连接关系类型。
            source_id: 源节点。
            target_id: 目标节点。
            created_by: 创建者。
            description: 边缘描述。
            strength: 连接力度。
        """
        await self._validate_edge_input(
            edge_type=edge_type,
            source_id=source_id,
            target_id=target_id,
            created_by=created_by,
            strength=max(0.0, min(1.0, strength)),
        )

        # 开始写入，上锁。
        async with self._lock:
            version_before = self._version
            source_node = self.node_dict.get(source_id)
            target_node = self.node_dict.get(target_id)

            if source_node is None:
                raise KeyError(f"Source node {source_id} does not exist.")
            if target_node is None:
                raise KeyError(f"Target node {target_id} does not exist.")

            # 创建前检查 schema，避免脏边入图
            if not await self._is_edge_allowed(
                edge_type=edge_type,
                source_type=source_node.node_type,
                target_type=target_node.node_type,
            ):
                raise ValueError(
                    f"Invalid edge schema: "
                    f"{source_node.node_type.value} -[{edge_type.value}]-> "
                    f"{target_node.node_type.value}"
                )

            edge_id = self._alloc_id()
            edge = ThinkingGraphEdge(
                id=edge_id,
                edge_type=edge_type,
                source_id=source_id,
                target_id=target_id,
                created_by=created_by,
                description=description,
                strength=max(0.0, min(1.0, strength)),
            )
            self.edge_dict[edge_id] = edge
            self._version += 1
            self._record_transaction(
                operation="add_edge",
                object_kind="edge",
                object_id=edge_id,
                before=None,
                after=edge,
                created_by=created_by,
                version_before=version_before,
                version_after=self._version,
                metadata={
                    "edge_type": edge_type.value,
                    "source_id": source_id,
                    "target_id": target_id,
                },
            )

        return edge_id

    async def modify_node(
        self,
        node_id: int,
        *,
        node_type: Optional[ThinkingNodeType] = None,
        info: Optional[str] = None,
        tags: Optional[List[str]] = None,
        created_by: Optional[str] = None,
        confidence: Optional[float] = None,
        description: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> ThinkingGraphNode:
        """
        修改现有节点的字段。

        未传入的字段保持不变。修改会在写锁内完成，并在提交后递增版本号。
        """
        async with self._lock:
            version_before = self._version
            node = self.node_dict.get(node_id)
            if node is None:
                raise KeyError(f"Node {node_id} does not exist.")

            new_node_type = node_type if node_type is not None else node.node_type
            new_info = info if info is not None else node.info
            new_tags = list(tags) if tags is not None else list(node.tags)
            new_created_by = created_by if created_by is not None else node.created_by
            new_confidence = confidence if confidence is not None else node.confidence
            new_description = description if description is not None else node.description
            new_payload = dict(payload) if payload is not None else dict(node.payload)

            await self._validate_node_input(
                node_type=new_node_type,
                info=new_info.strip(),
                tags=new_tags,
                created_by=new_created_by,
                confidence=max(0.0, min(1.0, new_confidence)),
                payload=new_payload,
            )

            updated = ThinkingGraphNode(
                id=node.id,
                node_type=new_node_type,
                info=new_info.strip(),
                tags=new_tags,
                created_by=new_created_by,
                confidence=max(0.0, min(1.0, new_confidence)),
                description=new_description,
                payload=new_payload,
            )
            self.node_dict[node_id] = updated
            self._version += 1
            self._record_transaction(
                operation="modify_node",
                object_kind="node",
                object_id=node_id,
                before=node,
                after=updated,
                created_by=new_created_by,
                version_before=version_before,
                version_after=self._version,
                metadata={
                    "changed_fields": [
                        name for name, old, new in [
                            ("node_type", node.node_type, new_node_type),
                            ("info", node.info, new_info),
                            ("tags", node.tags, new_tags),
                            ("created_by", node.created_by, new_created_by),
                            ("confidence", node.confidence, new_confidence),
                            ("description", node.description, new_description),
                            ("payload", node.payload, new_payload),
                        ]
                        if old != new
                    ]
                },
            )
            return updated

    async def modify_edge(
        self,
        edge_id: int,
        *,
        edge_type: Optional[ThinkingEdgeType] = None,
        source_id: Optional[int] = None,
        target_id: Optional[int] = None,
        created_by: Optional[str] = None,
        description: Optional[str] = None,
        strength: Optional[float] = None,
    ) -> ThinkingGraphEdge:
        """
        修改现有边的字段。

        当修改 edge_type 或端点时，会重新校验 schema 合法性。
        未传入的字段保持不变。
        """
        async with self._lock:
            version_before = self._version
            edge = self.edge_dict.get(edge_id)
            if edge is None:
                raise KeyError(f"Edge {edge_id} does not exist.")

            new_edge_type = edge_type if edge_type is not None else edge.edge_type
            new_source_id = source_id if source_id is not None else edge.source_id
            new_target_id = target_id if target_id is not None else edge.target_id
            new_created_by = created_by if created_by is not None else edge.created_by
            new_description = description if description is not None else edge.description
            new_strength = strength if strength is not None else edge.strength

            await self._validate_edge_input(
                edge_type=new_edge_type,
                source_id=new_source_id,
                target_id=new_target_id,
                created_by=new_created_by,
                strength=max(0.0, min(1.0, new_strength)),
            )

            source_node = self.node_dict.get(new_source_id)
            target_node = self.node_dict.get(new_target_id)
            if source_node is None:
                raise KeyError(f"Source node {new_source_id} does not exist.")
            if target_node is None:
                raise KeyError(f"Target node {new_target_id} does not exist.")

            if not await self._is_edge_allowed(
                edge_type=new_edge_type,
                source_type=source_node.node_type,
                target_type=target_node.node_type,
            ):
                raise ValueError(
                    "Invalid edge schema: "
                    f"{source_node.node_type.value} -[{new_edge_type.value}]-> "
                    f"{target_node.node_type.value}"
                )

            updated = ThinkingGraphEdge(
                id=edge.id,
                edge_type=new_edge_type,
                source_id=new_source_id,
                target_id=new_target_id,
                created_by=new_created_by,
                description=new_description,
                strength=max(0.0, min(1.0, new_strength)),
            )
            self.edge_dict[edge_id] = updated
            self._version += 1
            self._record_transaction(
                operation="modify_edge",
                object_kind="edge",
                object_id=edge_id,
                before=edge,
                after=updated,
                created_by=new_created_by,
                version_before=version_before,
                version_after=self._version,
                metadata={
                    "changed_fields": [
                        name for name, old, new in [
                            ("edge_type", edge.edge_type, new_edge_type),
                            ("source_id", edge.source_id, new_source_id),
                            ("target_id", edge.target_id, new_target_id),
                            ("created_by", edge.created_by, new_created_by),
                            ("description", edge.description, new_description),
                            ("strength", edge.strength, new_strength),
                        ]
                        if old != new
                    ]
                },
            )
            return updated
    
    async def _validate_edge_input(
        self,
        *,
        edge_type: ThinkingEdgeType,
        source_id: int,
        target_id: int,
        created_by: str,
        strength: float,
    ) -> None:
        """
        检查加入新连接前的有效性。

        Args:
            edge_type: 连接关系类型。
            source_id: 源节点。
            target_id: 目标节点。
            created_by: 创建者。
            strength: 连接力度。
        """
        if not isinstance(edge_type, ThinkingEdgeType):
            raise TypeError(f"Invalid edge_type: {edge_type!r}")

        if not isinstance(source_id, int):
            raise TypeError("source_id must be int.")

        if not isinstance(target_id, int):
            raise TypeError("target_id must be int.")

        if source_id == target_id:
            raise ValueError("Self-loop edge is not allowed.")

        if not isinstance(created_by, str) or not created_by.strip():
            raise ValueError("created_by cannot be empty.")

        if not isinstance(strength, Real) or isinstance(strength, bool):
            raise TypeError("strength must be a real number.")

        if not math.isfinite(float(strength)):
            raise ValueError("strength must be finite.")
    
    async def _is_edge_allowed(
        self,
        *,
        edge_type: ThinkingEdgeType,
        source_type: ThinkingNodeType,
        target_type: ThinkingNodeType,
    ) -> bool:
        return (source_type, target_type) in ALLOWED_EDGE_SCHEMA.get(edge_type, set())

    async def validate_incremental_context(
        self,
        center_id: int,
        max_hops: int = 1,
    ) -> None:
        """
        增量一致性检查：以 center_id 为中心，检查 max_hops 跳范围内的局部子图。

        相比 validate_graph_integrity 的全量扫描，这个函数只关注与增量相关的
        局部区域，适合在 add_node / add_edge 之后调用。

        检查项：
        1. 局部节点的基础有效性。
        2. 局部边的 schema 合规性。
        3. 语义冲突检测（如同一对节点间同时存在 SUPPORTS 和 CONTRADICTS）。

        Args:
            center_id: 中心节点 ID（通常是刚增量的节点）。
            max_hops: 最大扩散跳数，默认 1（只检查直接邻居）。

        Raises:
            KeyError: center_id 不存在。
            ValueError: 局部子图存在不一致。
        """
        if center_id not in self.node_dict:
            raise KeyError(f"Center node {center_id} does not exist.")

        if max_hops < 0:
            raise ValueError("max_hops must be non-negative.")

        # ---------- 1. 收集局部子图 ----------
        local_node_ids: Set[int] = {center_id}
        current_frontier: Set[int] = {center_id}

        for _ in range(max_hops):
            next_frontier: Set[int] = set()
            for edge in self.edge_dict.values():
                if edge.source_id in current_frontier:
                    next_frontier.add(edge.target_id)
                if edge.target_id in current_frontier:
                    next_frontier.add(edge.source_id)
            local_node_ids.update(next_frontier)
            current_frontier = next_frontier

        # 过滤掉不存在的节点（理论上不应该出现，但防御性处理）
        local_node_ids = {nid for nid in local_node_ids if nid in self.node_dict}

        # 收集局部边：两端都在 local_node_ids 中
        local_edges: List[ThinkingGraphEdge] = []
        for edge in self.edge_dict.values():
            if edge.source_id in local_node_ids and edge.target_id in local_node_ids:
                local_edges.append(edge)

        # ---------- 2. 验证局部节点 ----------
        for nid in local_node_ids:
            node = self.node_dict[nid]
            await self._validate_node_input(
                node_type=node.node_type,
                info=node.info,
                tags=node.tags,
                created_by=node.created_by,
                confidence=node.confidence,
                payload=node.payload,
            )

        # ---------- 3. 验证局部边 ----------
        for edge in local_edges:
            await self._validate_edge_input(
                edge_type=edge.edge_type,
                source_id=edge.source_id,
                target_id=edge.target_id,
                created_by=edge.created_by,
                strength=edge.strength,
            )

            source_node = self.node_dict[edge.source_id]
            target_node = self.node_dict[edge.target_id]

            if not await self._is_edge_allowed(
                edge_type=edge.edge_type,
                source_type=source_node.node_type,
                target_type=target_node.node_type,
            ):
                raise ValueError(
                    "Invalid edge schema in local context: "
                    f"edge={edge.id}, "
                    f"{source_node.node_type.value} "
                    f"-[{edge.edge_type.value}]-> "
                    f"{target_node.node_type.value}"
                )

        # ---------- 4. 语义冲突检测 ----------
        # 统计 (source, target) 之间的所有边类型
        edge_types_between: Dict[Tuple[int, int], Set[ThinkingEdgeType]] = defaultdict(set)
        for edge in local_edges:
            key = (edge.source_id, edge.target_id)
            edge_types_between[key].add(edge.edge_type)

        for (src, tgt), etypes in edge_types_between.items():
            # 冲突规则 1：不能同时 SUPPORTS + CONTRADICTS
            if (
                ThinkingEdgeType.SUPPORTS in etypes
                and ThinkingEdgeType.CONTRADICTS in etypes
            ):
                raise ValueError(
                    f"Semantic conflict between node {src} and {tgt}: "
                    "both SUPPORTS and CONTRADICTS exist."
                )

            # 冲突规则 2：不能同时 SUPPORTS + OPPOSES（支持又反对）
            if (
                ThinkingEdgeType.SUPPORTS in etypes
                and ThinkingEdgeType.OPPOSES in etypes
            ):
                raise ValueError(
                    f"Semantic conflict between node {src} and {tgt}: "
                    "both SUPPORTS and OPPOSES exist."
                )

            # 冲突规则 3：不能同时 OPPOSES + CONTRADICTS（语义重复，保留 CONTRADICTS 即可）
            if (
                ThinkingEdgeType.OPPOSES in etypes
                and ThinkingEdgeType.CONTRADICTS in etypes
            ):
                raise ValueError(
                    f"Semantic conflict between node {src} and {tgt}: "
                    "both OPPOSES and CONTRADICTS exist."
                )

    async def validate_graph_integrity(self) -> None:
        """
        检查当前图整体一致性。
        - 这是一次全量检查，所以我还需要检查部分一致性的函数。
        """
        seen_ids = set()

        # 基本检查
        for node_id, node in self.node_dict.items():
            # 规则1：节点 id 和字典内储存的 id 必须一致
            if node_id != node.id:
                raise ValueError(f"Node id mismatch: key={node_id}, node.id={node.id}")
            
            # 规则2：图中禁止存在同 id 节点
            if node.id in seen_ids:
                raise ValueError(f"Duplicate object id: {node.id}")

            seen_ids.add(node.id)
            
            # 检查节点自身
            await self._validate_node_input(
                node_type=node.node_type,
                info=node.info,
                tags=node.tags,
                created_by=node.created_by,
                confidence=node.confidence,
                payload=node.payload,
            )
        
        # 检查边
        for edge_id, edge in self.edge_dict.items():
            if edge_id != edge.id:
                raise ValueError(f"Edge id mismatch: key={edge_id}, edge.id={edge.id}")

            if edge.id in seen_ids:
                raise ValueError(f"Duplicate object id: {edge.id}")

            seen_ids.add(edge.id)

            # 检查输入
            await self._validate_edge_input(
                edge_type=edge.edge_type,
                source_id=edge.source_id,
                target_id=edge.target_id,
                created_by=edge.created_by,
                strength=edge.strength,
            )

            # 检查边缘节点信息
            if edge.source_id not in self.node_dict:
                raise ValueError(f"Edge {edge.id} has missing source node: {edge.source_id}")

            if edge.target_id not in self.node_dict:
                raise ValueError(f"Edge {edge.id} has missing target node: {edge.target_id}")

            source_node = self.node_dict[edge.source_id]
            target_node = self.node_dict[edge.target_id]

            # 检查节点连接有效性
            if not await self._is_edge_allowed(
                edge.edge_type,
                source_node.node_type,
                target_node.node_type,
            ):
                raise ValueError(
                    "Invalid edge schema: "
                    f"edge={edge.id}, "
                    f"{source_node.node_type.value} "
                    f"-[{edge.edge_type.value}]-> "
                    f"{target_node.node_type.value}"
                )
