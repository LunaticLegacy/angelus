"""Runtime Slot —— 后台执行服务。

为耗时任务（>30s 或不可预期完成时间）提供"提交-轮询-收集"模式。
每个任务被放入一个 Slot，Agent 可以：

1. `slot_submit(tool, args)` —— 提交后台任务，获得 slot_id
2. `slot_poll(slot_id)`     —— 查询任务状态
3. `slot_collect(slot_id)`  —— 收集已完成任务的结果

与 ThinkingGraph 集成：
- 提交时自动创建 `action` 节点
- 完成时自动创建 `observation` 节点，并通过 `produces` 边关联
- 失败时自动创建 `error` 节点
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

from ..thinking_graph import ThinkingGraph, ThinkingNodeType, ThinkingEdgeType
from ..tool import Tool


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class SlotStatus(str, Enum):
    PENDING = "pending"      # 已提交，尚未开始
    RUNNING = "running"      # 正在执行
    COMPLETED = "completed"  # 成功完成
    FAILED = "failed"        # 执行失败
    TIMEOUT = "timeout"      # 超时终止
    CANCELLED = "cancelled"  # 被取消


@dataclass
class RuntimeSlot:
    """单个后台任务槽位。"""

    slot_id: str
    name: str                       # 人类可读的任务名
    task_coro: Callable[[], Coroutine[Any, Any, Any]]
    status: SlotStatus = SlotStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    timeout: Optional[float] = None
    stop_requested: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    last_polled_at: Optional[str] = None
    poll_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ThinkingGraph integration
    action_node_id: Optional[int] = None
    result_node_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "name": self.name,
            "status": self.status.value,
            "result": str(self.result)[:500] if self.result is not None else None,
            "error": self.error,
            "timeout": self.timeout,
            "stop_requested": self.stop_requested,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "last_polled_at": self.last_polled_at,
            "poll_count": self.poll_count,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# RuntimeSlotManager
# ---------------------------------------------------------------------------

class RuntimeSlotManager:
    """管理后台任务槽位，支持提交、轮询、收集。

    Usage:
        manager = RuntimeSlotManager(thinking_graph=graph)
        slot_id = await manager.submit(tool, args, name="web_crawl")
        # ... 后续轮次 ...
        status = await manager.poll(slot_id)
        if status == SlotStatus.COMPLETED:
            result = await manager.collect(slot_id)
    """

    def __init__(
        self,
        thinking_graph: Optional[ThinkingGraph] = None,
        default_timeout: float = 300.0,
        max_concurrent: int = 4,
    ) -> None:
        self._slots: Dict[str, RuntimeSlot] = {}
        self._thinking_graph = thinking_graph
        self._default_timeout = default_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: Dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    async def submit(
        self,
        tool: Tool,
        arguments: Dict[str, Any],
        *,
        name: Optional[str] = None,
        timeout: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Submit a tool invocation as a background slot task.

        Returns:
            slot_id: UUID string for later polling / collection.
        """
        slot_id = uuid.uuid4().hex[:12]
        display_name = name or f"{tool.name}:{slot_id}"

        async def _coro():
            return await tool.execute(**arguments)

        slot = RuntimeSlot(
            slot_id=slot_id,
            name=display_name,
            task_coro=_coro,
            timeout=timeout or self._default_timeout,
            metadata=dict(metadata or {}),
        )

        # ThinkingGraph: record action node
        if self._thinking_graph is not None:
            node_id = await self._thinking_graph.add_node(
                node_type=ThinkingNodeType.ACTION,
                info=f"[Slot {slot_id}] {display_name}",
                tags=["slot", "background", tool.name],
                payload={"slot_id": slot_id, "tool": tool.name, "arguments": arguments},
            )
            slot.action_node_id = node_id

        self._slots[slot_id] = slot

        # Start immediately in background
        task = asyncio.create_task(self._run_slot(slot))
        self._tasks[slot_id] = task

        return slot_id

    # ------------------------------------------------------------------
    # Internal runner
    # ------------------------------------------------------------------

    async def _run_slot(self, slot: RuntimeSlot) -> None:
        """Execute the slot coroutine with semaphore + timeout."""
        slot.status = SlotStatus.RUNNING
        slot.started_at = datetime.now(timezone.utc).isoformat()

        try:
            async with self._semaphore:
                coro = slot.task_coro()
                if slot.timeout is not None:
                    result = await asyncio.wait_for(coro, timeout=slot.timeout)
                else:
                    result = await coro

            if slot.stop_requested is not None:
                slot.status = SlotStatus.CANCELLED
                if slot.stop_requested == "soft":
                    slot.error = "Soft stop requested"
                elif slot.stop_requested == "hard":
                    slot.error = "Hard stop requested"
                else:
                    slot.error = "Stopped"
                slot.completed_at = datetime.now(timezone.utc).isoformat()
                return

            slot.result = result
            slot.status = SlotStatus.COMPLETED
            slot.completed_at = datetime.now(timezone.utc).isoformat()

            # ThinkingGraph: record observation
            if self._thinking_graph is not None and slot.action_node_id is not None:
                obs_id = await self._thinking_graph.add_node(
                    node_type=ThinkingNodeType.OBSERVATION,
                    info=f"[Slot {slot.slot_id}] completed: {str(result)[:200]}",
                    tags=["slot", "completed"],
                    payload={"slot_id": slot.slot_id, "result_preview": str(result)[:500]},
                )
                slot.result_node_id = obs_id
                await self._thinking_graph.add_edge(
                    edge_type=ThinkingEdgeType.PRODUCES,
                    source_id=slot.action_node_id,
                    target_id=obs_id,
                )

        except asyncio.TimeoutError:
            slot.status = SlotStatus.TIMEOUT
            slot.error = f"Timeout after {slot.timeout}s"
            slot.completed_at = datetime.now(timezone.utc).isoformat()
            await self._record_error(slot, "timeout")

        except asyncio.CancelledError:
            slot.status = SlotStatus.CANCELLED
            if slot.stop_requested == "soft":
                slot.error = "Soft stop requested"
            elif slot.stop_requested == "hard":
                slot.error = "Hard stop requested"
            else:
                slot.error = "Cancelled by user/system"
            slot.completed_at = datetime.now(timezone.utc).isoformat()
            raise  # propagate cancellation

        except Exception as exc:
            slot.status = SlotStatus.FAILED
            slot.error = f"{type(exc).__name__}: {exc}"
            slot.completed_at = datetime.now(timezone.utc).isoformat()
            await self._record_error(slot, "exception")

        finally:
            self._tasks.pop(slot.slot_id, None)

    async def _record_error(self, slot: RuntimeSlot, kind: str) -> None:
        if self._thinking_graph is None or slot.action_node_id is None:
            return
        err_id = await self._thinking_graph.add_node(
            node_type=ThinkingNodeType.ERROR,
            info=f"[Slot {slot.slot_id}] {kind}: {slot.error}",
            tags=["slot", "background", kind],
            payload={"slot_id": slot.slot_id, "error": slot.error},
        )
        await self._thinking_graph.add_edge(
            edge_type=ThinkingEdgeType.BLOCKS,
            source_id=err_id,
            target_id=slot.action_node_id,
        )

    # ------------------------------------------------------------------
    # Poll
    # ------------------------------------------------------------------

    async def poll(self, slot_id: str) -> RuntimeSlot:
        """Poll a slot and return its current snapshot.

        Raises:
            KeyError: if slot_id does not exist.
        """
        if slot_id not in self._slots:
            raise KeyError(f"Slot {slot_id} not found")
        slot = self._slots[slot_id]
        slot.last_polled_at = datetime.now(timezone.utc).isoformat()
        slot.poll_count += 1
        return slot

    async def list_slots(
        self,
        status_filter: Optional[List[SlotStatus]] = None,
    ) -> List[RuntimeSlot]:
        """List all slots, optionally filtered by status."""
        slots = list(self._slots.values())
        if status_filter:
            sf = set(status_filter)
            slots = [s for s in slots if s.status in sf]
        return slots

    # ------------------------------------------------------------------
    # Collect
    # ------------------------------------------------------------------

    async def collect(self, slot_id: str) -> Any:
        """Collect the result of a completed/failed slot.

        After collection the slot is removed from memory.

        Raises:
            KeyError: if slot_id does not exist.
            RuntimeError: if slot is still RUNNING or PENDING.
        """
        if slot_id not in self._slots:
            raise KeyError(f"Slot {slot_id} not found")
        slot = self._slots[slot_id]

        if slot.status in (SlotStatus.PENDING, SlotStatus.RUNNING):
            raise RuntimeError(
                f"Slot {slot_id} is still {slot.status.value}; poll again later."
            )

        result = slot.result
        self._slots.pop(slot_id, None)
        return result

    async def request_soft_stop(self, slot_id: str) -> bool:
        """Request a soft stop for a running slot.

        Soft stop is cooperative: we cancel the task and wait for it to unwind
        so the coroutine has a chance to clean up before the manager returns.
        """
        if slot_id not in self._slots:
            raise KeyError(f"Slot {slot_id} not found")
        slot = self._slots[slot_id]
        task = self._tasks.get(slot_id)
        if task is None:
            return False
        slot.stop_requested = "soft"
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    async def request_hard_stop(self, slot_id: str) -> bool:
        """Request a hard stop for a running slot.

        Hard stop is immediate from the manager's perspective: the task is
        cancelled and this method returns without waiting for it to unwind.
        """
        if slot_id not in self._slots:
            raise KeyError(f"Slot {slot_id} not found")
        slot = self._slots[slot_id]
        task = self._tasks.get(slot_id)
        if task is None:
            return False
        slot.stop_requested = "hard"
        task.cancel()
        return True

    async def cancel(self, slot_id: str) -> bool:
        """Cancel a running slot. Alias for hard stop."""
        return await self.request_hard_stop(slot_id)

    async def soft_stop(self, slot_id: str) -> bool:
        """Alias for request_soft_stop."""
        return await self.request_soft_stop(slot_id)

    async def hard_stop(self, slot_id: str) -> bool:
        """Alias for request_hard_stop."""
        return await self.request_hard_stop(slot_id)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_count": len(self._slots),
            "active_tasks": len(self._tasks),
            "slots": {sid: s.to_dict() for sid, s in self._slots.items()},
        }

    def __repr__(self) -> str:
        counts: Dict[str, int] = {}
        for s in self._slots.values():
            counts[s.status.value] = counts.get(s.status.value, 0) + 1
        return f"RuntimeSlotManager(slots={len(self._slots)}, {counts})"
