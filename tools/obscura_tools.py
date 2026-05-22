"""Obscura Tool —— 将 headless browser CLI 封装为 Agent 可调用的 Tool.

提供两种使用模式：
1. CLI 模式：调用 obscura fetch 命令（需要 obscura 在 PATH 中）
2. CDP 模式：连接已启动的 obscura serve 服务（需先启动 serve）

当前实现以 CLI 模式为主，CDP 模式预留接口。

注意：使用前请确保 obscura 可执行文件已在系统 PATH 中，或通过 OBSCURA_BIN 环境变量指定路径。
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional

from ..tool import Tool


# ---------------------------------------------------------------------------
# CLI 模式
# ---------------------------------------------------------------------------

def _get_obscura_bin() -> str:
    """Get obscura binary path from environment or default to 'obscura' in PATH."""
    return os.environ.get("OBSCURA_BIN", "obscura")


async def _obscura_fetch_cli(**kwargs: Any) -> Dict[str, Any]:
    """Execute obscura fetch via CLI.

    Args:
        url: Target URL (required)
        mode: Output mode - "html", "text", or "links" (default: text)
        selector: CSS selector to extract specific elements (optional)
        wait: Seconds to wait after page load (default: 3)
        wait_until: Wait event - "load", "domcontentloaded", "networkidle" (default: load)
        stealth: Enable anti-detection mode (default: false)
        eval_js: JavaScript expression to evaluate on the page (optional)
    """
    url = kwargs["url"]
    mode = kwargs.get("mode", "text")
    selector = kwargs.get("selector", "")
    wait = kwargs.get("wait", 3)
    wait_until = kwargs.get("wait_until", "load")
    stealth = kwargs.get("stealth", False)
    eval_js = kwargs.get("eval_js", "")

    obscura_bin = _get_obscura_bin()
    cmd_parts = [
        obscura_bin,
        "fetch",
        f"'{url}'",
        "--dump", str(mode),
        "--wait", str(wait),
        "--wait-until", str(wait_until),
        "--quiet",
    ]
    if selector:
        cmd_parts.extend(["--selector", selector])
    if stealth:
        cmd_parts.append("--stealth")
    if eval_js:
        cmd_parts.extend(["-e", eval_js])

    cmd = " ".join(cmd_parts)

    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=wait + 15,  # hard ceiling
    )

    return {
        "url": url,
        "mode": mode,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": result.returncode == 0,
    }


async def _obscura_scrape_cli(**kwargs: Any) -> Dict[str, Any]:
    """Batch scraping via CLI.
    
    """
    urls = kwargs.get("urls", [])
    if isinstance(urls, str):
        urls = [urls]
    concurrency = kwargs.get("concurrency", 5)
    timeout = kwargs.get("timeout", 30)
    eval_js = kwargs.get("eval_js", "")

    obscura_bin = _get_obscura_bin()
    cmd_parts = [
        obscura_bin,
        "scrape",
        "--concurrency", str(concurrency),
        "--timeout", str(timeout),
        "--format", "json",
    ]
    if eval_js:
        cmd_parts.extend(["-e", eval_js])
    for u in urls:
        cmd_parts.append(f"'{u}'")

    cmd = " ".join(cmd_parts)

    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout + 15,
    )

    stdout_text = result.stdout.strip()
    parsed = None
    if stdout_text:
        try:
            parsed = json.loads(stdout_text)
        except json.JSONDecodeError:
            parsed = None

    return {
        "urls": urls,
        "exit_code": result.returncode,
        "stdout_raw": stdout_text,
        "parsed": parsed,
        "stderr": result.stderr,
        "ok": result.returncode == 0 and parsed is not None,
    }


# ---------------------------------------------------------------------------
# CDP 模式（预留）
# ---------------------------------------------------------------------------

class ObscuraCDPClient:
    """预留：通过 CDP WebSocket 连接已启动的 obscura serve 实例。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 9222) -> None:
        self._host = host
        self._port = port
        self._ws_url: Optional[str] = None

    # TODO: implement CDP session management (Page.navigate, Runtime.evaluate, DOM.querySelector, etc.)


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------

def create_obscura_tools() -> List[Tool]:
    """Create Agent-ready tools for web scraping via Obscura."""
    return [
        Tool(
            name="web_fetch",
            description=(
                "Fetch a single webpage using a headless browser and extract content. "
                "Supports html/text/links output modes, CSS selectors, JavaScript evaluation, "
                "and stealth mode. "
                "This beorser is the FASTEST headless browser for you to fetch a URL."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Target URL to fetch",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["html", "text", "links"],
                        "default": "text",
                        "description": "Output extraction mode",
                    },
                    "selector": {
                        "type": "string",
                        "default": "",
                        "description": "CSS selector to extract specific elements only",
                    },
                    "wait": {
                        "type": "integer",
                        "default": 3,
                        "minimum": 0,
                        "description": "Seconds to wait after initial page load",
                    },
                    "wait_until": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle"],
                        "default": "load",
                        "description": "Page event to wait for before extraction",
                    },
                    "stealth": {
                        "type": "boolean",
                        "default": False,
                        "description": "Enable anti-detection stealth mode",
                    },
                    "eval_js": {
                        "type": "string",
                        "default": "",
                        "description": "JavaScript expression to evaluate on the page",
                    },
                },
                "required": ["url"],
            },
            handler=_obscura_fetch_cli,
        ),
        Tool(
            name="web_scrape",
            description=(
                "Batch scrape multiple URLs using headless browser workers. "
                "Outputs JSON with timing and per-page results."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of URLs to scrape",
                    },
                    "concurrency": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "description": "Number of parallel workers",
                    },
                    "timeout": {
                        "type": "integer",
                        "default": 30,
                        "minimum": 1,
                        "description": "Per-page timeout in seconds",
                    },
                    "eval_js": {
                        "type": "string",
                        "default": "",
                        "description": "JS expression to evaluate on each page",
                    },
                },
                "required": ["urls"],
            },
            handler=_obscura_scrape_cli,
        ),
    ]
