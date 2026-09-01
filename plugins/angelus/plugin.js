/** Angelus skin frontend entry.
 * Loaded only while the plugin is enabled. Decorative nodes are tagged with
 * data-angelus-plugin so the host removes them during plugin unload.
 */
(function () {
  "use strict";
  const plugin = "angelus";
  if (!window.Angelus) return;

  function node(className, parent) {
    const el = document.createElement("div");
    el.className = className;
    el.dataset.angelusPlugin = plugin;
    el.setAttribute("aria-hidden", "true");
    parent.appendChild(el);
    return el;
  }

  function mountOrnaments() {
    if (document.querySelector(".angelus-skin-ornaments")) return;
    const shell = node("angelus-skin-ornaments", document.body);
    node("angelus-skin-halo", shell);
    for (let i = 1; i <= 3; i += 1) {
      node(`angelus-skin-wing angelus-skin-wing-l wing-${i}`, shell);
      node(`angelus-skin-wing angelus-skin-wing-r wing-${i}`, shell);
    }
    node("angelus-skin-feathers", shell);
  }

  mountOrnaments();

  window.Angelus.registerCommand(plugin, {
    id: "toggle-ornaments",
    description: "显示/隐藏 Angelus 皮肤的羽翼与光环装饰",
    handler() {
      const shell = document.querySelector(".angelus-skin-ornaments");
      if (!shell) return { visible: false };
      shell.hidden = !shell.hidden;
      return { visible: !shell.hidden };
    },
  });

  window.Angelus.registerSettings(plugin, {
    title: "Angelus Skin",
    description: "昼夜模式跟随 Angelus 的 data-theme；可通过命令 angelus:toggle-ornaments 隐藏装饰层。",
  });
})();
