"""Regression coverage for the browser Agent shell tool."""

import tempfile

from llmfetcher.tools.shell_tools import create_shell_tools


def test_shell_tool_runs_with_popen_pipes() -> None:
    """The shell handler must use Popen-compatible stdout/stderr arguments."""
    with tempfile.TemporaryDirectory() as directory:
        shell = create_shell_tools(sandbox_cwd=directory)[0]
        result = shell.handler(command="printf hello")

    assert result == "[stdout]\nhello"
