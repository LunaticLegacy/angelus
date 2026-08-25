"""Regression coverage for the active Workbench HTML and classic script."""

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_SCRIPT = PROJECT_ROOT / "frontend" / "static" / "app.js"
INDEX_TEMPLATE = PROJECT_ROOT / "frontend" / "templates" / "index.html"
COMPONENTS_DIR = PROJECT_ROOT / "frontend" / "static" / "components"


def test_event_listeners_target_existing_template_elements() -> None:
    """Keep direct Workbench event listeners aligned with static HTML IDs."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")
    stylesheet = (PROJECT_ROOT / "frontend" / "static" / "app.css").read_text(encoding="utf-8")
    element_ids = set(re.findall(r'\\bid="([^"]+)"', template))
    listener_ids = set(re.findall(r'\\$\\("([^"]+)"\\)\\.addEventListener', script))

    assert listener_ids <= element_ids


def test_workspace_row_actions_target_their_own_session_without_switching() -> None:
    """Project actions stay on their rendered session row, even when it is inactive."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'id="workspace-open-hint"' in template
    assert 'id="open-workspace"' not in template
    assert 'id="change-workspace-directory"' not in template
    assert 'data-session-change-directory=' in script
    assert 'data-session-open-folder=' in script
    assert 'data-session-agent-profile=' in script
    assert "function openAgentProfile" in script
    assert 'aria-label="更改 ${escapeHtml(item.name)} 的项目目录"' in script
    assert 'aria-label="打开 ${escapeHtml(item.name)} 的项目目录"' in script
    assert "open-folder" in script
    assert "encodeURIComponent(targetSessionId)" in script
    assert '$("workspace").addEventListener("change", event=>{const nextWorkspaceId=event.target.value;switchSession(nextWorkspaceId)' in script
    assert "function changeWorkspaceDirectory(targetSessionId)" in script
    assert "function openWorkspaceFolder(targetSessionId)" in script


def test_active_workbench_uses_component_views_through_an_es_module_entrypoint() -> None:
    """Keep the running Workbench on the componentized module path."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'type="module" src="/static/app.js?v=workbench-' in template
    assert 'from "./components/chat-view.js?v=history-pagination-2"' in script
    assert 'from "./components/trace-view.js"' in script
    assert 'from "./components/task-plan-view.js"' in script
    assert (COMPONENTS_DIR / "chat-view.js").is_file()
    assert (COMPONENTS_DIR / "trace-view.js").is_file()
    assert (COMPONENTS_DIR / "task-plan-view.js").is_file()


def test_workbench_uses_the_angelus_mission_control_visual_system() -> None:
    """Keep the redesigned brand, responsive shell, and accessibility layer active."""
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")
    stylesheet = (PROJECT_ROOT / "frontend" / "static" / "app.css").read_text(encoding="utf-8")

    assert "<title>Angelus · Agent Workbench</title>" in template
    assert 'class="brand-mark">A</span>' in template
    assert 'src="/static/app.js?v=workbench-82"' in template
    assert 'href="/static/app.css?v=workbench-81"' in template
    assert "本地优先" not in template
    assert "Workbench 2026 — calm mission-control visual system." in stylesheet
    assert "grid-template-columns:248px minmax(560px,1fr) 368px" in stylesheet
    assert "@media (max-width:1020px)" in stylesheet
    assert "@media (prefers-reduced-motion:reduce)" in stylesheet


def test_task_plan_statuses_are_read_only_and_preserve_real_line_breaks() -> None:
    """Render lifecycle-owned states as labels and retain JSON newline layout."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    component = (COMPONENTS_DIR / "task-plan-view.js").read_text(encoding="utf-8")
    stylesheet = (PROJECT_ROOT / "frontend" / "static" / "app.css").read_text(encoding="utf-8")

    assert '<span class="task-state ${escapeHtml(status)}"' in component
    assert '<select data-task-id=' not in component
    assert "updatePlanStatus" not in script
    assert '$("task-plan").addEventListener("change"' not in script
    assert ".plan-summary,.task-description { white-space:pre-wrap;" in stylesheet


def test_tool_payloads_use_structured_json_and_verbatim_stdout_views() -> None:
    """Tool call cards must decode JSON escapes without altering raw stdout."""
    chat_component = (COMPONENTS_DIR / "chat-view.js").read_text(encoding="utf-8")
    stylesheet = (PROJECT_ROOT / "frontend" / "static" / "app.css").read_text(encoding="utf-8")

    assert "function decodeJson(value)" in chat_component
    assert "function decodeDisplayString(value)" in chat_component
    assert "JSON.parse(text)" in chat_component
    assert "function legacyPythonContainerToJson(source)" in chat_component
    assert "legacyPythonContainerToJson(text)" in chat_component
    assert "escapeHtml(decodeDisplayString(value))" in chat_component
    assert 'class="tool-json"' in chat_component
    assert 'class="tool-stdout"' in chat_component
    assert 'return `<pre class="tool-stdout">${escapeHtml(String(value))}</pre>`' in chat_component
    assert ".tool-json { max-height:280px; overflow:auto;" in stylesheet


