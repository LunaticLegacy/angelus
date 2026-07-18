"""Internet search and headless-browser tools exposed to an Agent."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        ``OBSCURA_BIN`` when configured, otherwise ``obscura`` from ``PATH``.
    """
    return os.environ.get("OBSCURA_BIN", "obscura")


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
    "providers": ["duckduckgo"],
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
        allowed = {"duckduckgo", "brave", "bing"}
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
        # Some deployments cannot reach DDG through Python's HTTP stack but can
        # reach it through the system proxy configured for curl.
        if os.environ.get("WEB_SEARCH_TRANSPORT", "curl") == "curl":
            completed = subprocess.run(
                ["curl", "-L", "--compressed", "--max-time", str(timeout), "-A", user_agent, url],
                capture_output=True,
                text=True,
                check=True,
            )
            document = BeautifulSoup(completed.stdout, "html.parser")
        else:
            import requests
            response = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
            response.raise_for_status()
            document = BeautifulSoup(response.text, "html.parser")

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
    """Search configured web providers, record usage, and deduplicate results.

    Args:
        **kwargs: Tool arguments containing ``query`` and optional result limit.

    Returns:
        Normalized result payload with provider attempt metadata.
    """
    query = str(kwargs.get("query", "")).strip()
    store = get_web_search_store()
    settings = store.get_settings()
    max_results = max(1, min(int(kwargs.get("max_results", settings["max_results"])), 10))
    if not query:
        return {"ok": False, "error": "query is required", "results": []}

    attempts = []
    payloads = {}
    providers = settings["providers"]
    if settings["mode"] == "parallel" and len(providers) > 1:
        with ThreadPoolExecutor(max_workers=len(providers)) as executor:
            futures = {executor.submit(_search_provider, provider, query, max_results, settings["timeout" ]): provider for provider in providers}
            for future in as_completed(futures):
                provider = futures[future]
                started = time.perf_counter()
                try:
                    payload = future.result()
                    error = ""
                except Exception as exc:
                    payload = {"ok": False, "provider": provider, "results": [], "error": str(exc)}
                    error = str(exc)
                duration = int((time.perf_counter() - started) * 1000)
                payloads[provider] = payload
                store.record(provider, bool(payload.get("ok")), len(payload.get("results", [])), duration)
                attempts.append({"provider": provider, "ok": bool(payload.get("ok")), "error": error or payload.get("error", ""), "duration_ms": duration})
    else:
        for provider in providers:
            started = time.perf_counter()
            try:
                payload = _search_provider(provider, query, max_results, settings["timeout"])
                error = ""
            except Exception as exc:
                payload = {"ok": False, "provider": provider, "results": [], "error": str(exc)}
                error = str(exc)
            duration = int((time.perf_counter() - started) * 1000)
            payloads[provider] = payload
            store.record(provider, bool(payload.get("ok")), len(payload.get("results", [])), duration)
            attempts.append({"provider": provider, "ok": bool(payload.get("ok")), "error": error or payload.get("error", ""), "duration_ms": duration})
            if payload.get("ok") and settings["mode"] == "fallback":
                break

    merged = []
    seen = set()
    for attempt in attempts:
        if not attempt["ok"]:
            continue
        provider_payload = payloads.get(attempt["provider"])
        for item in (provider_payload or {}).get("results", []):
            if item.get("url") in seen:
                continue
            seen.add(item.get("url"))
            merged.append({**item, "provider": attempt["provider"]})
    return {"ok": bool(merged), "query": query, "providers": attempts, "results": merged[:max_results], "error": "" if merged else "all providers failed"}


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

    return {
        "url": url,
        "mode": mode,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": result.returncode == 0,
    }


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
                "Search the live public web for current sources. Returns result titles, "
                "direct URLs, and snippets. Use this before web_fetch when the source URL "
                "is not already known."
            ),
            schemas=ToolSchema(
                properties=[
                    ToolParameter(name="query", type="string", description="Web search query", required=True),
                    ToolParameter(name="max_results", type="integer", default=5, description="Maximum results (1-10)", required=False),
                ],
            ),
            handler=_web_search,
        ),
        Tool(
            name="web_fetch",
            description=(
                "Fetch a single webpage using a headless browser and extract content. "
                "Supports html/text/links output modes, CSS selectors, JavaScript evaluation, "
                "and stealth mode. Use it to inspect primary sources returned by web_search."
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
