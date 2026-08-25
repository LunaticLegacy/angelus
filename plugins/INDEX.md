# plugins/ — Plugin Examples INDEX

开发期插件示例，也是桌面发布包的默认 starter plugins。首次启动时会被复制到与 `workspace/` 并列的持久 `plugins/` 目录；仅供发现，不会自动加载或覆盖用户文件。生产插件由 `angelus/plugins/` 的运行时发现、校验与加载；具体格式见 [`../docs/plugin-guide.md`](../docs/plugin-guide.md)。

| Entry | Type | Purpose |
|---|---|---|
| `demo-hello/` | End-to-end example | 演示面板、命令、工具、钩子、路由以及可选 CSS 前端资产。 |
| `example-tool/` | Tool example | 演示网络搜索工具和 `tool.before` / `tool.after` 钩子。 |
| `angelus/` | Skin plugin example | 演示工作台皮肤插件的清单、后端入口与前端样式/脚本。 |
| `angelus-control-plane-ui/` | Control-plane UI example | 演示更完整的控制平面 UI 插件，并附设计、变更和使用文档。 |
| `*.zip` | Distribution snapshots | 插件示例的手工分发快照；可编辑权威内容仍是同名目录。 |

每个示例目录的 `manifest.json` 是声明式入口；`main.py` 是 Python 实现，`plugin.js` / `plugin.css`（如存在）是被清单白名单允许的前端资源。

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [angelus-control-plane-ui/main.py](angelus-control-plane-ui/main.py#L17) | `ControlPlaneUIPlugin.setup` | `runtime: PluginRuntime` | `None` | Implement `ControlPlaneUIPlugin.setup`. |
| [angelus-control-plane-ui/main.py](angelus-control-plane-ui/main.py#L21) | `ControlPlaneUIPlugin.teardown` | `None` | `None` | Implement `ControlPlaneUIPlugin.teardown`. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L15) | `$` | `selector: unknown, root: unknown` | `unknown` | Perform the browser runtime operation: $. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L16) | `$$` | `selector: unknown, root: unknown` | `unknown` | Perform the browser runtime operation: $$. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L56) | `currentSessionId` | `None` | `unknown` | Perform the browser runtime operation: current session id. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L60) | `esc` | `value: unknown` | `unknown` | Perform the browser runtime operation: esc. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L69) | `pluginElement` | `tag: unknown, className: unknown` | `unknown` | Perform the browser runtime operation: plugin element. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L76) | `clamp` | `value: unknown, min: unknown, max: unknown` | `unknown` | Perform the browser runtime operation: clamp. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L80) | `finite` | `value: unknown, fallback: unknown` | `unknown` | Perform the browser runtime operation: finite. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L85) | `formatDuration` | `ms: unknown` | `unknown` | Perform the browser runtime operation: format duration. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L95) | `formatClock` | `epochSeconds: unknown, withDate: unknown` | `unknown` | Perform the browser runtime operation: format clock. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L105) | `formatNumber` | `value: unknown, digits: unknown` | `unknown` | Perform the browser runtime operation: format number. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L110) | `eventKey` | `event: unknown, index: unknown` | `unknown` | Perform the browser runtime operation: event key. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L124) | `apiJson` | `path: unknown` | `Promise<unknown>` | Perform the browser runtime operation: api json. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L137) | `loadEventsSince` | `sessionId: unknown, cutoffSeconds: unknown, maxPages: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load events since. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L173) | `loadLatestRunEvents` | `sessionId: unknown, maxPages: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load latest run events. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L201) | `lastRunWindow` | `events: unknown` | `unknown` | Perform the browser runtime operation: last run window. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L272) | `setView` | `view: unknown` | `unknown` | Perform the browser runtime operation: set view. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L299) | `timelineSpans` | `events: unknown` | `unknown` | Perform the browser runtime operation: timeline spans. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L382) | `timelineBounds` | `spans: unknown, inputs: unknown` | `unknown` | Perform the browser runtime operation: timeline bounds. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L395) | `spanCard` | `span: unknown, bounds: unknown, pxPerSecond: unknown` | `unknown` | Perform the browser runtime operation: span card. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L409) | `timeTicks` | `bounds: unknown, pxPerSecond: unknown` | `unknown` | Perform the browser runtime operation: time ticks. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L424) | `renderTimeline` | `None` | `unknown` | Perform the browser runtime operation: render timeline. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L445) | `column` | `lane: unknown, spans: unknown` | `unknown` | Perform the browser runtime operation: column. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L472) | `detailRows` | `detail: unknown` | `unknown` | Perform the browser runtime operation: detail rows. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L480) | `jsonBlock` | `title: unknown, value: unknown` | `unknown` | Perform the browser runtime operation: json block. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L488) | `overlayContent` | `span: unknown` | `unknown` | Perform the browser runtime operation: overlay content. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L503) | `chooseOverlayRect` | `sourceRect: unknown` | `unknown` | Perform the browser runtime operation: choose overlay rect. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L515) | `closeTimelineOverlay` | `animated: unknown` | `unknown` | Perform the browser runtime operation: close timeline overlay. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L536) | `openTimelineOverlay` | `source: unknown, span: unknown` | `unknown` | Perform the browser runtime operation: open timeline overlay. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L556) | `refreshTimeline` | `force: unknown` | `Promise<unknown>` | Perform the browser runtime operation: refresh timeline. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L587) | `rangeCutoff` | `key: unknown` | `unknown` | Perform the browser runtime operation: range cutoff. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L597) | `quantile` | `values: unknown, p: unknown` | `unknown` | Perform the browser runtime operation: quantile. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L607) | `average` | `values: unknown` | `unknown` | Perform the browser runtime operation: average. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L611) | `stddev` | `values: unknown` | `unknown` | Perform the browser runtime operation: stddev. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L617) | `telemetry` | `events: unknown` | `unknown` | Perform the browser runtime operation: telemetry. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L669) | `bucketSeries` | `items: unknown, start: unknown, end: unknown, bucketSeconds: unknown, valueFn: unknown, reducer: unknown` | `unknown` | Perform the browser runtime operation: bucket series. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L686) | `chartSvg` | `series: unknown, options: unknown` | `unknown` | Perform the browser runtime operation: chart svg. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L696) | `x` | `index: unknown` | `unknown` | Perform the browser runtime operation: x. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L697) | `y` | `value: unknown` | `unknown` | Perform the browser runtime operation: y. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L720) | `tokenTotals` | `modelCalls: unknown, internal: unknown` | `unknown` | Perform the browser runtime operation: token totals. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L728) | `activitySeries` | `modelCalls: unknown, tools: unknown, start: unknown, end: unknown, bucket: unknown` | `unknown` | Perform the browser runtime operation: activity series. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L736) | `internalBreakdown` | `records: unknown` | `unknown` | Perform the browser runtime operation: internal breakdown. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L746) | `renderStatistics` | `None` | `unknown` | Perform the browser runtime operation: render statistics. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L816) | `refreshStatistics` | `force: unknown` | `Promise<unknown>` | Perform the browser runtime operation: refresh statistics. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L863) | `agentSuggestions` | `prefix: unknown` | `Promise<unknown>` | Perform the browser runtime operation: agent suggestions. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L872) | `sessionSuggestions` | `prefix: unknown` | `unknown` | Perform the browser runtime operation: session suggestions. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L879) | `commandCatalog` | `None` | `unknown` | Perform the browser runtime operation: command catalog. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L887) | `slashItems` | `value: unknown` | `Promise<unknown>` | Perform the browser runtime operation: slash items. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L916) | `renderSlashConsole` | `None` | `unknown` | Perform the browser runtime operation: render slash console. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L947) | `updateSlashConsole` | `None` | `Promise<unknown>` | Perform the browser runtime operation: update slash console. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L959) | `closeSlashConsole` | `None` | `unknown` | Perform the browser runtime operation: close slash console. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L966) | `replaceInput` | `value: unknown` | `unknown` | Perform the browser runtime operation: replace input. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L973) | `clearAndResizeInput` | `None` | `unknown` | Perform the browser runtime operation: clear and resize input. |
| [angelus-control-plane-ui/plugin.js](angelus-control-plane-ui/plugin.js#L978) | `acceptSlashSelection` | `execute: unknown` | `unknown` | Perform the browser runtime operation: accept slash selection. |
| [angelus/main.py](angelus/main.py#L14) | `AngelusSkinPlugin.setup` | `runtime: Any` | `Any` | Implement `AngelusSkinPlugin.setup`. |
| [angelus/main.py](angelus/main.py#L17) | `AngelusSkinPlugin.teardown` | `None` | `Any` | Implement `AngelusSkinPlugin.teardown`. |
| [angelus/plugin.js](angelus/plugin.js#L9) | `node` | `className: unknown, parent: unknown` | `unknown` | Perform the browser runtime operation: node. |
| [angelus/plugin.js](angelus/plugin.js#L18) | `mountOrnaments` | `None` | `unknown` | Perform the browser runtime operation: mount ornaments. |
| [demo-hello/main.py](demo-hello/main.py#L28) | `DemoHelloPlugin.setup` | `runtime: PluginRuntime` | `None` | Implement `DemoHelloPlugin.setup`. |
| [demo-hello/main.py](demo-hello/main.py#L51) | `DemoHelloPlugin.teardown` | `None` | `None` | Implement `DemoHelloPlugin.teardown`. |
| [demo-hello/main.py](demo-hello/main.py#L57) | `DemoHelloPlugin._tool_hello` | `name: str, **_: Any` | `dict[str, Any]` | Agent-visible tool: greets ``name`` (default "world"). |
| [demo-hello/main.py](demo-hello/main.py#L65) | `DemoHelloPlugin._on_tool_after` | `event: Any` | `None` | Append the event to ``<state_dir>/events.jsonl`` (never raises). |
| [demo-hello/main.py](demo-hello/main.py#L81) | `DemoHelloPlugin._api_hello` | `None` | `dict[str, Any]` | REST: GET /plugins/demo-hello/api/hello. |
| [example-tool/main.py](example-tool/main.py#L60) | `ExampleToolPlugin.setup` | `runtime: PluginRuntime` | `None` | 注册工具与钩子（所有 register_* 只能发生在 setup 内）。 |
| [example-tool/main.py](example-tool/main.py#L94) | `ExampleToolPlugin.teardown` | `None` | `None` | 幂等清理：注册回收由 manager 负责，这里只复位内部引用。 |
| [example-tool/main.py](example-tool/main.py#L101) | `ExampleToolPlugin._web_search` | `query: str, limit: int, base_url: str, **_kwargs: Any` | `dict[str, Any]` | 执行搜索：有 base_url 走 HTTP，否则查内置演示索引。 |
| [example-tool/main.py](example-tool/main.py#L123) | `ExampleToolPlugin._local_search` | `query: str` | `list[dict[str, str]]` | 内置演示索引的简单子串匹配（无网络）。 |
| [example-tool/main.py](example-tool/main.py#L135) | `ExampleToolPlugin._remote_search` | `base_url: str, query: str` | `list[dict[str, Any]]` | 远程索引：GET ``base_url?q=<query>``，响应体为 ``{"results": [...]}``。 |
| [example-tool/main.py](example-tool/main.py#L153) | `ExampleToolPlugin._on_tool_before` | `event: Any` | `None` | tool.before 钩子：把事件快照写入 state_dir/events.jsonl。 |
| [example-tool/main.py](example-tool/main.py#L157) | `ExampleToolPlugin._on_tool_after` | `event: Any` | `None` | tool.after 钩子：把事件快照写入 state_dir/events.jsonl。 |
| [example-tool/main.py](example-tool/main.py#L161) | `ExampleToolPlugin._record_event` | `kind: str, event: Any, payload: dict[str, Any] \| None` | `None` | 追加一行 JSON 事件到 ``<state_dir>/events.jsonl``。 |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [angelus-control-plane-ui/main.py](angelus-control-plane-ui/main.py#L13) | `ControlPlaneUIPlugin` | `None` | `AngelusPlugin` | Provide `ControlPlaneUIPlugin` behavior. |
| [angelus/main.py](angelus/main.py#L10) | `AngelusSkinPlugin` | `None` | `AngelusPlugin` | Provide `AngelusSkinPlugin` behavior. |
| [demo-hello/main.py](demo-hello/main.py#L24) | `DemoHelloPlugin` | `None` | `AngelusPlugin` | Provide `DemoHelloPlugin` behavior. |
| [example-tool/main.py](example-tool/main.py#L48) | `ExampleToolPlugin` | `None` | `AngelusPlugin` | 网络搜索工具示例：``web_search`` 工具 + ``tool.before``/``tool.after`` 钩子。 |

<!-- END GENERATED SYMBOL MAP -->