def test_live_and_historical_tool_cards_share_the_chat_view_renderer() -> None:
    """SSE, aggregate replay, and selected-Agent replay must render one card type."""
    script = APP_SCRIPT.read_text(encoding="utf-8")

    assert "chatView.append({role,content,reasoning,content_html:contentHtml,reasoning_html:reasoningHtml,tools,usage,model_duration_ms:modelDurationMs,timestamp},agentName)" in script
    assert "chatView.render(messages, assistantLabel)" in script
    assert "chatView.buildMessage(message, selectedAgent)" in script


def test_transcript_uses_cursor_pages_and_one_top_scroll_loader() -> None:
    """Keep 200-message cursor paging locked, retryable, and viewport-stable."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    chat_component = (COMPONENTS_DIR / "chat-view.js").read_text(encoding="utf-8")

    assert 'new URLSearchParams({agent,limit:"200"})' in script
    assert 'params.set("cursor",String(cursor))' in script
    assert "events?limit=1" not in script
    assert '$("chat").addEventListener("scroll"' in script
    assert '$("chat").scrollTop<=24' in script
    assert "messageLoadPending" in script
    assert "snapshot.generation!==historyGeneration" in script
    assert "chat.scrollHeight - previousHeight + previousTop" in script
    assert "button.after(fragment)" in script
    assert "button.disabled=false" in script
    assert "function ensureLoadMoreMessagesButton()" in script
    assert 'button.textContent="加载失败，点击重试"' in script
    assert '$("chat").addEventListener("click"' in script
    assert "chat.replaceChildren(loadMore)" in chat_component


def test_new_session_requires_a_native_selected_project_directory() -> None:
    """Keep project files separate from internal session manifests and state."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'id="new-session-path"' in template
    assert 'id="choose-session-directory"' in template
    assert 'data-session-change-directory=' in script
    assert 'id="new-session-feedback"' in template
    assert 'apiPost("/api/workspace-directory/pick")' in script
    assert "project_path:selectedPath" in script
    assert "opened.project_path" in script
    assert "/project-path`" in script


def test_trace_uses_reverse_cursor_and_durable_offset_for_sse() -> None:
    """Initial Trace hydration must also establish the byte resume watermark."""
    script = APP_SCRIPT.read_text(encoding="utf-8")

    assert 'params.set("cursor",String(cursor))' in script
    assert "traceBefore=page.next_cursor??null" in script
    assert "durableEventOffset=Number(page.durable_offset||0)" in script
    assert 'durableEventOffset > 0 ? `cursor=${durableEventOffset}`' in script


def test_reasoning_is_visible_transcript_content_not_a_disclosure() -> None:
    """Reasoning must be visible for both live and restored message cards."""
    chat_component = (COMPONENTS_DIR / "chat-view.js").read_text(encoding="utf-8")
    stylesheet = (PROJECT_ROOT / "frontend" / "static" / "app.css").read_text(encoding="utf-8")

    assert '<section class="reasoning" aria-label="思考过程">' in chat_component
    assert '<details class="reasoning">' not in chat_component
    assert '${reasoning ? `<section class="reasoning"' in chat_component
    assert '${thought}</div></section>` : ""}${content ? `<div class="bubble' in chat_component
    assert ".message .reasoning { max-height:180px;" in stylesheet
    assert ".message .reasoning > div { max-height:145px; padding:0; overflow:auto;" in stylesheet


