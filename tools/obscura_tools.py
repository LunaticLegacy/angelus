"""Internet search and headless-browser tools exposed to an Agent."""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, quote_plus, urlparse

from ..llm_types import Tool, ToolSchema, ToolParameter


# ---------------------------------------------------------------------------
# CLI 模式
# ---------------------------------------------------------------------------

def _get_obscura_bin() -> str:
    """Resolve the configured Obscura executable.

    Returns:
        Explicit ``OBSCURA_BIN``, a product-local bundled executable, or
        ``obscura`` from ``PATH`` in that order.
    """
    explicit = os.environ.get("OBSCURA_BIN")
    if explicit:
        return explicit
    project_root = Path(__file__).resolve().parents[3]
    platform_name = {
        ("linux", "x86_64"): "linux-x86_64",
        ("linux", "aarch64"): "linux-aarch64",
        ("darwin", "x86_64"): "macos-x86_64",
        ("darwin", "arm64"): "macos-aarch64",
        ("win32", "AMD64"): "windows-x86_64",
    }.get((sys.platform, platform.machine()), "")
    if platform_name:
        bundled = project_root / "vendor" / "obscura" / platform_name / ("obscura.exe" if sys.platform == "win32" else "obscura")
        if bundled.is_file():
            return str(bundled)
    return "obscura"


def _unwrap_search_url(href: str) -> str:
    """Extract a destination URL from a DuckDuckGo redirect link.

    Args:
        href: Search-result anchor URL.

    Returns:
        Direct destination URL when a redirect parameter is present, otherwise
        the original URL.
    """
    parsed = urlparse(href)
    redirect_target = parse_qs(parsed.query).get("uddg", [])
    return redirect_target[0] if redirect_target else href


_DEFAULT_SEARCH_SETTINGS = {
    "providers": ["baidu", "bing_html", "duckduckgo"],
    "mode": "fallback",
    "max_results": 5,
    "timeout": 20,
    "brave_api_key": "",
    "bing_api_key": "",
}
_SEARCH_STORE: "WebSearchStore | None" = None


class WebSearchStore:
    """Persist web-search settings and per-provider usage counters in SQLite.

    Args:
        path: SQLite database path shared with the Agent control plane.
        defaults: Initial settings used only when no saved settings exist.
    """

    def __init__(self, path: str | Path, defaults: dict[str, Any] | None = None) -> None:
        """Open or initialize the persistent search settings store.

        Args:
            path: SQLite database path shared with the Agent control plane.
            defaults: Initial settings used when no saved settings exist.

        Returns:
            None.
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.defaults = {**_DEFAULT_SEARCH_SETTINGS, **(defaults or {})}
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        """Open a short-lived WAL connection for a thread-safe operation."""
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _migrate(self) -> None:
        """Create settings and usage tables without disturbing Agent data."""
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS web_search_settings "
                "(id INTEGER PRIMARY KEY CHECK (id = 1), settings_json TEXT NOT NULL, updated_at REAL NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS web_search_usage "
                "(provider TEXT NOT NULL, day TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0, "
                "successes INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0, "
                "results INTEGER NOT NULL DEFAULT 0, duration_ms INTEGER NOT NULL DEFAULT 0, "
                "PRIMARY KEY(provider, day))"
            )

    def get_settings(self) -> dict[str, Any]:
        """Return saved search settings merged with safe defaults."""
        with self._connect() as connection:
            row = connection.execute("SELECT settings_json FROM web_search_settings WHERE id = 1").fetchone()
        saved = json.loads(row["settings_json"]) if row else {}
        return {**self.defaults, **saved}

    def update_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        """Validate, persist, and return web-search settings."""
        current = self.get_settings()
        providers = [str(item) for item in values.get("providers", current["providers"])]
        allowed = {"baidu", "bing_html", "duckduckgo", "brave", "bing"}
        providers = [item for item in providers if item in allowed]
        if not providers:
            raise ValueError("至少启用一个搜索 Provider")
        merged = {
            **current,
            **values,
            "providers": providers,
            "mode": "parallel" if values.get("mode") == "parallel" else "fallback",
            "max_results": max(1, min(int(values.get("max_results", current["max_results"])), 10)),
            "timeout": max(3, min(int(values.get("timeout", current["timeout"])), 60)),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO web_search_settings(id, settings_json, updated_at) VALUES(1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET settings_json=excluded.settings_json, updated_at=excluded.updated_at",
                (json.dumps(merged, ensure_ascii=False), time.time()),
            )
        return merged

    def record(self, provider: str, ok: bool, result_count: int, duration_ms: int) -> None:
        """Add one provider attempt to today's durable usage aggregate."""
        day = time.strftime("%Y-%m-%d", time.localtime())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO web_search_usage(provider, day, calls, successes, failures, results, duration_ms) "
                "VALUES (?, ?, 1, ?, ?, ?, ?) ON CONFLICT(provider, day) DO UPDATE SET "
                "calls=calls+1, successes=successes+excluded.successes, failures=failures+excluded.failures, "
                "results=results+excluded.results, duration_ms=duration_ms+excluded.duration_ms",
                (provider, day, int(ok), int(not ok), result_count, duration_ms),
            )

    def usage(self, days: int = 30) -> list[dict[str, Any]]:
        """Return provider usage totals for the requested recent day window."""
        cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - max(1, days) * 86400))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT provider, SUM(calls) calls, SUM(successes) successes, SUM(failures) failures, "
                "SUM(results) results, SUM(duration_ms) duration_ms FROM web_search_usage WHERE day >= ? "
                "GROUP BY provider ORDER BY calls DESC, provider", (cutoff,)
            ).fetchall()
        return [dict(row) for row in rows]


