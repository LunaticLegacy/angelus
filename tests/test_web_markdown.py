"""Regression coverage for safe web-console Markdown rendering."""

from angelus.webapp import render_markdown
from angelus.runtime import _event_payload
from llmfetcher.events import ExecutionEvent


def test_markdown_renders_code_and_escapes_raw_html() -> None:
    """Render common Markdown while retaining raw HTML as harmless text."""
    rendered = render_markdown("# Title\n\n`code`\n\n<script>alert(1)</script>")
    assert "<h1>Title</h1>" in rendered
    assert "<code>code</code>" in rendered
    assert "&lt;script&gt;" in rendered


def test_markdown_renders_gfm_style_tables() -> None:
    """Enable the table rule needed for column-aligned model output."""
    rendered = render_markdown("| Name | Value |\n| --- | --- |\n| A | 1 |")
    assert "<table>" in rendered
    assert "<th>Name</th>" in rendered


def test_live_agent_round_contains_the_same_safe_markdown_html() -> None:
    """SSE round updates use the history renderer rather than plain text."""
    payload = _event_payload(ExecutionEvent(
        source="agent",
        agent_name="coordinator",
        event_type="agent:round",
        message="round complete",
        data={"assistant_content": "# 标题\n\n<script>alert(1)</script>", "reasoning_content": "`checked`"},
    ))

    assert "<h1>标题</h1>" in payload["data"]["assistant_content_html"]
    assert "&lt;script&gt;" in payload["data"]["assistant_content_html"]
    assert "<code>checked</code>" in payload["data"]["reasoning_content_html"]
