"""Workflow execution tool — run staged DAGs of registered tool calls.

The agent invokes a single tool with a JSON describing multiple stages.
Each stage is an array of tool calls that execute in **parallel**.
Stages execute **sequentially**: stage N waits for all tools in stage N-1.

Purpose: let the agent compose small, focused tool calls instead of generating
a giant inline shell script that gets rewritten every turn.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from ..tool import Tool

if TYPE_CHECKING:
    from ..agent import Agent


# ── Helpers ──────────────────────────────────────────────────────────────────


def _check_stage_tool_limit(stages: List[Any], max_parallel: int) -> Optional[str]:
    """Validate that no stage exceeds the parallel tool limit."""
    for i, stage in enumerate(stages):
        if isinstance(stage, (list, tuple)) and len(stage) > max_parallel:
            return (
                f"Stage {i} has {len(stage)} parallel tools, "
                f"but max_concurrent_tools={max_parallel}. "
                f"Split into multiple stages or reduce the batch."
            )
    return None


def _normalize_stage(stage: Any) -> List[Dict[str, Any]]:
    """Normalise a stage to a list of tool definitions."""
    if isinstance(stage, dict) and "tool" in stage:
        return [stage]
    if isinstance(stage, (list, tuple)):
        items: List[Dict[str, Any]] = []
        for item in stage:
            if isinstance(item, dict) and "tool" in item:
                items.append(item)
            elif isinstance(item, str):
                items.append({"tool": item, "args": {}})
        return items
    if isinstance(stage, str):
        return [{"tool": stage, "args": {}}]
    return []


def _format_result(
    tool_name: str,
    elapsed: float,
    result: Any,
    *,
    truncate: int = 2000,
) -> str:
    """Format a single tool execution result for the workflow summary."""
    text = str(result) if result is not None else "(no output)"
    tag = f"[{elapsed:.1f}s]"
    if len(text) > truncate:
        text = text[:truncate] + f"\n[... truncated {len(text)} chars]"
    return f"  {tag} {tool_name}: {text}"


# ── Tool factory ─────────────────────────────────────────────────────────────


def create_workflow_tool(
    agent: Agent,
    max_parallel: int = 8,
) -> List[Tool]:
    """Create a workflow tool bound to an Agent's ToolRegistry.

    The tool accesses ``agent.tool_registry`` at runtime so it can dispatch
    any registered tool by name — ``shell``, ``ctf_*``, hotplug tools, etc.

    Args:
        agent: The Agent whose ToolRegistry to dispatch through.
        max_parallel: Hard limit on parallel tool calls per stage.

    Returns:
        A list containing one Tool (``run_workflow``).
    """

    async def _run_workflow(**kwargs: Any) -> str:
        workflow_raw: str = kwargs.get("workflow", "")
        if not workflow_raw:
            return "Error: 'workflow' parameter is required"

        try:
            workflow: dict = json.loads(workflow_raw)
        except json.JSONDecodeError as exc:
            return f"Error: invalid workflow JSON: {exc}"

        stages: List[Any] = workflow.get("stages", [])
        if not stages:
            return "Error: workflow has no stages"

        limit_error = _check_stage_tool_limit(stages, max_parallel)
        if limit_error:
            return f"Error: {limit_error}"

        registry = agent.tool_registry
        context: Dict[str, str] = {}
        report_lines: List[str] = []
        total_start = time.time()

        for stage_idx, stage_raw in enumerate(stages):
            stage_tools = _normalize_stage(stage_raw)
            if not stage_tools:
                report_lines.append(f"\n--- Stage {stage_idx}: (empty, skipped) ---")
                continue

            report_lines.append(f"\n--- Stage {stage_idx}: {len(stage_tools)} parallel tool(s) ---")

            # Resolve ``$var`` references in args using context
            resolved: List[tuple[str, Dict[str, Any], Optional[str]]] = []
            for td in stage_tools:
                args = dict(td.get("args", {}))
                for key, val in list(args.items()):
                    if isinstance(val, str) and val.startswith("$"):
                        var_name = val[1:]
                        args[key] = context.get(var_name, f"(undefined: ${var_name})")
                resolved.append((td["tool"], args, td.get("save")))

            # Execute stage in parallel via the ToolRegistry
            from asyncio import gather, create_task

            async def _run_one(tool_name: str, args: dict) -> tuple:
                start = time.time()
                try:
                    result = await registry.execute(tool_name, args)
                    elapsed = time.time() - start
                    return (tool_name, elapsed, result, None)
                except Exception as exc:
                    elapsed = time.time() - start
                    return (tool_name, elapsed, None, str(exc))

            tasks = [create_task(_run_one(name, a)) for name, a, _ in resolved]
            results = await gather(*tasks, return_exceptions=False)

            # Report and save context
            for (_, _, save_var), (ret_name, elapsed, result, error) in zip(resolved, results):
                if error:
                    report_lines.append(f"  [FAIL {elapsed:.1f}s] {ret_name}: {error}")
                else:
                    report_lines.append(_format_result(ret_name, elapsed, result))
                    if save_var:
                        context[save_var] = str(result) if result else ""

        total_elapsed = time.time() - total_start

        report_lines.append(f"\n{'=' * 60}")
        report_lines.append(f"Workflow complete in {total_elapsed:.1f}s")
        if context:
            report_lines.append(f"Saved variables: {', '.join(context.keys())}")

        return "\n".join(report_lines)

    return [
        Tool(
            name="run_workflow",
            description=(
                "Execute a staged DAG of registered tool calls. "
                "Provide a JSON workflow describing stages of tool calls. "
                "Tools within a stage run in parallel; stages run sequentially. "
                "Use 'save' to capture a tool's output and reference it in later "
                "stages with $varname in argument values.\n\n"
                "Example:\n"
                '  {"stages": ['
                '    [{"tool": "ctf_read_file", "args": {"path": "data.bin"}, "save": "raw"}],'
                '    [{"tool": "shell", "args": {"command": "xxd $raw"}}]'
                "  ]}"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "workflow": {
                        "type": "string",
                        "description": (
                            "JSON workflow definition. "
                            "Format: {\"stages\": [[tool_def, ...], ...]}. "
                            "A tool_def is {\"tool\": \"name\", \"args\": {...}, \"save\"?: \"var\"}. "
                            "Use $varname in args to reference a previous stage's saved output."
                        ),
                    },
                },
                "required": ["workflow"],
            },
            handler=_run_workflow,
        ),
    ]
