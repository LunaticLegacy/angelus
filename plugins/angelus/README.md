# Angelus Skin Plugin

一个面向 Angelus Workbench 插件系统 v1 的纯视觉皮肤插件。

## 设计

- **Day**：珍珠白、冰蓝、浅薰衣草，弱玻璃质感。
- **Night**：深海军蓝、靛紫与冰白高光。
- **Angelus motif**：中心光环、三对羽翼状装饰、星芒、轻量羽毛纹理。
- 不改宿主业务逻辑；插件卸载后 CSS 与装饰 DOM 会一起消失。

## 安装

```bash
angelus plugin install ./angelus -y
angelus plugin enable angelus
```

也可以把整个 `angelus/` 目录复制到 `<app_data>/plugins/` 后，在 Angelus 插件页中“加入工作台”并启用。

## 昼夜模式

插件跟随宿主现有主题：

- 默认 / 无 `data-theme`：夜间模式
- `<html data-theme="light">`：白天模式

## 可选命令

```js
window.Angelus.dispatchCommand("angelus:toggle-ornaments")
```

可临时隐藏/显示光环与三对羽翼装饰。

## 文件

- `manifest.json` — v1 插件清单
- `main.py` — 最小 Python 入口
- `plugin.js` — 装饰层与命令
- `plugin.css` — 昼夜皮肤
