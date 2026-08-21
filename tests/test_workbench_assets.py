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


def test_workspace_button_opens_current_directory_without_replacing_the_session() -> None:
    """The workspace button is a host-file-manager action, not a session switch."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'id="open-workspace"' in template
    assert 'id="workspace-open-hint"' in template
    assert "open-folder" in script
    assert "encodeURIComponent(workspaceId)" in script
    assert '$("workspace").addEventListener("change", event=>{const nextWorkspaceId=event.target.value;switchSession(nextWorkspaceId)' in script
    assert '$("open-workspace").addEventListener("click"' in script


def test_active_workbench_uses_component_views_through_an_es_module_entrypoint() -> None:
    """Keep the running Workbench on the componentized module path."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'type="module" src="/static/app.js?v=workbench-' in template
    assert 'from "./components/chat-view.js?v=tool-payload-2"' in script
    assert 'from "./components/trace-view.js"' in script
    assert 'from "./components/task-plan-view.js"' in script
    assert (COMPONENTS_DIR / "chat-view.js").is_file()
    assert (COMPONENTS_DIR / "trace-view.js").is_file()
    assert (COMPONENTS_DIR / "task-plan-view.js").is_file()


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

    assert "chatView.append({role,content,reasoning,content_html:contentHtml,reasoning_html:reasoningHtml,tools},agentName)" in script
    assert "chatView.render(messages, assistantLabel)" in script
    assert "chatView.buildMessage(message, selectedAgent)" in script


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

    assert navigation_sections == panel_sections == {"connection", "agent", "plugins", "future"}
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


def test_running_session_does_not_turn_unknown_agents_into_running_agents() -> None:
    """Keep each Agent light tied to evidence, not the session-wide run flag."""
    script = APP_SCRIPT.read_text(encoding="utf-8")

    assert 'if(runActive && agentId !== "all")' not in script
    assert 'return stateView("idle","尚无执行事件",agentId);' in script
    assert "const persisted=currentGraph.node_states?.[agentId];" in script


def test_completed_swarm_is_blue_even_when_a_worker_failed() -> None:
    """Represent successful coordinator recovery as a completed aggregate run."""
    script = APP_SCRIPT.read_text(encoding="utf-8")

    assert 'currentGraph.run_status?.status==="completed"' in script
    assert 'return stateView("completed","当前会话：运行完毕",agentId);' in script
    assert 'finish(); loadGraph().then(loadAgents)' in script


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


def test_agent_settings_expose_native_mcp_tool_configuration() -> None:
    """Keep MCP discovery an explicit Agent-run setting with JSON validation."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'id="enable-mcp"' in template
    assert 'id="mcp-servers"' in template
    assert "function mcpServers()" in script
    assert "enable_mcp:" in script
    assert "mcp_servers:" in script


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
