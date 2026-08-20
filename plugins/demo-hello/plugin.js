/**
 * demo-hello frontend entry — loaded by frontend/static/plugins.js from
 * /plugins/demo-hello/static/plugin.js (whitelisted in manifest.frontend.assets).
 * Uses the window.Angelus bridge (the only safe UI registration surface, S8).
 */
(function () {
  "use strict";
  const plugin = "demo-hello";

  // 1) Inspector panel — appears as a new tab in the workbench "执行动态" area.
  const panel = window.Angelus.registerPanel(plugin, {
    id: "status",
    title: "Demo Hello",
    render(body) {
      body.innerHTML =
        '<div class="demo-hello-card">' +
        '<p class="eyebrow">PLUGIN DEMO</p>' +
        '<h4>插件前端显示成功 🎉</h4>' +
        '<p>这个面板由 <code>plugins/demo-hello/plugin.js</code> 通过 ' +
        '<code>window.Angelus.registerPanel</code> 注册。</p>' +
        '<button id="demo-hello-call-api" type="button">调用插件 API</button>' +
        '<pre id="demo-hello-result" class="demo-hello-result">点击按钮查看 ' +
        "/plugins/demo-hello/api/hello 的返回</pre>" +
        "</div>";
      body
        .querySelector("#demo-hello-call-api")
        .addEventListener("click", async () => {
          const out = body.querySelector("#demo-hello-result");
          out.textContent = "请求中…";
          try {
            const res = await fetch("/plugins/demo-hello/api/hello");
            const data = await res.json();
            out.textContent = JSON.stringify(data, null, 2);
          } catch (error) {
            out.textContent = "调用失败: " + error.message;
          }
        });
    },
  });

  // 2) Command — dispatchable via window.Angelus.dispatchCommand("demo-hello:hello").
  const command = window.Angelus.registerCommand(plugin, {
    id: "hello",
    description: "返回插件问候（示例命令）",
    handler(args) {
      const name = Array.isArray(args) && args[0] ? String(args[0]) : "world";
      return {
        message: `Hello, ${name}! (from demo-hello command)`,
        time: new Date().toISOString(),
      };
    },
  });

  // 3) Settings placeholder — desktop settings page not in this iteration (D3).
  window.Angelus.registerSettings(plugin, {
    title: "Demo Hello 设置",
    description: "本期不渲染设置页（D3）；注册已被桥记录。",
  });

  console.info("[demo-hello] panel:", panel, "command:", command);
})();
