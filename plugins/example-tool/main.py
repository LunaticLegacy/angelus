"""example-tool — 网络搜索工具示例插件（决策 D4）。

演示插件系统的两条主线（docs/plugin-guide.md 对应章节）：

* register_tool —— 注册 ``web_search`` 工具；运行时的完整工具名为
  ``plugin.example-tool.web_search``（manager 自动加 ``plugin.<name>.`` 前缀，
  与内建工具隔离，见 docs/plugin-api.md §4.2）。
* register_hook —— 订阅白名单事件 ``tool.before`` / ``tool.after``（内部映射为
  ``agent:tools_requested`` / ``agent:tools_completed``），把每次工具调用前后
  的事件追加写入插件私有 ``state_dir``（``<plugin_dir>/data/events.jsonl``），
  供宿主观察钩子是否被触发（docs/plugin-api.md §5）。

实现刻意离线安全：默认从内置演示索引返回结果，不发起真实网络请求；仅当调用方
显式传入 ``base_url`` 时才走 urllib HTTP 请求（此时需要宿主授予 ``network`` /
``http`` 权限，见 manifest.permissions 与 docs/security.md 权限门）。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from angelus.plugins import AngelusPlugin, PluginRuntime

#: 内置演示索引：安装后无需网络即可完成「安装→启用→工具调用→钩子触发」全链路验证。
_DEMO_INDEX: list[dict[str, str]] = [
    {
        "title": "Angelus Plugin API",
        "url": "https://angelus.local/docs/plugin-api",
        "snippet": "manifest v1 契约、权限枚举、AngelusPlugin/PluginRuntime API 与五类扩展接线",
    },
    {
        "title": "Angelus Plugin Guide",
        "url": "https://angelus.local/docs/plugin-guide",
        "snippet": "插件作者教程：目录放置、manifest 写法、四类扩展示例与权限确认流程",
    },
    {
        "title": "Angelus Security Model",
        "url": "https://angelus.local/docs/security",
        "snippet": "权限门（permission gate）与完整性校验（checksum）风险模型",
    },
]


class ExampleToolPlugin(AngelusPlugin):
    """网络搜索工具示例：``web_search`` 工具 + ``tool.before``/``tool.after`` 钩子。"""

    name = "example-tool"
    version = "0.1.0"

    def __init__(self) -> None:
        self._runtime: PluginRuntime | None = None

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def setup(self, runtime: PluginRuntime) -> None:
        """注册工具与钩子（所有 register_* 只能发生在 setup 内）。"""
        self._runtime = runtime
        runtime.logger.info(
            "example-tool setup: registering web_search tool and tool.before/tool.after hooks"
        )
        runtime.register_tool(
            name="web_search",
            schema={
                "description": "搜索演示索引（或指定 base_url 的远程索引）并返回前 N 条结果",
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果条数（默认 5）",
                        "default": 5,
                    },
                    "base_url": {
                        "type": "string",
                        "description": "可选：远程搜索索引 URL；缺省使用内置演示索引",
                        "default": "",
                    },
                },
                "required": ["query"],
            },
            handler=self._web_search,
        )
        runtime.register_hook("tool.before", self._on_tool_before, priority=10)
        runtime.register_hook("tool.after", self._on_tool_after, priority=10)

    def teardown(self) -> None:
        """幂等清理：注册回收由 manager 负责，这里只复位内部引用。"""
        self._runtime = None

    # ------------------------------------------------------------------
    # tool handler
    # ------------------------------------------------------------------
    def _web_search(
        self,
        query: str,
        limit: int = 5,
        base_url: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        """执行搜索：有 base_url 走 HTTP，否则查内置演示索引。"""
        query = (query or "").strip()
        count = max(0, int(limit or 0))
        if base_url:
            results = self._remote_search(base_url, query)
        else:
            results = self._local_search(query)
        self._record_event("tool.call", payload={"tool": "web_search", "query": query})
        return {
            "tool": "plugin.example-tool.web_search",
            "query": query,
            "count": len(results[:count]) if count else len(results),
            "results": results[:count] if count else results,
        }

    def _local_search(self, query: str) -> list[dict[str, str]]:
        """内置演示索引的简单子串匹配（无网络）。"""
        if not query:
            return [dict(item) for item in _DEMO_INDEX]
        lowered = query.lower()
        return [
            dict(item)
            for item in _DEMO_INDEX
            if lowered in item["title"].lower()
            or lowered in item["snippet"].lower()
        ]

    def _remote_search(self, base_url: str, query: str) -> list[dict[str, Any]]:
        """远程索引：GET ``base_url?q=<query>``，响应体为 ``{"results": [...]}``。

        真实部署时宿主应在调用前通过 security.check_permission 核对该插件的
        ``network``/``http`` 授权；本示例只做最小演示。
        """
        separator = "&" if "?" in base_url else "?"
        url = f"{base_url}{separator}q={urllib.parse.quote(query)}"
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)]

    # ------------------------------------------------------------------
    # hook handlers
    # ------------------------------------------------------------------
    def _on_tool_before(self, event: Any) -> None:
        """tool.before 钩子：把事件快照写入 state_dir/events.jsonl。"""
        self._record_event("tool.before", event)

    def _on_tool_after(self, event: Any) -> None:
        """tool.after 钩子：把事件快照写入 state_dir/events.jsonl。"""
        self._record_event("tool.after", event)

    def _record_event(self, kind: str, event: Any = None, payload: dict[str, Any] | None = None) -> None:
        """追加一行 JSON 事件到 ``<state_dir>/events.jsonl``。

        钩子失败必须隔离（单个钩子抛异常不能影响 agent 主流程），因此这里
        把所有 I/O 异常吞掉并记日志——与 bridge_hooks 的失败隔离语义一致。
        """
        runtime = self._runtime
        if runtime is None:
            return
        entry: dict[str, Any] = {"event": kind}
        if event is not None:
            entry.update(
                {
                    "source": getattr(event, "source", ""),
                    "agent_name": getattr(event, "agent_name", ""),
                    "event_type": getattr(event, "event_type", ""),
                    "message": getattr(event, "message", ""),
                }
            )
        if payload:
            entry["payload"] = payload
        try:
            path = Path(runtime.state_dir) / "events.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            runtime.logger.exception("failed to record plugin event %s", kind)


#: 加载协议：entry_type=module 时导入本模块后取 ``angelus_plugin`` 实例。
angelus_plugin = ExampleToolPlugin()