def configure_web_search_store(path: str | Path, defaults: dict[str, Any] | None = None) -> None:
    """Configure the process-wide persistent store used by new search tools."""
    global _SEARCH_STORE
    _SEARCH_STORE = WebSearchStore(path, defaults)


def get_web_search_store() -> WebSearchStore:
    """Return the configured store, lazily defaulting to the local runtime DB."""
    global _SEARCH_STORE
    if _SEARCH_STORE is None:
        _SEARCH_STORE = WebSearchStore(Path(".runtime") / "agent_console.sqlite3")
    return _SEARCH_STORE


def _search_duckduckgo(query: str, max_results: int, timeout: int) -> dict[str, Any]:
    """Search DuckDuckGo's HTML endpoint and normalize organic results.

    Args:
        query: Search phrase.
        max_results: Maximum number of organic results.
        timeout: HTTP request timeout in seconds.

    Returns:
        Search provider metadata and a list of title, URL, and snippet
        dictionaries. Failures are returned as ``ok=False`` payloads.
    """
    try:
        from bs4 import BeautifulSoup

        url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
        user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        document, transport_error = _curl_document(url, timeout, user_agent)
        if document is None:
            return {"ok": False, "provider": "duckduckgo", "query": query, "results": [], "error": transport_error}

        # Keep only organic result blocks and expose direct source URLs.
        results = []
        for result_node in document.select(".result"):
            anchor = result_node.select_one(".result__a")
            if anchor is None or not anchor.get("href"):
                continue
            raw_url = str(anchor["href"])
            parsed_url = urlparse(raw_url)
            if parsed_url.path.endswith("/y.js") or "ad_provider" in parsed_url.query:
                continue
            snippet_node = result_node.select_one(".result__snippet")
            results.append({
                "title": anchor.get_text(" ", strip=True),
                "url": _unwrap_search_url(raw_url),
                "snippet": snippet_node.get_text(" ", strip=True) if snippet_node else "",
            })
            if len(results) >= max_results:
                break
        return {
            "ok": bool(results),
            "provider": "duckduckgo",
            "query": query,
            "results": results,
            "error": "" if results else "search returned no parseable results",
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": "duckduckgo",
            "query": query,
            "results": [],
            "error": str(exc),
        }


