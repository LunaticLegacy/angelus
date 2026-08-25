"""Official MCP SDK bridge coverage with a real stdio server."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from angelus.mcp_tools import MCPToolError, create_mcp_tools


_SERVER = """\
from mcp.server.mcpserver import MCPServer

server = MCPServer("fixture")

@server.tool(description="Add two whole numbers.")
def add(left: int, right: int) -> str:
    return str(left + right)

server.run(transport="stdio")
"""


def test_stdio_mcp_tools_are_discovered_and_called_without_shell(tmp_path: Path) -> None:
    server_path = tmp_path / "mcp_server.py"
    server_path.write_text(_SERVER, encoding="utf-8")
    bridge, tools = create_mcp_tools([{
        "name": "fixture",
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(server_path)],
        "env": [],
    }])
    try:
        tool = next(item for item in tools if item.name == "mcp.fixture.add")
        assert tool.schemas.to_dict()["properties"]["left"]["type"] == "integer"
        result = tool.handler(left=20, right=22)
        assert result["content"][0]["text"] == "42"
        assert result["is_error"] is False
    finally:
        bridge.close()


def test_mcp_rejects_inline_secret_values() -> None:
    with pytest.raises(MCPToolError, match="env must contain environment-variable names"):
        create_mcp_tools([{
            "name": "bad-env",
            "transport": "stdio",
            "command": "python",
            "env": ["TOKEN=do-not-store-secrets-here"],
        }])


def test_desktop_sidecar_collects_official_mcp_client_runtime() -> None:
    script = (Path(__file__).resolve().parents[1] / "scripts" / "build_backend.py").read_text(
        encoding="utf-8"
    )
    assert '"--collect-submodules",\n        "mcp.client",' in script
    assert '"--collect-submodules",\n        "mcp.shared",' in script
    assert '"--collect-data",\n        "mcp",' in script


def test_desktop_sidecar_build_uses_a_cross_platform_non_shell_launcher() -> None:
    root = Path(__file__).resolve().parents[1]
    package = (root / "package.json").read_text(encoding="utf-8")
    launcher = (root / "scripts" / "build-backend.mjs").read_text(encoding="utf-8")

    assert '"build:backend": "node scripts/build-backend.mjs"' in package
    assert "spawnSync" in launcher
    assert "ANGELUS_PYTHON" in launcher
    assert "bash scripts/" not in package.lower()
