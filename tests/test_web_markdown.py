"""Regression coverage for safe web-console Markdown rendering."""

from llmfetcher.webapp import render_markdown


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
