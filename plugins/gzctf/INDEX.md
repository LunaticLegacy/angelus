# gzctf/ — GZCTF Helper v1 Plugin INDEX

| File | Responsibility |
|---|---|
| `manifest.json` | Current v1 tool-plugin declaration: persisted non-secret endpoint/account settings and host-rendered transient password login panel. |
| `main.py` | Namespaced GZCTF Tool provider, transient login action, authenticated HTTP helpers, attachment download, dynamic-instance, and batch orchestration logic. |
| `automation.py` | Atomic plugin-private durable state for authorized batch runs. |
| `README.md` | Legacy capability and protocol reference retained for operators. |

## Runtime boundaries

- The host imports `main.py` only after registration, permission approval, and
  explicit load. It publishes 11 `plugin.gzctf.*` Agent tools for coordinator
  and worker roles.
- `base_url` and `username` are non-secret settings. The login panel password
  is a `sensitive` transient field: it has no default and is neither persisted
  nor returned to the browser.
- Cookies, attachment downloads, and batch-run JSON live only under the
  Angelus plugin state directory, never in this source package.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [automation.py](automation.py#L23) | `AutomationRunStore._path` | `run_id: str` | `Path` | Implement `AutomationRunStore._path`. |
| [automation.py](automation.py#L28) | `AutomationRunStore.load` | `run_id: str` | `dict[str, Any]` | Implement `AutomationRunStore.load`. |
| [automation.py](automation.py#L37) | `AutomationRunStore.save` | `run: dict[str, Any]` | `dict[str, Any]` | Implement `AutomationRunStore.save`. |
| [automation.py](automation.py#L45) | `AutomationRunStore.create` | `game_id: int, challenges: list[dict[str, Any]], max_instances: int` | `dict[str, Any]` | Implement `AutomationRunStore.create`. |
| [automation.py](automation.py#L58) | `AutomationRunStore.complete` | `run: dict[str, Any]` | `bool` | Implement `AutomationRunStore.complete`. |
| [automation.py](automation.py#L63) | `AutomationRunStore.active_instances` | `run: dict[str, Any]` | `int` | Implement `AutomationRunStore.active_instances`. |
| [main.py](main.py#L83) | `_GzctfSession.request` | `method: str, url: str, json_body: Any, timeout: float` | `Tuple[int, bytes]` | Implement `_GzctfSession.request`. |
| [main.py](main.py#L104) | `_GzctfSession.has_cookies` | `None` | `bool` | Implement `_GzctfSession.has_cookies`. |
| [main.py](main.py#L107) | `_GzctfSession.save` | `None` | `None` | Implement `_GzctfSession.save`. |
| [main.py](main.py#L113) | `_GzctfSession.clear` | `None` | `None` | Implement `_GzctfSession.clear`. |
| [main.py](main.py#L125) | `_json_of` | `body: bytes` | `Any` | Implement `_json_of`. |
| [main.py](main.py#L134) | `_error_detail` | `body: bytes` | `str` | Implement `_error_detail`. |
| [main.py](main.py#L146) | `_raise` | `status: int, body: bytes, prefix: str` | `None` | Raise a readable error preserving server-side context (>=400). |
| [main.py](main.py#L154) | `_parse_int` | `value: Any` | `Optional[int]` | Implement `_parse_int`. |
| [main.py](main.py#L161) | `_normalize_label` | `value: str` | `str` | Implement `_normalize_label`. |
| [main.py](main.py#L165) | `_walk_strings` | `value: Any` | `Iterable[str]` | Implement `_walk_strings`. |
| [main.py](main.py#L180) | `parse_game_url` | `game_url: str` | `Tuple[str, Optional[int]]` | 推断部署 base URL 与可选 gameId（``/games/{id}``）。 |
| [main.py](main.py#L191) | `fetch_public_key` | `session: _GzctfSession, base_url: str` | `Optional[str]` | 读取 ``/api/config`` 并提取可选的 API 加密公钥。 |
| [main.py](main.py#L198) | `find_public_key` | `obj: Any` | `Optional[str]` | 在 JSON 中递归寻找 GZCTF API 加密公钥。 |
| [main.py](main.py#L217) | `encrypt_api_data` | `plain_text: str, public_key_b64: Optional[str]` | `str` | 用 GZCTF 前端兼容方案（X25519 + AES-GCM）加密一个 API 字段。 |
| [main.py](main.py#L257) | `verify_profile` | `session: _GzctfSession, base_url: str` | `dict` | 确认当前 Cookie 属于已登录用户。 |
| [main.py](main.py#L265) | `perform_login` | `session: _GzctfSession, base_url: str, username: str, password: str` | `dict` | 登录 GZCTF，返回 profile（失败抛 RuntimeError）。 |
| [main.py](main.py#L281) | `fetch_game_details` | `session: _GzctfSession, base_url: str, game_id: int` | `dict` | 拉取比赛参与详情（含题目元数据与队伍排名）。 |
| [main.py](main.py#L293) | `extract_team_info` | `game_details: dict` | `Optional[dict]` | 从比赛详情中提取前端可展示的队伍摘要。 |
| [main.py](main.py#L310) | `list_challenge_candidates` | `game_details: dict` | `List[dict]` | 把 game details 中嵌套的题目负载展平为 challenge-like dict 列表。 |
| [main.py](main.py#L317) | `_collect_challenge_candidates` | `value: Any, dest: List[dict]` | `None` | Implement `_collect_challenge_candidates`. |
| [main.py](main.py#L333) | `_challenge_identifier` | `challenge: dict` | `str` | Implement `_challenge_identifier`. |
| [main.py](main.py#L341) | `_challenge_title` | `challenge: dict` | `str` | Implement `_challenge_title`. |
| [main.py](main.py#L349) | `_challenge_category` | `challenge: dict` | `str` | Implement `_challenge_category`. |
| [main.py](main.py#L363) | `_clean_html` | `text: str` | `str` | Implement `_clean_html`. |
| [main.py](main.py#L369) | `_challenge_labels` | `item: dict` | `List[str]` | Implement `_challenge_labels`. |
| [main.py](main.py#L378) | `_match_challenge_id` | `item: dict, expected: int` | `bool` | Implement `_match_challenge_id`. |
| [main.py](main.py#L386) | `resolve_challenge` | `game_details: dict, challenge_id: str, title: str` | `Optional[dict]` | 按显式 id 或标题模糊匹配题目。 |
| [main.py](main.py#L426) | `fetch_challenge_detail` | `session: _GzctfSession, base_url: str, game_id: int, challenge_id: int` | `dict` | 合并题目详情/实例负载（对缺失端点做容忍）。 |
| [main.py](main.py#L447) | `_merge_dicts` | `base: dict, overlay: dict` | `dict` | Implement `_merge_dicts`. |
| [main.py](main.py#L457) | `_collect_attachments` | `challenge: dict, base_url: str` | `List[dict]` | 收集嵌套负载中的可下载附件 URL。 |
| [main.py](main.py#L507) | `_looks_like_download_url` | `url: str` | `bool` | Implement `_looks_like_download_url`. |
| [main.py](main.py#L518) | `_collect_connection_hints` | `challenge: dict` | `List[str]` | 收集 service/instance/container 等连接提示（含 nc host port 文本）。 |
| [main.py](main.py#L559) | `submit_flag` | `session: _GzctfSession, base_url: str, game_id: int, challenge_id: int, flag: str` | `Tuple[int, bytes]` | 提交一个 flag，404/405 时回退 ``/submit`` 端点。 |
| [main.py](main.py#L579) | `parse_submit_id` | `body: bytes` | `Optional[int]` | 从提交响应中提取 submission id。 |
| [main.py](main.py#L599) | `poll_submission_status` | `session: _GzctfSession, base_url: str, game_id: int, challenge_id: int, submit_id: int, max_polls: int, delay: float` | `Optional[str]` | 轮询判题结果直到 accepted/rejected 或达到上限。 |
| [main.py](main.py#L623) | `classify_verdict` | `payload: Any` | `Optional[str]` | 把多样的判题负载归一化为 accepted/rejected/pending。 |
| [main.py](main.py#L639) | `_url_basename` | `url: str` | `str` | 从 URL 提取默认附件文件名（去除控制字符）。 |
| [main.py](main.py#L646) | `start_challenge_instance` | `session: _GzctfSession, base_url: str, game_id: int, challenge_id: int` | `Tuple[dict, bytes]` | POST 启动动态题目实例，``/instance`` 优先，404/405 时回退 ``/container``。 |
| [main.py](main.py#L683) | `download_attachment` | `session: _GzctfSession, url: str, dest: Path, timeout: float` | `Tuple[str, int]` | 用已登录会话下载附件到 ``dest``，返回 (文件名, 字节数)。 |
| [main.py](main.py#L697) | `_profile_summary` | `profile: dict` | `dict` | Implement `_profile_summary`. |
| [main.py](main.py#L719) | `GzctfProvider.materialize` | `session_id: str, policy: ToolPolicy, role: str` | `list[Tool]` | Create namespaced GZCTF Tools for a coordinator or worker. |
| [main.py](main.py#L766) | `GzctfLoginAction.__call__` | `request: PluginUiActionRequest` | `PluginUiActionResult` | Log in without persisting or echoing the submitted password. |
| [main.py](main.py#L795) | `GzctfPlugin.setup` | `runtime: PluginRuntime` | `None` | Register GZCTF tool definitions and the transient login action. |
| [main.py](main.py#L825) | `GzctfPlugin.teardown` | `None` | `None` | Release the host runtime reference during plugin unload. |
| [main.py](main.py#L836) | `GzctfPlugin._session` | `None` | `_GzctfSession` | Implement `GzctfPlugin._session`. |
| [main.py](main.py#L839) | `GzctfPlugin._config` | `*keys: str, value: str` | `str` | 参数优先，其次回落插件 settings（plugins.json 持久化配置）。 |
| [main.py](main.py#L850) | `GzctfPlugin._login_if_needed` | `session: _GzctfSession, base_url: str, username: str, password: str` | `None` | 优先复用有效 Cookie，否则用账号密码登录。 |
| [main.py](main.py#L869) | `GzctfPlugin._downloads_dir` | `None` | `Path` | Implement `GzctfPlugin._downloads_dir`. |
| [main.py](main.py#L872) | `GzctfPlugin._run_store` | `None` | `AutomationRunStore` | Implement `GzctfPlugin._run_store`. |
| [main.py](main.py#L875) | `GzctfPlugin._safe_download_leaf` | `dest: str, url_name: str` | `Path` | 把目标文件名归一化为 downloads 根内的单层路径（拒绝路径穿越）。 |
| [main.py](main.py#L898) | `GzctfPlugin._tool_login` | `base_url: str, username: str, password: str, **_kwargs: Any` | `dict` | Implement `GzctfPlugin._tool_login`. |
| [main.py](main.py#L924) | `GzctfPlugin._tool_status` | `base_url: str, **_kwargs: Any` | `dict` | Implement `GzctfPlugin._tool_status`. |
| [main.py](main.py#L947) | `GzctfPlugin._tool_team` | `base_url: str, username: str, password: str, **_kwargs: Any` | `dict` | Implement `GzctfPlugin._tool_team`. |
| [main.py](main.py#L972) | `GzctfPlugin._tool_challenges` | `base_url: str, username: str, password: str, category: str, keyword: str, limit: int, **_kwargs: Any` | `dict` | Implement `GzctfPlugin._tool_challenges`. |
| [main.py](main.py#L1030) | `GzctfPlugin._tool_challenge_info` | `base_url: str, challenge_id: str, title: str, username: str, password: str, include_detail: bool, **_kwargs: Any` | `dict` | Implement `GzctfPlugin._tool_challenge_info`. |
| [main.py](main.py#L1095) | `GzctfPlugin._tool_submit_flag` | `base_url: str, challenge_id: str, title: str, flag: str, username: str, password: str, max_polls: int, delay: float, **_kwargs: Any` | `dict` | Implement `GzctfPlugin._tool_submit_flag`. |
| [main.py](main.py#L1171) | `GzctfPlugin._tool_download` | `base_url: str, url: str, dest: str, **_kwargs: Any` | `dict` | Implement `GzctfPlugin._tool_download`. |
| [main.py](main.py#L1192) | `GzctfPlugin._tool_start_instance` | `base_url: str, challenge_id: str, title: str, **_kwargs: Any` | `dict` | Implement `GzctfPlugin._tool_start_instance`. |
| [main.py](main.py#L1239) | `GzctfPlugin._tool_batch_prepare` | `base_url: str, category: str, challenge_ids: list[Any] \| None, max_instances: int, **_kwargs: Any` | `dict` | Create a durable run and prepare attachments without solving anything. |
| [main.py](main.py#L1258) | `GzctfPlugin._tool_batch_status` | `run_id: str, **_kwargs: Any` | `dict` | Implement `GzctfPlugin._tool_batch_status`. |
| [main.py](main.py#L1261) | `GzctfPlugin._tool_instance_acquire` | `run_id: str, challenge_id: str, base_url: str, **_kwargs: Any` | `dict` | Implement `GzctfPlugin._tool_instance_acquire`. |
| [main.py](main.py#L1280) | `GzctfPlugin._batch_summary` | `run: dict` | `dict` | Implement `GzctfPlugin._batch_summary`. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [automation.py](automation.py#L18) | `AutomationRunStore` | `state_dir: Path \| str` | `object` | Provide `AutomationRunStore` behavior. |
| [main.py](main.py#L66) | `_GzctfSession` | `state_dir: Path` | `object` | Minimal cookie-aware HTTP session built on urllib + MozillaCookieJar. |
| [main.py](main.py#L705) | `GzctfProvider` | `plugin: 'GzctfPlugin'` | `object` | Materialize the authenticated GZCTF operations for eligible Agents. |
| [main.py](main.py#L752) | `GzctfLoginAction` | `plugin: 'GzctfPlugin'` | `object` | Perform one password-only transient login from the host panel. |
| [main.py](main.py#L789) | `GzctfPlugin` | `None` | `object` | GZCTF Helper 插件：登录、题目信息拉取、flag 提交判题、附件下载与动态实例启动。 |

<!-- END GENERATED SYMBOL MAP -->
