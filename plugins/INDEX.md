# plugins/ — Plugin Examples INDEX

开发期插件示例。Angelus 在启动时将本目录作为本地开发发现源，并同时扫描持久化的 `.angelus-state/plugins/packages/`。发现只读取 `manifest.json`；插件不会被复制、导入或执行，直到用户在设置页明确“加入工作台”并启用。具体格式见 [`../docs/plugin-guide.md`](../docs/plugin-guide.md)。

| Entry | Type | Purpose |
|---|---|---|
| `demo-hello/` | Tool + UI example | 演示受控、命名空间化工具和可选 CSS 前端资产。 |
| `example-tool/` | Tool example | 演示离线文档搜索 Tool provider。 |
| `pofp-ctf/` | Tool example | 迁移后的 POFP CTF Markdown 知识库搜索与文档读取 Tool provider，带可持久化知识库目录设置。 |
| [`gzctf/`](gzctf/INDEX.md) | Tool example | 迁移后的 GZCTF v1 Provider：11 个命名空间 Agent 工具、插件私有 Cookie/下载/批量状态，以及宿主渲染的一次性密码登录面板。 |
| `angelus/` | UI skin example | 演示工作台皮肤插件的清单与前端样式/脚本。 |
| `angelus-control-plane-ui/` | Control-plane UI example | 演示更完整的控制平面 UI 插件，并附设计、变更和使用文档。 |
| `token-burner/` | Visual example | 把 token 消耗速率可视化为火焰的独立浮动窗口插件（纯前端，读 /api/sessions/{id}/usage）。 |
| `*.zip` | Distribution snapshots | 插件示例的手工分发快照；可编辑权威内容仍是同名目录。 |

