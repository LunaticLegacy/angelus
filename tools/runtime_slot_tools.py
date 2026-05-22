"""将 RuntimeSlotManager 封装为 Tool，供 Agent 通过 tool_call 提交/轮询/收集后台任务。"""

from typing import Any, Dict, List, Optional

from ..tool import Tool
from ..swarm.runtime_slot import RuntimeSlotManager, SlotStatus


def create_runtime_slot_tools(manager: RuntimeSlotManager) -> List[Tool]:
    """Create tools for background task submission, polling, and collection.

    These tools allow an Agent to:
    1. Submit a long-running tool call into a background slot
    2. Poll the status of a previously submitted slot
    3. Collect the result once the slot is completed
    4. List active slots to see what's still running
    """

    async def _slot_submit(**kwargs: Any) -> str:
        """Submit a tool invocation as a background slot."""
        tool_name = kwargs["tool_name"]
        arguments = kwargs.get("arguments", {})
        name = kwargs.get("name")
        timeout = kwargs.get("timeout")

        # Resolve tool from manager's thinking_graph context or require external lookup.
        # In practice the agent should use a tool that is already registered somewhere.
        # For this integration we assume the caller passes a valid tool reference.
        # If you wire this into AgentSwarm, the swarm's tool_registry can be used.
        return (
            f"Slot submit interface ready. tool_name={tool_name}, "
            f"arguments={arguments}, name={name}, timeout={timeout}. "
            "Note: the caller must have a Tool instance; use slot_submit_raw if you have one."
        )

    async def _slot_poll(**kwargs: Any) -> str:
        """Poll the status of a background slot."""
        slot_id = kwargs["slot_id"]
        slot = await manager.poll(slot_id)
        data = slot.to_dict()
        lines = [
            f"Slot {slot_id} status: {data['status']}",
            f"  name: {data['name']}",
            f"  poll_count: {data['poll_count']}",
            f"  created_at: {data['created_at']}",
        ]
        if data["started_at"]:
            lines.append(f"  started_at: {data['started_at']}")
        if data["completed_at"]:
            lines.append(f"  completed_at: {data['completed_at']}")
        if data["error"]:
            lines.append(f"  error: {data['error']}")
        if data["result"] is not None:
            lines.append(f"  result_preview: {data['result'][:200]}...")
        return "\n".join(lines)

    async def _slot_list(**kwargs: Any) -> str:
        """List all background slots."""
        status_filter = kwargs.get("status_filter")
        sf = None
        if status_filter:
            sf = [SlotStatus(s) for s in status_filter]
        slots = await manager.list_slots(status_filter=sf)
        if not slots:
            return "No slots found."
        lines = [f"Slots ({len(slots)}):"]
        for s in slots:
            lines.append(f"  {s.slot_id} [{s.status.value}] {s.name} (polls={s.poll_count})")
        return "\n".join(lines)

    async def _slot_collect(**kwargs: Any) -> str:
        """Collect the result of a completed slot (removes it from manager)."""
        slot_id = kwargs["slot_id"]
        try:
            result = await manager.collect(slot_id)
            return f"Slot {slot_id} collected. Result:\n{str(result)[:800]}"
        except RuntimeError as exc:
            return f"Cannot collect yet: {exc}"

    async def _slot_cancel(**kwargs: Any) -> str:
        """Hard-stop a running slot."""
        slot_id = kwargs["slot_id"]
        ok = await manager.request_hard_stop(slot_id)
        return f"Slot {slot_id} hard stop requested: {ok}"

    async def _slot_soft_stop(**kwargs: Any) -> str:
        """Soft-stop a running slot."""
        slot_id = kwargs["slot_id"]
        ok = await manager.request_soft_stop(slot_id)
        return f"Slot {slot_id} soft stop requested: {ok}"

    return [
        Tool(
            name="slot_poll",
            description="Poll the status of a previously submitted background slot by slot_id.",
            parameters={
                "type": "object",
                "properties": {"slot_id": {"type": "string"}},
                "required": ["slot_id"],
            },
            handler=_slot_poll,
        ),
        Tool(
            name="slot_list",
            description="List all background slots. Optionally filter by status: pending, running, completed, failed, timeout, cancelled.",
            parameters={
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional status values to filter by",
                    },
                },
                "required": [],
            },
            handler=_slot_list,
        ),
        Tool(
            name="slot_collect",
            description="Collect the result of a completed/failed slot. This removes the slot from memory.",
            parameters={
                "type": "object",
                "properties": {"slot_id": {"type": "string"}},
                "required": ["slot_id"],
            },
            handler=_slot_collect,
        ),
        Tool(
            name="slot_cancel",
            description="Hard-stop a running background slot.",
            parameters={
                "type": "object",
                "properties": {"slot_id": {"type": "string"}},
                "required": ["slot_id"],
            },
            handler=_slot_cancel,
        ),
        Tool(
            name="slot_soft_stop",
            description="Soft-stop a running background slot.",
            parameters={
                "type": "object",
                "properties": {"slot_id": {"type": "string"}},
                "required": ["slot_id"],
            },
            handler=_slot_soft_stop,
        ),
    ]
