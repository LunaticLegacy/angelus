/**
 * example-tool 前端桥接（S8 window.Angelus）。
 *
 * 仅当本文件出现在 manifest.frontend.assets 白名单内时，后端才会通过
 * GET /plugins/example-tool/static/plugin.js 服务它（docs/plugin-api.md §6.1）；
 * 未启用插件的前端资源一律 404，脚本永远不会被注入。
 */
(function () {
  "use strict";

  if (!window.Angelus) {
    console.warn("[example-tool] window.Angelus bridge unavailable");
    return;
  }

  // 命令名会被桥接层命名空间为 "example-tool:search"（plugin:id）。
  window.Angelus.registerCommand("example-tool", {
    id: "search",
    description: "调用插件 web_search 工具（演示命令）",
    handler: function (args, flags) {
      var query = (args && args[0]) || "plugin";
      console.log("[example-tool] search command: " + query);
      return { ok: true, query: query };
    },
  });
})();