def _curl_document(url: str, timeout: int, user_agent: str) -> tuple[Any | None, str]:
    """Fetch one HTML document with bounded curl diagnostics.

    Args:
        url: Public HTTP(S) search endpoint.
        timeout: Total curl timeout in seconds.
        user_agent: Browser-like user-agent header.

    Returns:
        A BeautifulSoup document and an empty error, or ``None`` with a
        diagnostic containing curl's exit status and stderr.
    """
    from bs4 import BeautifulSoup

    completed = subprocess.run(
        [
            "curl", "-L", "--compressed", "--connect-timeout", str(min(5, timeout)),
            "--max-time", str(timeout), "-A", user_agent, url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "no stderr"
        return None, f"curl exit status {completed.returncode}: {detail}"
    return BeautifulSoup(completed.stdout, "html.parser"), ""


def _search_baidu(query: str, max_results: int, timeout: int) -> dict[str, Any]:
    """Search Baidu's public HTML endpoint for domestic-first retrieval."""
    from urllib.parse import quote_plus

    url = "https://www.baidu.com/s?wd=" + quote_plus(query)
    document, error = _curl_document(url, timeout, "Mozilla/5.0")
    if document is None:
        return {"ok": False, "provider": "baidu", "query": query, "results": [], "error": error}
    results = []
    for node in document.select("div.result, div.c-container"):
        anchor = node.select_one("h3 a, h3 a[href]")
        if anchor is None or not anchor.get("href"):
            continue
        snippet = node.select_one(".c-span-last, .c-color-text, .c-abstract")
        results.append({
            "title": anchor.get_text(" ", strip=True),
            "url": _unwrap_search_url(str(anchor["href"])),
            "snippet": snippet.get_text(" ", strip=True) if snippet else "",
        })
        if len(results) >= max_results:
            break
    return {"ok": bool(results), "provider": "baidu", "query": query, "results": results, "error": "" if results else "search returned no parseable results"}


def _search_bing_html(query: str, max_results: int, timeout: int) -> dict[str, Any]:
    """Search Bing's public HTML endpoint without requiring an API key."""
    from urllib.parse import quote_plus

    url = "https://cn.bing.com/search?q=" + quote_plus(query)
    document, error = _curl_document(url, timeout, "Mozilla/5.0")
    if document is None:
        return {"ok": False, "provider": "bing_html", "query": query, "results": [], "error": error}
    results = []
    for node in document.select("li.b_algo"):
        anchor = node.select_one("h2 a[href]")
        if anchor is None:
            continue
        snippet = node.select_one(".b_caption p")
        results.append({
            "title": anchor.get_text(" ", strip=True),
            "url": str(anchor["href"]),
            "snippet": snippet.get_text(" ", strip=True) if snippet else "",
        })
        if len(results) >= max_results:
            break
    return {"ok": bool(results), "provider": "bing_html", "query": query, "results": results, "error": "" if results else "search returned no parseable results"}


def _search_brave(query: str, max_results: int, timeout: int, api_key: str) -> dict[str, Any]:
    """Search Brave's JSON API using the configured subscription token."""
    import requests
    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": max_results},
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        timeout=timeout,
    )
    response.raise_for_status()
    items = response.json().get("web", {}).get("results", [])
    return {"ok": bool(items), "provider": "brave", "query": query, "results": [
        {"title": item.get("title", ""), "url": item.get("url", ""), "snippet": item.get("description", "")}
        for item in items[:max_results]
    ], "error": "" if items else "search returned no results"}


def _search_bing(query: str, max_results: int, timeout: int, api_key: str) -> dict[str, Any]:
    """Search Bing Web Search API using the configured subscription key."""
    import requests
    response = requests.get(
        "https://api.bing.microsoft.com/v7.0/search",
        params={"q": query, "count": max_results, "responseFilter": "Webpages"},
        headers={"Ocp-Apim-Subscription-Key": api_key},
        timeout=timeout,
    )
    response.raise_for_status()
    items = response.json().get("webPages", {}).get("value", [])
    return {"ok": bool(items), "provider": "bing", "query": query, "results": [
        {"title": item.get("name", ""), "url": item.get("url", ""), "snippet": item.get("snippet", "")}
        for item in items[:max_results]
    ], "error": "" if items else "search returned no results"}


def _search_provider(provider: str, query: str, max_results: int, timeout: int, settings: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one configured provider and return its normalized payload."""
    if provider == "baidu":
        return _search_baidu(query, max_results, timeout)
    if provider == "bing_html":
        return _search_bing_html(query, max_results, timeout)
    if provider == "duckduckgo":
        return _search_duckduckgo(query, max_results, timeout)
    if provider == "brave":
        if not settings.get("brave_api_key"):
            raise ValueError("Brave API key is not configured")
        return _search_brave(query, max_results, timeout, settings["brave_api_key"])
    if provider == "bing":
        if not settings.get("bing_api_key"):
            raise ValueError("Bing API key is not configured")
        return _search_bing(query, max_results, timeout, settings["bing_api_key"])
    raise ValueError(f"Unsupported search provider: {provider}")


def _web_search(**kwargs: Any) -> dict[str, Any]:
    """Search domestic-first providers through curl with bounded fallback.

    Args:
        **kwargs: Tool arguments containing ``query`` and optional result limit.

    Returns:
        Normalized result payload with provider attempt metadata.
    """
    query = str(kwargs.get("query", "")).strip()
    max_results = max(1, min(int(kwargs.get("max_results", 5)), 10))
    timeout = max(3, min(int(kwargs.get("timeout", 20)), 60))
    if not query:
        return {"ok": False, "error": "query is required", "results": []}
    settings = get_web_search_store().get_settings()
    providers = ["baidu", "bing_html", "duckduckgo"]
    attempts = []
    per_provider_timeout = max(3, timeout // len(providers))
    for provider in providers:
        started = time.perf_counter()
        try:
            payload = _search_provider(provider, query, max_results, per_provider_timeout, settings)
        except Exception as exc:
            payload = {"ok": False, "provider": provider, "query": query, "results": [], "error": str(exc)}
        duration = int((time.perf_counter() - started) * 1000)
        result_count = len(payload.get("results", []))
        get_web_search_store().record(provider, bool(payload.get("ok")), result_count, duration)
        attempts.append({"provider": provider, "ok": bool(payload.get("ok")), "duration_ms": duration, "error": payload.get("error", "")})
        if payload.get("ok"):
            return {"ok": True, "query": query, "transport": "curl", "provider": provider, "duration_ms": sum(item["duration_ms"] for item in attempts), "results": payload["results"], "attempts": attempts, "error": ""}
    return {"ok": False, "query": query, "transport": "curl", "duration_ms": sum(item["duration_ms"] for item in attempts), "results": [], "attempts": attempts, "error": "all search providers failed"}


def _obscura_fetch_cli(**kwargs: Any) -> dict[str, Any]:
    """Execute obscura fetch via CLI.

    Args:
        **kwargs: Tool arguments containing URL, extraction mode, selector,
            wait policy, stealth flag, and optional JavaScript expression.

    Returns:
        Obscura exit status and captured page output.
    """
    url = str(kwargs["url"])
    mode = str(kwargs.get("mode", "text"))
    selector = str(kwargs.get("selector", ""))
    wait = max(0, min(int(kwargs.get("wait", 3)), 30))
    wait_until = str(kwargs.get("wait_until", "load"))
    stealth = bool(kwargs.get("stealth", False))
    eval_js = str(kwargs.get("eval_js", ""))
    include_images = bool(kwargs.get("include_images", True))
    requested_mode = mode
    if include_images and mode == "text":
        mode = "html"

    cmd_parts = [
        _get_obscura_bin(),
        "fetch",
        url,
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

    result = subprocess.run(
        cmd_parts,
        capture_output=True,
        text=True,
        timeout=wait + 15,  # hard ceiling
    )

    payload = {
        "url": url,
        "mode": requested_mode,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": result.returncode == 0,
    }
    if include_images and result.returncode == 0:
        try:
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin
            document = BeautifulSoup(result.stdout, "html.parser")
            images = [
                {"url": urljoin(url, str(node.get("src") or node.get("data-src"))), "alt": node.get("alt", "")}
                for node in document.select("img[src], img[data-src]")
                if node.get("src") or node.get("data-src")
            ]
            payload["images"] = images[:20]
            if requested_mode == "text":
                payload["stdout"] = document.get_text(" ", strip=True)
        except Exception as exc:
            payload["images_error"] = str(exc)
    return payload


def _obscura_scrape_cli(**kwargs: Any) -> dict[str, Any]:
    """Batch-scrape URLs with Obscura workers.

    Args:
        **kwargs: Tool arguments containing URL list, concurrency, timeout,
            and optional JavaScript expression.

    Returns:
        Obscura exit status plus parsed and raw JSON output.
    """
    urls = kwargs.get("urls", [])
    if isinstance(urls, str):
        urls = [urls]
    urls = [str(url) for url in urls]
    concurrency = max(1, min(int(kwargs.get("concurrency", 5)), 12))
    timeout = max(1, min(int(kwargs.get("timeout", 30)), 120))
    eval_js = str(kwargs.get("eval_js", ""))

    cmd_parts = [
        _get_obscura_bin(),
        "scrape",
        "--concurrency", str(concurrency),
        "--timeout", str(timeout),
        "--format", "json",
    ]
    if eval_js:
        cmd_parts.extend(["-e", eval_js])
    cmd_parts.extend(urls)

    result = subprocess.run(
        cmd_parts,
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
    """Placeholder configuration for a future Obscura CDP client."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9222) -> None:
        """Store the future CDP endpoint coordinates.

        Args:
            host: Obscura CDP service host.
            port: Obscura CDP service port.

        Returns:
            None.
        """
        self._host = host
        self._port = port
        self._ws_url: Optional[str] = None

    # TODO: implement CDP session management (Page.navigate, Runtime.evaluate, DOM.querySelector, etc.)


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------

def create_obscura_tools() -> list[Tool]:
    """Create Agent-ready web search and browsing tools.

    Returns:
        Tools for public web search, single-page reading, and batch scraping.
    """
    return [
        Tool(
            name="web_search",
            description=(
                "Search the live public web through the local curl command. Returns only "
                "URLs extracted from DuckDuckGo HTML; use web_fetch to verify every source "
                "before citing it."
            ),
            schemas=ToolSchema(
                properties=[
                    ToolParameter(name="query", type="string", description="Web search query", required=True),
                    ToolParameter(name="max_results", type="integer", default=5, description="Maximum results (1-10)", required=False),
                    ToolParameter(name="timeout", type="integer", default=20, description="curl timeout in seconds (3-60)", required=False),
                ],
            ),
            handler=_web_search,
        ),
        Tool(
            name="web_fetch",
            description=(
                "Fetch a single webpage using a headless browser and extract content. "
                "Supports html/text/links output modes, CSS selectors, JavaScript evaluation, "
                "and stealth mode. It also returns bounded image URLs for visual inspection. "
                "Use it to inspect primary sources returned by web_search."
            ),
            schemas=ToolSchema(
                properties=[
                    ToolParameter(name="url", type="string", description="Target URL to fetch", required=True),
                    ToolParameter(name="mode", type="string", enum=["html", "text", "links"], default="text", description="Output extraction mode", required=False),
                    ToolParameter(name="selector", type="string", default="", description="CSS selector to extract specific elements only", required=False),
                    ToolParameter(name="wait", type="integer", default=3, description="Seconds to wait after initial page load", required=False),
                    ToolParameter(name="wait_until", type="string", enum=["load", "domcontentloaded", "networkidle"], default="load", description="Page event to wait for before extraction", required=False),
                    ToolParameter(name="stealth", type="boolean", default=False, description="Enable anti-detection stealth mode", required=False),
                    ToolParameter(name="eval_js", type="string", default="", description="JavaScript expression to evaluate on the page", required=False),
                    ToolParameter(name="include_images", type="boolean", default=True, description="Extract image URLs from the page for analyze_image", required=False),
                ],
            ),
            handler=_obscura_fetch_cli,
        ),
        Tool(
            name="web_scrape",
            description=(
                "Batch scrape multiple URLs using headless browser workers. "
                "Outputs JSON with timing and per-page results."
            ),
            schemas=ToolSchema(
                properties=[
                    ToolParameter(name="urls", type="array", description="List of URLs to scrape", required=True),
                    ToolParameter(name="concurrency", type="integer", default=5, description="Number of parallel workers", required=False),
                    ToolParameter(name="timeout", type="integer", default=30, description="Per-page timeout in seconds", required=False),
                    ToolParameter(name="eval_js", type="string", default="", description="JS expression to evaluate on each page", required=False),
                ],
            ),
            handler=_obscura_scrape_cli,
        ),
    ]
