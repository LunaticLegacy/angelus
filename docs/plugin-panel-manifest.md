# 声明式插件功能面板

Angelus 插件可在 `manifest.json` 声明由宿主渲染的功能面板。用户只会
看到插件作者声明的输入和按钮；manifest 不能注入 HTML、JavaScript 或任意
HTTP 路由。

## 分工

- `settings_schema`：长期保存的非敏感配置。用户保存后，在下次插件加载时由
  `PluginRuntime.setting(key, default)` 读取。
- `frontend.panels`：一次性功能输入。提交值不会写入插件设置；宿主校验后只
  交给当前已加载插件注册的 action。

面板仅适用于 `kind: "tool"` 插件，因为 action handler 必须由 Python 的
`setup()` 显式注册。

## Manifest

```json
{
  "kind": "tool",
  "entry": "main",
  "frontend": {
    "assets": [],
    "settings": false,
    "panels": [
      {
        "id": "lookup",
        "title": "知识查询",
        "description": "查找本地知识。",
        "action": "lookup",
        "submit_label": "查询",
        "fields": [
          {
            "key": "query",
            "type": "string",
            "title": "关键词",
            "required": true,
            "placeholder": "输入查询内容"
          },
          {
            "key": "limit",
            "type": "integer",
            "title": "结果数",
            "default": 10,
            "minimum": 1,
            "maximum": 100
          }
        ]
      }
    ]
  }
}
```

`id`、`action` 和字段 `key` 必须是受限的插件本地标识符。字段类型是
`string`、`integer`、`number` 或 `boolean`；`enum`、数值范围、`placeholder`
和 `format: uri | path | textarea` 与 settings schema 的含义一致。

只有一次性 panel 可以声明密码输入，且必须同时使用
`"format": "password"` 与 `"sensitive": true`：它不能给 `default`，不会进入
插件 settings、浏览器存储或 API 事件记录。所有敏感名称（如 `token`、`api_key`、
`password`）仍禁止出现在 `settings_schema` 中。

## Python action

```python
from angelus.modules.plugin_module import PluginUiActionRequest, PluginUiActionResult


def lookup(request: PluginUiActionRequest) -> PluginUiActionResult:
    query = request.value("query", "")
    limit = request.value("limit", 10)
    return PluginUiActionResult("查询结果", f"{query}: {limit}", "success")


class Plugin:
    def setup(self, runtime) -> None:
        runtime.register_ui_action("lookup", lookup)

    def teardown(self) -> None:
        return None
```

每个 manifest panel 都必须恰好对应一个 `register_ui_action()`；缺失、重复或
未声明的 action 会使整个插件加载失败。结果仅含 `title`、`content` 和
`tone`（`info`、`success`、`error`），由宿主以纯文本回显。

## HTTP 边界

浏览器仅能调用：

```text
POST /api/plugins/{plugin_id}/panels/{panel_id}/invoke
```

请求体只能包含该 panel 声明的字段。插件未加载、panel 不存在、字段非法、或
action 未注册都会得到明确的 4xx 响应。