def test_context_graph_dialog_contains_selectable_raw_context_preview() -> None:
    """Keep the context inspector's full prompt preview wired to its API route."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")
    stylesheet = (PROJECT_ROOT / "frontend" / "static" / "app.css").read_text(encoding="utf-8")

    assert 'data-context-dialog-tab="graph"' in template
    assert 'data-context-dialog-tab="prompt"' in template
    assert 'id="context-prompt-preview"' in template
    assert 'id="context-metadata-list"' in template
    assert 'id="context-request-stats"' in template
    assert 'id="context-prompt-cards"' not in template
    assert "function selectContextDialogTab(tab)" in script
    assert "function loadContextPrompt(agentId)" in script
    assert "function decodePromptText(value)" in script
    assert "Actual line feeds remain line feeds." in script
    assert "item.source" in script
    assert "/context`" in script
    assert "不能替代真实请求" in script
    assert "messages.length?formatPromptPreview(messages)" not in script
    assert "let contextDialogAgent = \"\";" in script
    assert 'event.type === "agent:remote_request"' in script
    assert "loadContextPrompt(contextDialogAgent)" in script
    assert "stats.tool_schema_characters" in script
    assert "width:min(1440px,calc(100vw - 32px))" in stylesheet
    assert "height:min(920px,calc(100vh - 32px))" in stylesheet
    assert ".context-prompt-preview { display:block; flex:1 1 auto; min-height:0; max-height:none;" in stylesheet
    assert "#context-panel-graph { display:grid; grid-template-rows:auto 270px minmax(190px,1fr);" in stylesheet
    assert "#context-panel-graph .context-graph-details { min-height:0; height:100%;" in stylesheet


def test_workbench_uses_the_current_settings_persistence_api() -> None:
    """Prevent stale setting helper names from blocking session initialization."""
    script = APP_SCRIPT.read_text(encoding="utf-8")

    assert "persistAgentSettings" not in script
    assert "restoreAgentSettings" not in script
    assert "persistConnection" not in script
    assert "openSettingsDialog" not in script
    assert "function persistSettings" in script
    assert "function restoreSettings" in script


def test_settings_categories_use_left_navigation_buttons() -> None:
    """Keep each settings navigation category connected to one content pane."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")
    navigation_sections = set(re.findall(r'data-settings-section="([^"]+)"', template))
    panel_sections = set(re.findall(r'data-settings-panel="([^"]+)"', template))

    assert navigation_sections == panel_sections == {"connection", "agent", "permissions", "mcp", "plugins", "future"}
    assert 'id="settings-section"' not in template
    assert 'querySelectorAll("[data-settings-section]")' in script


def test_memory_authorizations_are_selected_and_sent_as_run_grants() -> None:
    """Keep memory grants session-scoped, selectable, and present in run payloads."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'id="session-memory-search"' in template
    assert 'id="session-memory-options"' in template
    assert 'id="session-memory-selected"' in template
    assert '"session-memory-sessions"' in script
    assert "session_memory_search_sessions: selectedMemorySessions()" in script
    assert "session_artifact_open_sessions: selectedMemorySessions()" in script


def test_retry_count_is_session_persisted_and_sent_with_runs() -> None:
    """Expose the additional timeout retry count as a saved Agent setting."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'id="max-retries"' in template
    assert 'value="3"' in template
    assert 'max_retries: Number($("max-retries").value)' in script
    assert '"max-retries"' in script
    assert re.search(r'/static/app\.js\?v=workbench-\d+', template)


def test_usage_cards_reuse_reconciled_agent_status_lights() -> None:
    """Keep per-Agent usage cards aligned with the canonical status projection."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    stylesheet = (PROJECT_ROOT / "frontend" / "static" / "app.css").read_text(encoding="utf-8")

    assert "const view=agentStateView(agent.id)" in script
    assert 'class="agent-state ${escapeHtml(view.ui)}"' in script
    assert "apiJson(graphUrl()).catch(()=>null)" in script
    assert ".usage-agent .agent-state.running" in stylesheet
    assert re.search(r'/static/app\.js\?v=workbench-\d+', INDEX_TEMPLATE.read_text(encoding="utf-8"))


def test_usage_tiles_show_current_lifecycle_tokens_in_green() -> None:
    """Each session usage tile and per-Agent card shows the latest run's tokens as a green +X line."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    stylesheet = (PROJECT_ROOT / "frontend" / "static" / "app.css").read_text(encoding="utf-8")

    assert "function usageCells(usage, run=null)" in script
    assert '<i class="usage-round">+${Number(run[key] || 0).toLocaleString()}</i>' in script
    assert "usageCells(usage, payload.run)" in script
    assert "usageCells(agent.usage, agent.run)" in script
    assert '<small>${label}</small><b>${Number(usage[key] || 0).toLocaleString()}</b>' in script
    assert ".usage-round { display:block; color:var(--green);" in stylesheet


def test_running_session_does_not_turn_unknown_agents_into_running_agents() -> None:
    """Keep each Agent light tied to evidence, not the session-wide run flag."""
    script = APP_SCRIPT.read_text(encoding="utf-8")

    assert 'if(runActive && agentId !== "all")' not in script
    assert 'return stateView("idle","尚无执行事件",agentId);' in script
    assert "const persisted=currentGraph.node_states?.[agentId];" in script


def test_completed_swarm_is_blue_even_when_a_worker_failed() -> None:
    """Represent successful coordinator recovery as a completed aggregate run."""
    script = APP_SCRIPT.read_text(encoding="utf-8")

    assert 'terminal==="completed"' in script
    assert 'views.some(view=>view.canonical==="running")' in script
    assert 'return stateView("completed","当前会话：运行完毕",agentId);' in script
    # The done handler now schedules a debounced graph+plan reload instead of
    # firing an immediate fetch; the reload must still be wired up.
    assert 'scheduleGraphPlanReload();' in script
    assert 'loadGraph().then(loadAgents)' in script


