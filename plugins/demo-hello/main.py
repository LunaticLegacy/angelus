"""demo-hello plugin — frontend-visible full-chain demo.

Covers every extension point the v1 plugin API exposes:

* ``register_tool``    — ``demo_hello`` tool joined into the agent toolchain
                         (live name ``plugin.demo-hello.demo_hello``)
* ``register_hook``    — subscribe to ``tool.after``; records events into the
                         plugin-private ``state_dir`` (failure-isolated)
* ``register_route``   — ``GET /hello`` mounted at ``/plugins/demo-hello/api``
* frontend (plugin.js) — ``window.Angelus`` panel + command rendered in the
                         workbench inspector area
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from angelus.plugins import AngelusPlugin, PluginRuntime


class DemoHelloPlugin(AngelusPlugin):
    name = "demo-hello"
    version = "0.1.0"

    def setup(self, runtime: PluginRuntime) -> None:
        runtime.logger.info("demo-hello setup: registering tool/hook/route")
        self._state_dir: Path = Path(runtime.state_dir)

        runtime.register_tool(
            "demo_hello",
            {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "打招呼的对象名字",
                    }
                },
                "required": [],
            },
            self._tool_hello,
        )

        runtime.register_hook("tool.after", self._on_tool_after, priority=0)
        runtime.register_route("GET", "/hello", self._api_hello)

    def teardown(self) -> None:
        self._state_dir = None  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # extension handlers
    # ------------------------------------------------------------------
    def _tool_hello(self, name: str = "world", **_: Any) -> dict[str, Any]:
        """Agent-visible tool: greets ``name`` (default "world")."""
        return {
            "message": f"Hello, {name}!",
            "from": "plugin.demo-hello",
            "server_time": round(time.time(), 3),
        }

    def _on_tool_after(self, event: Any) -> None:
        """Append the event to ``<state_dir>/events.jsonl`` (never raises)."""
        try:
            log = self._state_dir / "events.jsonl"
            log.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "event": getattr(event, "event_type", ""),
                "agent": getattr(event, "agent_name", ""),
                "ts": getattr(event, "timestamp", time.time()),
            }
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            # Hooks must never break the agent main flow (S5 isolation).
            pass

    def _api_hello(self) -> dict[str, Any]:
        """REST: GET /plugins/demo-hello/api/hello."""
        return {
            "plugin": "demo-hello",
            "version": self.version,
            "message": "Hello from the demo plugin API ✦",
            "server_time": round(time.time(), 3),
        }


# The v1 loader looks for the ``angelus_plugin`` module-level instance.
angelus_plugin = DemoHelloPlugin()