每个示例目录的 `manifest.json` 是声明式入口；仅 `kind: "tool"` 插件可以有 Python `main.py`。`plugin.js` / `plugin.css`（如存在）必须被清单白名单允许的前端资源。

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [angelus-control-plane-ui-v0.2.2/main.py](angelus-control-plane-ui-v0.2.2/main.py#L17) | `ControlPlaneUIPlugin.setup` | `runtime: PluginRuntime` | `None` | Implement `ControlPlaneUIPlugin.setup`. |
| [angelus-control-plane-ui-v0.2.2/main.py](angelus-control-plane-ui-v0.2.2/main.py#L21) | `ControlPlaneUIPlugin.teardown` | `None` | `None` | Implement `ControlPlaneUIPlugin.teardown`. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L15) | `$` | `selector: unknown, root: unknown` | `unknown` | Perform the browser runtime operation: $. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L16) | `$$` | `selector: unknown, root: unknown` | `unknown` | Perform the browser runtime operation: $$. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L57) | `currentSessionId` | `None` | `unknown` | Perform the browser runtime operation: current session id. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L61) | `esc` | `value: unknown` | `unknown` | Perform the browser runtime operation: esc. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L70) | `pluginElement` | `tag: unknown, className: unknown` | `unknown` | Perform the browser runtime operation: plugin element. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L77) | `clamp` | `value: unknown, min: unknown, max: unknown` | `unknown` | Perform the browser runtime operation: clamp. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L81) | `finite` | `value: unknown, fallback: unknown` | `unknown` | Perform the browser runtime operation: finite. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L86) | `formatDuration` | `ms: unknown` | `unknown` | Perform the browser runtime operation: format duration. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L96) | `formatClock` | `epochSeconds: unknown, withDate: unknown` | `unknown` | Perform the browser runtime operation: format clock. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L106) | `formatNumber` | `value: unknown, digits: unknown` | `unknown` | Perform the browser runtime operation: format number. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L111) | `eventKey` | `event: unknown, index: unknown` | `unknown` | Perform the browser runtime operation: event key. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L125) | `apiJson` | `path: unknown` | `Promise<unknown>` | Perform the browser runtime operation: api json. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L138) | `loadEventsSince` | `sessionId: unknown, cutoffSeconds: unknown, maxPages: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load events since. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L174) | `loadLatestRunEvents` | `sessionId: unknown, maxPages: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load latest run events. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L202) | `lastRunWindow` | `events: unknown` | `unknown` | Perform the browser runtime operation: last run window. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L273) | `setView` | `view: unknown` | `unknown` | Perform the browser runtime operation: set view. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L300) | `timelineSpans` | `events: unknown` | `unknown` | Perform the browser runtime operation: timeline spans. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L383) | `timelineBounds` | `spans: unknown, inputs: unknown` | `unknown` | Perform the browser runtime operation: timeline bounds. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L396) | `spanCard` | `span: unknown, bounds: unknown, pxPerSecond: unknown` | `unknown` | Perform the browser runtime operation: span card. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L410) | `timeTicks` | `bounds: unknown, pxPerSecond: unknown` | `unknown` | Perform the browser runtime operation: time ticks. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L425) | `renderTimeline` | `None` | `unknown` | Perform the browser runtime operation: render timeline. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L446) | `column` | `lane: unknown, spans: unknown` | `unknown` | Perform the browser runtime operation: column. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L473) | `detailRows` | `detail: unknown` | `unknown` | Perform the browser runtime operation: detail rows. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L481) | `jsonBlock` | `title: unknown, value: unknown` | `unknown` | Perform the browser runtime operation: json block. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L489) | `overlayContent` | `span: unknown` | `unknown` | Perform the browser runtime operation: overlay content. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L504) | `chooseOverlayRect` | `sourceRect: unknown` | `unknown` | Perform the browser runtime operation: choose overlay rect. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L516) | `closeTimelineOverlay` | `animated: unknown` | `unknown` | Perform the browser runtime operation: close timeline overlay. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L537) | `openTimelineOverlay` | `source: unknown, span: unknown` | `unknown` | Perform the browser runtime operation: open timeline overlay. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L557) | `refreshTimeline` | `force: unknown` | `Promise<unknown>` | Perform the browser runtime operation: refresh timeline. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L588) | `rangeCutoff` | `key: unknown` | `unknown` | Perform the browser runtime operation: range cutoff. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L598) | `quantile` | `values: unknown, p: unknown` | `unknown` | Perform the browser runtime operation: quantile. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L608) | `average` | `values: unknown` | `unknown` | Perform the browser runtime operation: average. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L612) | `stddev` | `values: unknown` | `unknown` | Perform the browser runtime operation: stddev. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L618) | `eventAgent` | `event: unknown` | `unknown` | Perform the browser runtime operation: event agent. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L623) | `telemetry` | `events: unknown` | `unknown` | Perform the browser runtime operation: telemetry. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L681) | `bucketSeries` | `items: unknown, start: unknown, end: unknown, bucketSeconds: unknown, valueFn: unknown, reducer: unknown` | `unknown` | Perform the browser runtime operation: bucket series. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L698) | `chartSvg` | `series: unknown, options: unknown` | `unknown` | Perform the browser runtime operation: chart svg. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L708) | `x` | `index: unknown` | `unknown` | Perform the browser runtime operation: x. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L709) | `y` | `value: unknown` | `unknown` | Perform the browser runtime operation: y. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L732) | `tokenTotals` | `modelCalls: unknown, internal: unknown` | `unknown` | Perform the browser runtime operation: token totals. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L740) | `activitySeries` | `modelCalls: unknown, tools: unknown, start: unknown, end: unknown, bucket: unknown` | `unknown` | Perform the browser runtime operation: activity series. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L748) | `internalBreakdown` | `records: unknown` | `unknown` | Perform the browser runtime operation: internal breakdown. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L758) | `renderStatistics` | `None` | `unknown` | Perform the browser runtime operation: render statistics. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L851) | `refreshStatistics` | `force: unknown` | `Promise<unknown>` | Perform the browser runtime operation: refresh statistics. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L898) | `agentSuggestions` | `prefix: unknown` | `Promise<unknown>` | Perform the browser runtime operation: agent suggestions. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L907) | `sessionSuggestions` | `prefix: unknown` | `unknown` | Perform the browser runtime operation: session suggestions. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L914) | `commandCatalog` | `None` | `unknown` | Perform the browser runtime operation: command catalog. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L922) | `slashItems` | `value: unknown` | `Promise<unknown>` | Perform the browser runtime operation: slash items. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L951) | `renderSlashConsole` | `None` | `unknown` | Perform the browser runtime operation: render slash console. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L982) | `updateSlashConsole` | `None` | `Promise<unknown>` | Perform the browser runtime operation: update slash console. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L994) | `closeSlashConsole` | `None` | `unknown` | Perform the browser runtime operation: close slash console. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L1001) | `replaceInput` | `value: unknown` | `unknown` | Perform the browser runtime operation: replace input. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L1008) | `clearAndResizeInput` | `None` | `unknown` | Perform the browser runtime operation: clear and resize input. |
| [angelus-control-plane-ui-v0.2.2/plugin.js](angelus-control-plane-ui-v0.2.2/plugin.js#L1013) | `acceptSlashSelection` | `execute: unknown` | `unknown` | Perform the browser runtime operation: accept slash selection. |
| [angelus/main.py](angelus/main.py#L14) | `AngelusSkinPlugin.setup` | `runtime: Any` | `Any` | Implement `AngelusSkinPlugin.setup`. |
| [angelus/main.py](angelus/main.py#L17) | `AngelusSkinPlugin.teardown` | `None` | `Any` | Implement `AngelusSkinPlugin.teardown`. |
| [angelus/plugin.js](angelus/plugin.js#L9) | `node` | `className: unknown, parent: unknown` | `unknown` | Perform the browser runtime operation: node. |
| [angelus/plugin.js](angelus/plugin.js#L18) | `mountOrnaments` | `None` | `unknown` | Perform the browser runtime operation: mount ornaments. |
| [demo-hello/main.py](demo-hello/main.py#L23) | `GreetingProvider.materialize` | `session_id: str, policy: object, role: str` | `list[Tool]` | Return the namespaced greeting tool for coordinators and workers. |
| [demo-hello/main.py](demo-hello/main.py#L43) | `GreetingProvider._hello` | `name: str` | `str` | Format one safe, plain-text greeting. |
| [demo-hello/main.py](demo-hello/main.py#L58) | `DemoHelloPlugin.setup` | `runtime: PluginRuntime` | `None` | Declare the tool category and tool definition. |
| [demo-hello/main.py](demo-hello/main.py#L74) | `DemoHelloPlugin.teardown` | `None` | `None` | Release no resources because this plugin is stateless. |
| [example-tool/main.py](example-tool/main.py#L30) | `SearchProvider.materialize` | `session_id: str, policy: object, role: str` | `list[Tool]` | Return the offline search tool for supported Agent roles. |
| [example-tool/main.py](example-tool/main.py#L53) | `SearchProvider._search` | `query: str, limit: int` | `str` | Search the bounded local index and format matching documents. |
| [example-tool/main.py](example-tool/main.py#L75) | `ExampleToolPlugin.setup` | `runtime: PluginRuntime` | `None` | Declare the search category and definition through the host runtime. |
| [example-tool/main.py](example-tool/main.py#L90) | `ExampleToolPlugin.teardown` | `None` | `None` | Release no resources because the search index is immutable. |
| [geo-pack/geopack/analysis.py](geo-pack/geopack/analysis.py#L10) | `bbox` | `value: dict[str, Any]` | `list[float]` | Implement `bbox`. |
| [geo-pack/geopack/analysis.py](geo-pack/geopack/analysis.py#L18) | `centroid` | `value: dict[str, Any]` | `list[float]` | Implement `centroid`. |
| [geo-pack/geopack/analysis.py](geo-pack/geopack/analysis.py#L23) | `measure` | `value: dict[str, Any]` | `dict[str, float]` | Implement `measure`. |
| [geo-pack/geopack/analysis.py](geo-pack/geopack/analysis.py#L52) | `contains` | `value: dict[str, Any], point: tuple[float, float]` | `list[int]` | Implement `contains`. |
| [geo-pack/geopack/analysis.py](geo-pack/geopack/analysis.py#L70) | `feature_distance` | `value: dict[str, Any], point: tuple[float, float]` | `list[dict[str, Any]]` | Implement `feature_distance`. |
| [geo-pack/geopack/engine.py](geo-pack/geopack/engine.py#L17) | `GeoEngine.dispatch` | `tool: str, params: dict[str, Any] \| None` | `str` | Implement `GeoEngine.dispatch`. |
| [geo-pack/geopack/geojson.py](geo-pack/geopack/geojson.py#L7) | `normalize` | `value: Any` | `dict[str, Any]` | Implement `normalize`. |
| [geo-pack/geopack/geojson.py](geo-pack/geopack/geojson.py#L20) | `features` | `value: dict[str, Any]` | `list[dict[str, Any]]` | Implement `features`. |
| [geo-pack/geopack/geojson.py](geo-pack/geopack/geojson.py#L32) | `geometries` | `value: dict[str, Any]` | `Iterator[dict[str, Any]]` | Implement `geometries`. |
| [geo-pack/geopack/geojson.py](geo-pack/geopack/geojson.py#L45) | `coordinate_points` | `geometry: dict[str, Any]` | `Iterator[tuple[float, float]]` | Implement `coordinate_points`. |
| [geo-pack/geopack/geojson.py](geo-pack/geopack/geojson.py#L64) | `_list` | `value: Any` | `list[Any]` | Implement `_list`. |
| [geo-pack/geopack/geojson.py](geo-pack/geopack/geojson.py#L70) | `_point` | `value: Any` | `tuple[float, float]` | Implement `_point`. |
| [geo-pack/geopack/mathgeo.py](geo-pack/geopack/mathgeo.py#L11) | `haversine` | `a: tuple[float, float], b: tuple[float, float]` | `float` | Implement `haversine`. |
| [geo-pack/geopack/mathgeo.py](geo-pack/geopack/mathgeo.py#L18) | `line_length` | `points: list[tuple[float, float]]` | `float` | Implement `line_length`. |
| [geo-pack/geopack/mathgeo.py](geo-pack/geopack/mathgeo.py#L22) | `web_mercator` | `point: tuple[float, float]` | `tuple[float, float]` | Implement `web_mercator`. |
| [geo-pack/geopack/mathgeo.py](geo-pack/geopack/mathgeo.py#L30) | `inverse_web_mercator` | `point: tuple[float, float]` | `tuple[float, float]` | Implement `inverse_web_mercator`. |
| [geo-pack/geopack/mathgeo.py](geo-pack/geopack/mathgeo.py#L37) | `ring_area_m2` | `points: list[tuple[float, float]]` | `float` | Approximate geodesic polygon area using a spherical trapezoid sum. |
| [geo-pack/geopack/mathgeo.py](geo-pack/geopack/mathgeo.py#L49) | `point_in_ring` | `point: tuple[float, float], ring: list[tuple[float, float]]` | `bool` | Implement `point_in_ring`. |
| [geo-pack/geopack/mathgeo.py](geo-pack/geopack/mathgeo.py#L63) | `centroid_of_points` | `points: list[tuple[float, float]]` | `tuple[float, float]` | Implement `centroid_of_points`. |
| [geo-pack/geopack/mathgeo.py](geo-pack/geopack/mathgeo.py#L69) | `distance_to_segment_m` | `p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]` | `float` | Implement `distance_to_segment_m`. |
| [geo-pack/geopack/registry.py](geo-pack/geopack/registry.py#L22) | `GeoToolRegistry.add` | `name: str, description: str, parameters: dict[str, str], handler: Handler` | `None` | Implement `GeoToolRegistry.add`. |
| [geo-pack/geopack/registry.py](geo-pack/geopack/registry.py#L27) | `GeoToolRegistry.call` | `name: str, params: dict[str, Any]` | `Any` | Implement `GeoToolRegistry.call`. |
| [geo-pack/geopack/registry.py](geo-pack/geopack/registry.py#L33) | `GeoToolRegistry.describe` | `None` | `list[dict[str, Any]]` | Implement `GeoToolRegistry.describe`. |
| [geo-pack/geopack/store.py](geo-pack/geopack/store.py#L16) | `DatasetStore._safe_name` | `name: str` | `str` | Implement `DatasetStore._safe_name`. |
| [geo-pack/geopack/store.py](geo-pack/geopack/store.py#L22) | `DatasetStore.save` | `name: str, geojson: dict[str, Any]` | `dict[str, Any]` | Implement `DatasetStore.save`. |
| [geo-pack/geopack/store.py](geo-pack/geopack/store.py#L30) | `DatasetStore.load` | `name: str` | `dict[str, Any]` | Implement `DatasetStore.load`. |
| [geo-pack/geopack/store.py](geo-pack/geopack/store.py#L39) | `DatasetStore.delete` | `name: str` | `bool` | Implement `DatasetStore.delete`. |
| [geo-pack/geopack/store.py](geo-pack/geopack/store.py#L46) | `DatasetStore.list` | `None` | `list[dict[str, Any]]` | Implement `DatasetStore.list`. |
| [geo-pack/geopack/tools.py](geo-pack/geopack/tools.py#L13) | `build_registry` | `store: DatasetStore` | `GeoToolRegistry` | Implement `build_registry`. |
| [geo-pack/geopack/tools.py](geo-pack/geopack/tools.py#L79) | `_point` | `value: Any` | `tuple[float, float]` | Implement `_point`. |
| [geo-pack/geopack/tools.py](geo-pack/geopack/tools.py#L86) | `_xy` | `value: Any` | `tuple[float, float]` | Implement `_xy`. |
| [geo-pack/geopack/tools.py](geo-pack/geopack/tools.py#L92) | `_compare` | `actual: Any, expected: Any, op: str` | `bool` | Implement `_compare`. |
| [geo-pack/main.py](geo-pack/main.py#L50) | `GeoPackProvider.materialize` | `session_id: str, policy: object, role: str` | `list[Tool]` | Implement `GeoPackProvider.materialize`. |
| [geo-pack/main.py](geo-pack/main.py#L71) | `GeoPackPlugin.setup` | `runtime: PluginRuntime` | `None` | Implement `GeoPackPlugin.setup`. |
| [geo-pack/main.py](geo-pack/main.py#L99) | `GeoPackPlugin._bridge` | `request: PluginUiActionRequest` | `PluginUiActionResult` | Implement `GeoPackPlugin._bridge`. |
| [geo-pack/main.py](geo-pack/main.py#L113) | `GeoPackPlugin.teardown` | `None` | `None` | Implement `GeoPackPlugin.teardown`. |
| [geo-pack/plugin.js](geo-pack/plugin.js#L6) | `el` | `tag: unknown, cls: unknown, text: unknown` | `unknown` | Perform the browser runtime operation: el. |
| [geo-pack/plugin.js](geo-pack/plugin.js#L8) | `bridge` | `tool: unknown, params: unknown` | `Promise<unknown>` | Perform the browser runtime operation: bridge. |
| [geo-pack/plugin.js](geo-pack/plugin.js#L16) | `features` | `g: unknown` | `unknown` | Perform the browser runtime operation: features. |
| [geo-pack/plugin.js](geo-pack/plugin.js#L17) | `walkCoords` | `g: unknown, cb: unknown` | `unknown` | Perform the browser runtime operation: walk coords. |
| [geo-pack/plugin.js](geo-pack/plugin.js#L18) | `calcBBox` | `g: unknown` | `unknown` | Perform the browser runtime operation: calc b box. |
| [geo-pack/plugin.js](geo-pack/plugin.js#L19) | `fit` | `g: unknown` | `unknown` | Perform the browser runtime operation: fit. |
| [geo-pack/plugin.js](geo-pack/plugin.js#L20) | `project` | `p: unknown, canvas: unknown` | `unknown` | Perform the browser runtime operation: project. |
| [geo-pack/plugin.js](geo-pack/plugin.js#L21) | `drawGeom` | `ctx: unknown, g: unknown, c: unknown` | `unknown` | Perform the browser runtime operation: draw geom. |
| [geo-pack/plugin.js](geo-pack/plugin.js#L22) | `draw` | `None` | `unknown` | Perform the browser runtime operation: draw. |
| [geo-pack/plugin.js](geo-pack/plugin.js#L36) | `refresh` | `None` | `Promise<unknown>` | Perform the browser runtime operation: refresh. |
| [token-burner/plugin.js](token-burner/plugin.js#L38) | `clamp` | `value: unknown, min: unknown, max: unknown` | `unknown` | Perform the browser runtime operation: clamp. |
| [token-burner/plugin.js](token-burner/plugin.js#L42) | `finite` | `value: unknown, fallback: unknown` | `unknown` | Perform the browser runtime operation: finite. |
| [token-burner/plugin.js](token-burner/plugin.js#L47) | `readUiState` | `None` | `unknown` | Perform the browser runtime operation: read ui state. |
| [token-burner/plugin.js](token-burner/plugin.js#L56) | `writeUiState` | `patch: unknown` | `unknown` | Perform the browser runtime operation: write ui state. |
| [token-burner/plugin.js](token-burner/plugin.js#L64) | `currentSessionId` | `None` | `unknown` | Perform the browser runtime operation: current session id. |
| [token-burner/plugin.js](token-burner/plugin.js#L75) | `usageTotal` | `payload: unknown` | `unknown` | Perform the browser runtime operation: usage total. |
| [token-burner/plugin.js](token-burner/plugin.js#L90) | `getJson` | `url: unknown` | `Promise<unknown>` | Perform the browser runtime operation: get json. |
| [token-burner/plugin.js](token-burner/plugin.js#L101) | `normalizeSettings` | `values: unknown` | `unknown` | Perform the browser runtime operation: normalize settings. |
| [token-burner/plugin.js](token-burner/plugin.js#L113) | `refreshSettings` | `force: unknown` | `Promise<unknown>` | Perform the browser runtime operation: refresh settings. |
| [token-burner/plugin.js](token-burner/plugin.js#L125) | `resetSessionState` | `nextSession: unknown` | `unknown` | Perform the browser runtime operation: reset session state. |
| [token-burner/plugin.js](token-burner/plugin.js#L139) | `recordUsage` | `total: unknown, now: unknown` | `unknown` | Perform the browser runtime operation: record usage. |
| [token-burner/plugin.js](token-burner/plugin.js#L171) | `poll` | `None` | `Promise<unknown>` | Perform the browser runtime operation: poll. |
| [token-burner/plugin.js](token-burner/plugin.js#L214) | `schedulePoll` | `None` | `unknown` | Perform the browser runtime operation: schedule poll. |
| [token-burner/plugin.js](token-burner/plugin.js#L220) | `formatNumber` | `value: unknown` | `unknown` | Perform the browser runtime operation: format number. |
| [token-burner/plugin.js](token-burner/plugin.js#L228) | `formatRate` | `value: unknown` | `unknown` | Perform the browser runtime operation: format rate. |
| [token-burner/plugin.js](token-burner/plugin.js#L234) | `visualTick` | `None` | `unknown` | Perform the browser runtime operation: visual tick. |
| [token-burner/plugin.js](token-burner/plugin.js#L246) | `renderTelemetry` | `None` | `unknown` | Perform the browser runtime operation: render telemetry. |
| [token-burner/plugin.js](token-burner/plugin.js#L285) | `flameMarkup` | `None` | `unknown` | Perform the browser runtime operation: flame markup. |
| [token-burner/plugin.js](token-burner/plugin.js#L304) | `panelMarkup` | `None` | `unknown` | Perform the browser runtime operation: panel markup. |
| [token-burner/plugin.js](token-burner/plugin.js#L330) | `mount` | `None` | `unknown` | Perform the browser runtime operation: mount. |
| [token-burner/plugin.js](token-burner/plugin.js#L362) | `onActionClick` | `event: unknown` | `unknown` | Perform the browser runtime operation: on action click. |
| [token-burner/plugin.js](token-burner/plugin.js#L372) | `setCollapsed` | `value: unknown` | `unknown` | Perform the browser runtime operation: set collapsed. |
| [token-burner/plugin.js](token-burner/plugin.js#L378) | `toggleLarge` | `None` | `unknown` | Perform the browser runtime operation: toggle large. |
| [token-burner/plugin.js](token-burner/plugin.js#L385) | `resetPosition` | `None` | `unknown` | Perform the browser runtime operation: reset position. |
| [token-burner/plugin.js](token-burner/plugin.js#L394) | `bindDrag` | `None` | `unknown` | Perform the browser runtime operation: bind drag. |
| [token-burner/plugin.js](token-burner/plugin.js#L420) | `finish` | `None` | `unknown` | Perform the browser runtime operation: finish. |
| [token-burner/plugin.js](token-burner/plugin.js#L431) | `openPopout` | `None` | `unknown` | Perform the browser runtime operation: open popout. |
| [token-burner/plugin.js](token-burner/plugin.js#L438) | `toggleVisible` | `None` | `unknown` | Perform the browser runtime operation: toggle visible. |
| [token-burner/plugin.js](token-burner/plugin.js#L445) | `registerBridge` | `None` | `unknown` | Perform the browser runtime operation: register bridge. |
| [token-burner/plugin.js](token-burner/plugin.js#L474) | `destroy` | `None` | `unknown` | Perform the browser runtime operation: destroy. |
| [token-burner/plugin.js](token-burner/plugin.js#L481) | `start` | `None` | `Promise<unknown>` | Perform the browser runtime operation: start. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [angelus-control-plane-ui-v0.2.2/main.py](angelus-control-plane-ui-v0.2.2/main.py#L13) | `ControlPlaneUIPlugin` | `None` | `AngelusPlugin` | Provide `ControlPlaneUIPlugin` behavior. |
| [angelus/main.py](angelus/main.py#L10) | `AngelusSkinPlugin` | `None` | `AngelusPlugin` | Provide `AngelusSkinPlugin` behavior. |
| [demo-hello/main.py](demo-hello/main.py#L9) | `GreetingProvider` | `greeting: str` | `object` | Materialize the greeting tool for eligible Agent roles. |
| [demo-hello/main.py](demo-hello/main.py#L55) | `DemoHelloPlugin` | `None` | `object` | Publish one namespaced greeting tool through the constrained runtime. |
| [example-tool/main.py](example-tool/main.py#L12) | `SearchDocument` | `title: str, url: str, snippet: str` | `object` | One document in the plugin's intentionally offline demo index. |
| [example-tool/main.py](example-tool/main.py#L27) | `SearchProvider` | `None` | `object` | Materialize the offline search Tool without external permissions. |
| [example-tool/main.py](example-tool/main.py#L72) | `ExampleToolPlugin` | `None` | `object` | Publish one offline documentation search tool. |
| [geo-pack/geopack/engine.py](geo-pack/geopack/engine.py#L12) | `GeoEngine` | `state_root: Path, session_id: str` | `object` | Provide `GeoEngine` behavior. |
| [geo-pack/geopack/registry.py](geo-pack/geopack/registry.py#L11) | `GeoTool` | `name: str, description: str, parameters: dict[str, str], handler: Handler` | `object` | Provide `GeoTool` behavior. |
| [geo-pack/geopack/registry.py](geo-pack/geopack/registry.py#L18) | `GeoToolRegistry` | `None` | `object` | Provide `GeoToolRegistry` behavior. |
| [geo-pack/geopack/store.py](geo-pack/geopack/store.py#L9) | `DatasetStore` | `state_root: Path, session_id: str` | `object` | Provide `DatasetStore` behavior. |
| [geo-pack/main.py](geo-pack/main.py#L44) | `GeoPackProvider` | `state_root: Path` | `object` | Materialize the one model-visible router tool. |
| [geo-pack/main.py](geo-pack/main.py#L67) | `GeoPackPlugin` | `None` | `object` | Provide `GeoPackPlugin` behavior. |

<!-- END GENERATED SYMBOL MAP -->