def test_agents_panel_renders_only_the_single_topology_tree() -> None:
    """Avoid presenting the same Swarm hierarchy twice in the Agents panel."""
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'id="inspector-agents-list"' in template
    assert 'id="execution-graph"' not in template
    assert "点击下方 Agent 卡片可查看该 Agent 的上下文。" in template


def test_plan_panel_selects_an_agent_owned_plan_and_topology_fills_height() -> None:
    """The inspector exposes isolated plans and no longer caps topology height."""
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")
    script = APP_SCRIPT.read_text(encoding="utf-8")
    stylesheet = (PROJECT_ROOT / "frontend" / "static" / "app.css").read_text(encoding="utf-8")

    assert 'id="plan-agent"' in template
    assert "selectedPlanAgent" in script
    assert "agent=${encodeURIComponent(selectedPlanAgent)}" in script
    assert ".inspector-agents-list { flex:1 1 auto; min-height:0; max-height:none;" in stylesheet


def test_managed_mcp_console_replaces_browser_json_configuration() -> None:
    """Keep MCP configuration in the managed global registry and session grants."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'data-settings-panel="mcp"' in template
    assert 'id="mcp-server-form"' in template
    assert 'id="mcp-role-coordinator"' in template
    assert 'id="mcp-role-worker"' in template
    assert "function loadMcpConsole()" in script
    assert "function saveMcpBinding(serverId)" in script
    assert "function mcpServers()" not in script
    assert "enable_mcp:" not in script


def test_light_plan_agent_picker_overrides_the_dark_surface() -> None:
    """The plan Agent selector must remain readable in the light theme."""
    stylesheet = (PROJECT_ROOT / "frontend" / "static" / "app.css").read_text(encoding="utf-8")

    assert ":root[data-theme=\"light\"] .plan-agent-picker" in stylesheet
    assert ":root[data-theme=\"light\"] .plan-agent-picker select" in stylesheet


def test_kimi_code_connector_preset_survives_provider_refresh() -> None:
    """Kimi Code is a named connector choice, not a fragile manual preset."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'value="kimi-code"' in template
    assert 'const KIMI_CODE_BASE_URL = "https://api.kimi.com/coding/v1";' in script
    assert 'const KIMI_CODE_DEFAULT_MODEL = "kimi-for-coding";' in script
    assert "const KIMI_CODE_TEMPERATURE = 1;" in script
    assert "function applyProviderPreset()" in script
    assert "temperature.disabled=isKimi" in script
    assert "providerLabel(x)" in script
    assert 'id="provider-hint"' in template


def test_applied_steering_is_a_right_aligned_chat_input() -> None:
    """Keep applied steering beside the original user messages in chat."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    chat_component = (COMPONENTS_DIR / "chat-view.js").read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")
    stylesheet = (PROJECT_ROOT / "frontend" / "static" / "app.css").read_text(encoding="utf-8")

    assert 'id="steer-composer"' not in template
    assert 'id="steer-hint"' in template
    assert template.index('id="composer"') < template.index('id="steer-hint"')
    assert 'id="inspector-steer"' not in template
    assert 'data-inspector-panel="inspector-steer"' not in template
    assert 'selectInspectorPanel("inspector-steer")' not in script
    assert "function appendSteerMessage" in script
    assert 'if(role === "steer") return appendSteerMessage(content);' in script
    assert 'chatView.append({role:"steer",content:text})' in script
    assert 'className = "message steer"' in chat_component
    assert ".message.user,.message.steer { margin-left:auto; }" in stylesheet
    assert re.search(r'/static/app\.js\?v=workbench-\d+', template)


def test_context_dialog_exposes_compaction_input_preview_tab() -> None:
    """Keep the third context-dialog tab wired to its read-only API route."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'data-context-dialog-tab="compaction"' in template
    assert 'id="context-tab-compaction"' in template
    assert 'id="context-panel-compaction"' in template
    assert 'id="context-compaction-title"' in template
    assert 'id="context-compaction-note"' in template
    assert 'id="context-compaction-status"' in template
    assert 'id="context-compaction-stats"' in template
    assert 'id="context-compaction-preview"' in template
    assert "function renderCompactionInput(payload)" in script
    assert "function loadCompactionInput(agentId)" in script
    assert "/context/compaction-input`" in script
    assert 'tab==="compaction"?"compaction":"graph"' in script
    assert "$(\"context-panel-compaction\").hidden=selected!==\"compaction\"" in script
    assert "loadCompactionInput(agentId)" in script
    assert "payload.estimated_tokens" in script
    assert "payload.omitted" in script
    assert "压缩器没有可发送的输入" in script
