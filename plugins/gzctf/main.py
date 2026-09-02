"""GZCTF Helper plugin — GZCTF 比赛平台工具集。

注册八个工具（运行时完整名为 ``plugin.gzctf.gzctf_*``，manager 自动加
``plugin.<name>.`` 前缀）：

* ``gzctf_login``        —— 登录并持久化 Cookie，返回比赛/队伍信息
* ``gzctf_status``       —— 检查本地 Cookie 与登录态
* ``gzctf_team``         —— 拉取当前队伍信息（分数/排名/已解）
* ``gzctf_challenges``   —— 拉取题目列表（可按分类/关键词过滤）
* ``gzctf_challenge_info`` —— 拉取单题详情（描述/附件/连接提示）
* ``gzctf_submit_flag``  —— 提交 flag 并轮询判题结果
* ``gzctf_download``     —— 用已登录 Cookie 会话下载题目附件到插件私有目录
* ``gzctf_start_instance`` —— 启动动态题目实例（/instance 优先，404/405 回退 /container）

API 协议参考 ElfCTF_POFP 的 ``services/gzctf_service.py`` 与
``core/gzctf/module/automation.py``：

* 认证：Cookie 会话（``POST /api/account/login`` → ``GET /api/account/profile``），
  题目与提交接口共用同一 Cookie；Cookie 持久化在插件私有 ``state_dir``。
* 加密：当 ``GET /api/config`` 暴露 ``publicKey`` 时，password / flag 使用
  GZCTF 前端同款 X25519 + AES-GCM 方案加密（惰性依赖 ``cryptography``，
  未启用加密的实例完全不依赖它）。
* 判题：``POST /api/game/{id}/challenges/{cid}``（404/405 时回退
  ``.../{cid}/submit``）→ ``GET .../challenges/{cid}/status/{sid}`` 轮询。

HTTP 层仅使用标准库 ``urllib``，不引入 requests/httpx。网络请求由宿主在
授予 ``network``/``http`` 权限后放行（见 manifest.permissions 与
``docs/security.md`` 权限门）。
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from angelus.modules.plugin_module import (
    PluginRuntime,
    PluginToolCategory,
    PluginToolContribution,
    PluginToolDefinition,
    PluginUiActionRequest,
    PluginUiActionResult,
)
from angelus.modules.tool_module import ToolPolicy
from llmfetcher import Tool, ToolParameter, ToolSchema
from .automation import AutomationRunStore

USER_AGENT = "Angelus-gzctf-plugin/1.0.0"
TIMEOUT = 20
COOKIE_FILE = "cookies.txt"
TERMINAL_VERDICTS = {"accepted", "rejected"}


# ---------------------------------------------------------------------------
# minimal cookie-aware HTTP session (stdlib only)
# ---------------------------------------------------------------------------
class _GzctfSession:
    """Minimal cookie-aware HTTP session built on urllib + MozillaCookieJar."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.cookie_path = self.state_dir / COOKIE_FILE
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        self._jar = MozillaCookieJar(str(self.cookie_path))
        if self.cookie_path.is_file():
            try:
                self._jar.load(ignore_discard=True, ignore_expires=True)
            except Exception:
                pass
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar)
        )

    def request(
        self,
        method: str,
        url: str,
        json_body: Any = None,
        timeout: float = TIMEOUT,
    ) -> Tuple[int, bytes]:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        data = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            url, data=data, headers=headers, method=method.upper()
        )
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:  # 4xx/5xx carry a body
            return exc.code, exc.read()

    def has_cookies(self) -> bool:
        return len(self._jar) > 0

    def save(self) -> None:
        try:
            self._jar.save(ignore_discard=True, ignore_expires=True)
        except OSError:
            pass

    def clear(self) -> None:
        self._jar.clear()
        try:
            if self.cookie_path.is_file():
                self.cookie_path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# HTTP / JSON helpers
# ---------------------------------------------------------------------------
def _json_of(body: bytes) -> Any:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _error_detail(body: bytes) -> str:
    payload = _json_of(body)
    if isinstance(payload, dict):
        for key in ("title", "message", "detail", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return json.dumps(payload, ensure_ascii=False)[:500]
    text = body.decode("utf-8", errors="replace").strip()
    return text[:500] if text else ""


def _raise(status: int, body: bytes, prefix: str) -> None:
    """Raise a readable error preserving server-side context (>=400)."""
    if status < 400:
        return
    detail = _error_detail(body)
    raise RuntimeError(f"{prefix}: HTTP {status} {detail}".strip())


def _parse_int(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if not text or not text.isdigit():
        return None
    return int(text)


def _normalize_label(value: str) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").strip().lower())


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)
    elif value is not None:
        yield str(value)


# ---------------------------------------------------------------------------
# GZCTF API primitives（协议与 ElfCTF_POFP/services/gzctf_service.py 对齐）
# ---------------------------------------------------------------------------
def parse_game_url(game_url: str) -> Tuple[str, Optional[int]]:
    """推断部署 base URL 与可选 gameId（``/games/{id}``）。"""
    parsed = urllib.parse.urlparse(str(game_url).strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("GZCTF 比赛链接无效")
    base_url = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    match = re.search(r"/games/(\d+)", parsed.path)
    game_id = int(match.group(1)) if match else None
    return base_url, game_id


def fetch_public_key(session: _GzctfSession, base_url: str) -> Optional[str]:
    """读取 ``/api/config`` 并提取可选的 API 加密公钥。"""
    status, body = session.request("GET", f"{base_url}/api/config")
    _raise(status, body, "读取 GZCTF 配置失败")
    return find_public_key(_json_of(body))


def find_public_key(obj: Any) -> Optional[str]:
    """在 JSON 中递归寻找 GZCTF API 加密公钥。"""
    if isinstance(obj, dict):
        for key in ("publicKey", "apiPublicKey", "apiEncryptionPublicKey"):
            value = obj.get(key)
            if isinstance(value, str) and value:
                return value
        for value in obj.values():
            found = find_public_key(value)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_public_key(item)
            if found:
                return found
    return None


def encrypt_api_data(plain_text: str, public_key_b64: Optional[str]) -> str:
    """用 GZCTF 前端兼容方案（X25519 + AES-GCM）加密一个 API 字段。

    无公钥时原样返回；``cryptography`` 为惰性依赖，仅加密场景需要。
    """
    if not public_key_b64:
        return plain_text
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import x25519
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "GZCTF 实例启用了 API 加密，但当前环境缺少 cryptography 依赖"
        ) from exc

    server_public_bytes = base64.b64decode(public_key_b64)
    if len(server_public_bytes) != 32:
        raise ValueError("Invalid X25519 public key length")
    server_public_key = x25519.X25519PublicKey.from_public_bytes(
        server_public_bytes
    )

    ephemeral_private_key = x25519.X25519PrivateKey.generate()
    ephemeral_public_key = ephemeral_private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    shared_secret = ephemeral_private_key.exchange(server_public_key)

    digest = hashes.Hash(hashes.SHA256())
    digest.update(shared_secret)
    aes_key = digest.finalize()

    nonce = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(nonce, plain_text.encode("utf-8"), None)
    packed = ephemeral_public_key + nonce + ciphertext
    return base64.b64encode(packed).decode("ascii")


def verify_profile(session: _GzctfSession, base_url: str) -> dict:
    """确认当前 Cookie 属于已登录用户。"""
    status, body = session.request("GET", f"{base_url}/api/account/profile")
    _raise(status, body, "GZCTF 账号校验失败")
    payload = _json_of(body)
    return payload if isinstance(payload, dict) else {}


def perform_login(
    session: _GzctfSession, base_url: str, username: str, password: str
) -> dict:
    """登录 GZCTF，返回 profile（失败抛 RuntimeError）。"""
    public_key = fetch_public_key(session, base_url)
    payload = {
        "userName": username,
        "password": encrypt_api_data(password, public_key),
    }
    status, body = session.request(
        "POST", f"{base_url}/api/account/login", json_body=payload
    )
    _raise(status, body, "GZCTF 登录失败")
    return verify_profile(session, base_url)


def fetch_game_details(
    session: _GzctfSession, base_url: str, game_id: int
) -> dict:
    """拉取比赛参与详情（含题目元数据与队伍排名）。"""
    status, body = session.request(
        "GET", f"{base_url}/api/game/{game_id}/details"
    )
    _raise(status, body, "读取 GZCTF 比赛详情失败")
    payload = _json_of(body)
    return payload if isinstance(payload, dict) else {}


def extract_team_info(game_details: dict) -> Optional[dict]:
    """从比赛详情中提取前端可展示的队伍摘要。"""
    rank = game_details.get("rank")
    if not isinstance(rank, dict):
        return None
    return {
        "id": _parse_int(rank.get("id")),
        "name": str(rank.get("name") or "").strip(),
        "score": rank.get("score"),
        "rank": rank.get("rank"),
        "solvedCount": rank.get("solvedCount"),
    }


# ---------------------------------------------------------------------------
# challenge metadata helpers
# ---------------------------------------------------------------------------
def list_challenge_candidates(game_details: dict) -> List[dict]:
    """把 game details 中嵌套的题目负载展平为 challenge-like dict 列表。"""
    dest: List[dict] = []
    _collect_challenge_candidates(game_details.get("challenges"), dest)
    return dest


def _collect_challenge_candidates(value: Any, dest: List[dict]) -> None:
    if isinstance(value, list):
        for item in value:
            _collect_challenge_candidates(item, dest)
        return
    if not isinstance(value, dict):
        return
    if any(key in value for key in ("id", "gameChallengeId", "challengeId")) and any(
        key in value for key in ("title", "name", "slug", "tag")
    ):
        dest.append(value)
        return
    for item in value.values():
        _collect_challenge_candidates(item, dest)


def _challenge_identifier(challenge: dict) -> str:
    for key in ("id", "gameChallengeId", "challengeId"):
        value = str(challenge.get(key) or "").strip()
        if value:
            return value
    return ""


def _challenge_title(challenge: dict) -> str:
    for key in ("title", "name", "slug", "tag"):
        value = str(challenge.get(key) or "").strip()
        if value:
            return value
    return f"challenge-{_challenge_identifier(challenge) or 'unknown'}"


def _challenge_category(challenge: dict) -> str:
    for key in ("category", "type", "topic", "group"):
        value = challenge.get(key)
        if isinstance(value, dict):
            for nested in ("name", "title", "type"):
                text = str(value.get(nested) or "").strip()
                if text:
                    return text
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _clean_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", str(text or ""))
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def _challenge_labels(item: dict) -> List[str]:
    labels: List[str] = []
    for key in ("title", "name", "slug", "tag"):
        value = str(item.get(key) or "").strip()
        if value and value not in labels:
            labels.append(value)
    return labels


def _match_challenge_id(item: dict, expected: int) -> bool:
    for key in ("id", "gameChallengeId", "challengeId"):
        value = _parse_int(item.get(key))
        if value == expected:
            return True
    return False


def resolve_challenge(
    game_details: dict, challenge_id: str = "", title: str = ""
) -> Optional[dict]:
    """按显式 id 或标题模糊匹配题目。"""
    challenge_id = str(challenge_id or "").strip()
    title = str(title or "").strip()
    if not challenge_id and not title:
        return None
    candidates = list_challenge_candidates(game_details)
    if challenge_id.isdigit():
        expected = int(challenge_id)
        for item in candidates:
            if _match_challenge_id(item, expected):
                return item
    if challenge_id:
        normalized = _normalize_label(challenge_id)
        for item in candidates:
            for key in ("id", "gameChallengeId", "challengeId"):
                value = str(item.get(key) or "")
                if value and _normalize_label(value) == normalized:
                    return item
    if title:
        labels = {_normalize_label(title)}
        exact = fuzzy = None
        for item in candidates:
            for candidate in _challenge_labels(item):
                normalized = _normalize_label(candidate)
                if not normalized:
                    continue
                if normalized in labels:
                    exact = item
                    break
                if any(label in normalized or normalized in label for label in labels):
                    fuzzy = fuzzy or item
            if exact is not None:
                break
        return exact or fuzzy
    return None


def fetch_challenge_detail(
    session: _GzctfSession, base_url: str, game_id: int, challenge_id: int
) -> dict:
    """合并题目详情/实例负载（对缺失端点做容忍）。"""
    merged: dict = {}
    for path in (
        f"/api/game/{game_id}/challenges/{challenge_id}",
        f"/api/game/{game_id}/challenges/{challenge_id}/detail",
        f"/api/game/{game_id}/challenges/{challenge_id}/details",
        f"/api/game/{game_id}/challenges/{challenge_id}/instance",
        f"/api/game/{game_id}/challenges/{challenge_id}/container",
    ):
        status, body = session.request("GET", f"{base_url}{path}")
        if status >= 400:
            continue
        payload = _json_of(body)
        if isinstance(payload, dict):
            merged = _merge_dicts(merged, payload)
    return merged


def _merge_dicts(base: dict, overlay: dict) -> dict:
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def _collect_attachments(challenge: dict, base_url: str) -> List[dict]:
    """收集嵌套负载中的可下载附件 URL。"""
    specs: List[dict] = []
    seen: set = set()

    def add_spec(url: str, name: str = "") -> None:
        normalized = urllib.parse.urljoin(base_url + "/", url)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        safe = (
            str(name or Path(urllib.parse.urlparse(normalized).path).name)
            or f"attachment_{len(specs) + 1}"
        )
        specs.append({"name": safe, "url": normalized})

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            url_value = None
            for key in (
                "url", "href", "src", "downloadUrl", "download_url",
                "fileUrl", "file_url", "link",
            ):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    url_value = candidate.strip()
                    break
            if url_value and _looks_like_download_url(url_value):
                name = str(
                    value.get("name") or value.get("fileName")
                    or value.get("filename") or value.get("title") or ""
                )
                add_spec(url_value, name)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            for url in re.findall(
                r"https?://[^\s'\"<>]+|/api/[^\s'\"<>]+|/files/[^\s'\"<>]+|/assets/[^\s'\"<>]+",
                value,
            ):
                if _looks_like_download_url(url):
                    add_spec(url)

    walk(challenge)
    return specs


def _looks_like_download_url(url: str) -> bool:
    lowered = url.lower()
    if any(
        token in lowered
        for token in ("/files/", "/assets/", "/download", "/attachment", "/api/edit/files")
    ):
        return True
    filename = Path(urllib.parse.urlparse(url).path).name.lower()
    return "." in filename and len(filename.split(".")[-1]) <= 8


def _collect_connection_hints(challenge: dict) -> List[str]:
    """收集 service/instance/container 等连接提示（含 nc host port 文本）。"""
    hints: List[str] = []
    seen: set = set()

    def add(line: str) -> None:
        line = str(line or "").strip()
        if line and line not in seen:
            seen.add(line)
            hints.append(line)

    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_lower = str(key).lower()
                next_path = f"{path}.{key}" if path else str(key)
                if key_lower in {
                    "connection", "service", "instance", "endpoint",
                    "container", "remote", "docker", "host", "port",
                }:
                    text = str(nested or "").strip()
                    if text:
                        add(f"{next_path}: {text}")
                walk(nested, next_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str):
            candidate = value.strip()
            if re.search(r"\b(?:nc|tcp|udp|http|https|ws|wss)\b", candidate, flags=re.I) or re.search(
                r"\b[a-zA-Z0-9.-]+:\d{2,5}\b", candidate
            ):
                add(f"{path or 'hint'}: {candidate}")

    walk(challenge)
    return hints


# ---------------------------------------------------------------------------
# flag submit / verdict
# ---------------------------------------------------------------------------
def submit_flag(
    session: _GzctfSession,
    base_url: str,
    game_id: int,
    challenge_id: int,
    flag: str,
) -> Tuple[int, bytes]:
    """提交一个 flag，404/405 时回退 ``/submit`` 端点。"""
    public_key = fetch_public_key(session, base_url)
    payload = {"flag": encrypt_api_data(flag, public_key)}
    primary = f"{base_url}/api/game/{game_id}/challenges/{challenge_id}"
    status, body = session.request("POST", primary, json_body=payload)
    if status in (404, 405):
        status, body = session.request(
            "POST", f"{primary}/submit", json_body=payload
        )
    _raise(status, body, "GZCTF Flag 提交失败")
    return status, body


def parse_submit_id(body: bytes) -> Optional[int]:
    """从提交响应中提取 submission id。"""
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    payload = _json_of(body)
    if isinstance(payload, int):
        return payload
    if isinstance(payload, dict):
        for key in ("id", "submitId", "submissionId"):
            value = payload.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return None


def poll_submission_status(
    session: _GzctfSession,
    base_url: str,
    game_id: int,
    challenge_id: int,
    submit_id: int,
    max_polls: int = 8,
    delay: float = 1.0,
) -> Optional[str]:
    """轮询判题结果直到 accepted/rejected 或达到上限。"""
    verdict = None
    for _ in range(max(1, max_polls)):
        status, body = session.request(
            "GET",
            f"{base_url}/api/game/{game_id}/challenges/{challenge_id}/status/{submit_id}",
        )
        _raise(status, body, "读取 GZCTF 判题状态失败")
        verdict = classify_verdict(_json_of(body))
        if verdict in TERMINAL_VERDICTS:
            return verdict
        time.sleep(max(0.0, delay))
    return verdict


def classify_verdict(payload: Any) -> Optional[str]:
    """把多样的判题负载归一化为 accepted/rejected/pending。"""
    flattened = " ".join(part.lower() for part in _walk_strings(payload))
    if any(token in flattened for token in ("accepted", "correct", "success", "passed", "通过", "正确")):
        return "accepted"
    if any(token in flattened for token in ("wrong", "rejected", "incorrect", "denied", "失败", "错误", "不正确")):
        return "rejected"
    if any(token in flattened for token in ("pending", "checking", "queued", "processing", "判题", "等待")):
        return "pending"
    return None


# ---------------------------------------------------------------------------
# plugin
# ---------------------------------------------------------------------------

def _url_basename(url: str) -> str:
    """从 URL 提取默认附件文件名（去除控制字符）。"""
    name = Path(urllib.parse.urlparse(str(url)).path).name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name or "attachment.bin"


def start_challenge_instance(
    session: _GzctfSession,
    base_url: str,
    game_id: int,
    challenge_id: int,
) -> Tuple[dict, bytes]:
    """POST 启动动态题目实例，``/instance`` 优先，404/405 时回退 ``/container``。

    注：GZCTF 动态题目的确切启动协议在真实实例验证前为最佳努力实现——
    采用"POST 尝试 + 容错回退 + 原样透传响应体"，便于前端展示实例信息。
    """
    merged: dict = {}
    raw_body = b""
    last_status = None
    for path in (
        f"/api/game/{game_id}/challenges/{challenge_id}/instance",
        f"/api/game/{game_id}/challenges/{challenge_id}/container",
    ):
        status, body = session.request("POST", f"{base_url}{path}", json_body={})
        if status in (404, 405):
            continue
        last_status = status
        raw_body = body
        payload = _json_of(body)
        if isinstance(payload, dict):
            merged = _merge_dicts(merged, payload)
        elif payload is not None:
            merged.setdefault("raw", payload)
        break
    if last_status is None:
        raise RuntimeError(
            "GZCTF 实例启动失败：/instance 与 /container 端点均不可用（HTTP 404/405）"
        )
    _raise(last_status, raw_body, "GZCTF 实例启动失败")
    return merged, raw_body


def download_attachment(
    session: _GzctfSession,
    url: str,
    dest: Path,
    timeout: float = TIMEOUT,
) -> Tuple[str, int]:
    """用已登录会话下载附件到 ``dest``，返回 (文件名, 字节数)。"""
    status, body = session.request("GET", url, timeout=timeout)
    _raise(status, body, "GZCTF 附件下载失败")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return dest.name, len(body)


def _profile_summary(profile: dict) -> dict:
    out: dict = {}
    for key in ("userName", "role", "avatar"):
        if profile.get(key) is not None:
            out[key] = profile[key]
    return out


class GzctfProvider:
    """Materialize the authenticated GZCTF operations for eligible Agents."""

    def __init__(self, plugin: "GzctfPlugin") -> None:
        """Bind one provider to its plugin-owned service implementation.

        Args:
            plugin: Loaded GZCTF plugin that owns durable cookie state.

        Returns:
            None.
        """
        self._plugin = plugin

    def materialize(self, session_id: str, policy: ToolPolicy, role: str) -> list[Tool]:
        """Create namespaced GZCTF Tools for a coordinator or worker.

        Args:
            session_id: Session requesting the Tool set; cookie state remains
                plugin-private and is not exposed through this value.
            policy: Effective host tool policy; provider visibility is already
                enforced by the host registry.
            role: Receiving Agent role.

        Returns:
            GZCTF tools for coordinator and worker roles, otherwise an empty
            list.
        """
        if role not in {"coordinator", "worker"}:
            return []
        parameter = ToolParameter
        schema = ToolSchema
        return [
            Tool("plugin.gzctf.gzctf_login", "Log in to GZCTF and persist only the authenticated Cookie session.", schema(properties=[parameter("base_url", "string", "GZCTF site URL or /games/{id} URL."), parameter("username", "string", "GZCTF account name."), parameter("password", "string", "Transient GZCTF password; never stored in settings.")]), self._plugin._tool_login),
            Tool("plugin.gzctf.gzctf_status", "Check persisted GZCTF Cookie login state.", schema(properties=[parameter("base_url", "string", "GZCTF site URL or /games/{id} URL.", False, default="")]), self._plugin._tool_status),
            Tool("plugin.gzctf.gzctf_team", "Read current GZCTF team details.", schema(properties=[parameter("base_url", "string", "GZCTF game URL.", False, default=""), parameter("username", "string", "Optional account name for cookie renewal.", False, default=""), parameter("password", "string", "Transient password for cookie renewal.", False, default="")]), self._plugin._tool_team),
            Tool("plugin.gzctf.gzctf_challenges", "List GZCTF challenges with optional filters.", schema(properties=[parameter("base_url", "string", "GZCTF game URL.", False, default=""), parameter("category", "string", "Optional category filter.", False, default=""), parameter("keyword", "string", "Optional title keyword.", False, default=""), parameter("limit", "integer", "Maximum returned challenges.", False, default=100)]), self._plugin._tool_challenges),
            Tool("plugin.gzctf.gzctf_challenge_info", "Read one GZCTF challenge detail.", schema(properties=[parameter("base_url", "string", "GZCTF game URL.", False, default=""), parameter("challenge_id", "string", "Challenge identifier.", False, default=""), parameter("title", "string", "Challenge title when ID is unknown.", False, default=""), parameter("include_detail", "boolean", "Whether to fetch detailed challenge data.", False, default=True)]), self._plugin._tool_challenge_info),
            Tool("plugin.gzctf.gzctf_submit_flag", "Submit a flag and poll the GZCTF verdict.", schema(properties=[parameter("base_url", "string", "GZCTF game URL.", False, default=""), parameter("challenge_id", "string", "Challenge identifier.", False, default=""), parameter("title", "string", "Challenge title when ID is unknown.", False, default=""), parameter("flag", "string", "Flag to submit."), parameter("max_polls", "integer", "Maximum verdict polls.", False, default=8), parameter("delay", "number", "Delay between polls in seconds.", False, default=1.0)]), self._plugin._tool_submit_flag),
            Tool("plugin.gzctf.gzctf_download", "Download an authenticated challenge attachment into plugin-private storage.", schema(properties=[parameter("base_url", "string", "GZCTF site URL.", False, default=""), parameter("url", "string", "Attachment URL."), parameter("dest", "string", "Optional destination filename.", False, default="")]), self._plugin._tool_download),
            Tool("plugin.gzctf.gzctf_start_instance", "Start a GZCTF dynamic challenge instance.", schema(properties=[parameter("base_url", "string", "GZCTF game URL.", False, default=""), parameter("challenge_id", "string", "Challenge identifier."), parameter("title", "string", "Optional challenge title.", False, default="")]), self._plugin._tool_start_instance),
            Tool("plugin.gzctf.gzctf_batch_prepare", "Prepare an authorized GZCTF batch run without solving challenges.", schema(properties=[parameter("base_url", "string", "GZCTF game URL.", False, default=""), parameter("category", "string", "Optional category.", False, default=""), parameter("challenge_ids", "array", "Optional challenge IDs.", False, default=[]), parameter("max_instances", "integer", "Maximum simultaneous dynamic instances.", False, default=1)]), self._plugin._tool_batch_prepare),
            Tool("plugin.gzctf.gzctf_batch_status", "Read a GZCTF batch run state.", schema(properties=[parameter("run_id", "string", "Batch run identifier.")]), self._plugin._tool_batch_status),
            Tool("plugin.gzctf.gzctf_instance_acquire", "Acquire or reuse an instance in a GZCTF batch run.", schema(properties=[parameter("run_id", "string", "Batch run identifier."), parameter("challenge_id", "string", "Challenge identifier."), parameter("base_url", "string", "Optional GZCTF game URL.", False, default="")]), self._plugin._tool_instance_acquire),
        ]


class GzctfLoginAction:
    """Perform one password-only transient login from the host panel."""

    def __init__(self, plugin: "GzctfPlugin") -> None:
        """Retain the loaded plugin service.

        Args:
            plugin: Loaded GZCTF plugin handling the authenticated cookie.

        Returns:
            None.
        """
        self._plugin = plugin

    def __call__(self, request: PluginUiActionRequest) -> PluginUiActionResult:
        """Log in without persisting or echoing the submitted password.

        Args:
            request: Host-validated transient login fields.

        Returns:
            A safe status message without credential values or filesystem paths.
        """
        base_url = request.value("base_url", "")
        username = request.value("username", "")
        password = request.value("password", "")
        if not all(isinstance(value, str) for value in (base_url, username, password)):
            return PluginUiActionResult("登录失败", "登录参数类型无效。", "error")
        try:
            result = self._plugin._tool_login(base_url, username, password)
        except (RuntimeError, ValueError) as exc:
            return PluginUiActionResult("登录失败", str(exc), "error")
        game_id = result.get("game_id")
        suffix = f"，比赛 ID：{game_id}" if game_id is not None else ""
        return PluginUiActionResult("登录成功", f"已为 {username} 建立本地 Cookie 会话{suffix}。", "success")


class GzctfPlugin:
    """GZCTF Helper 插件：登录、题目信息拉取、flag 提交判题、附件下载与动态实例启动。"""

    name = "gzctf"
    version = "2.0.0"

    def setup(self, runtime: PluginRuntime) -> None:
        """Register GZCTF tool definitions and the transient login action.

        Args:
            runtime: Host-owned plugin runtime providing private state and
                non-secret persisted settings.

        Returns:
            None.
        """
        self._runtime = runtime
        runtime.register_tool_provider(PluginToolContribution(
            provider=GzctfProvider(self),
            categories=(PluginToolCategory("ctf", "GZCTF", "Authenticated GZCTF competition operations."),),
            definitions=(
                PluginToolDefinition("gzctf_login", "ctf", "Log in to GZCTF", "Create a private authenticated Cookie session.", frozenset({"coordinator", "worker"})),
                PluginToolDefinition("gzctf_status", "ctf", "Check GZCTF status", "Check the private Cookie login state.", frozenset({"coordinator", "worker"})),
                PluginToolDefinition("gzctf_team", "ctf", "Read GZCTF team", "Read current GZCTF team information.", frozenset({"coordinator", "worker"})),
                PluginToolDefinition("gzctf_challenges", "ctf", "List GZCTF challenges", "List and filter competition challenges.", frozenset({"coordinator", "worker"})),
                PluginToolDefinition("gzctf_challenge_info", "ctf", "Read GZCTF challenge", "Read one challenge detail.", frozenset({"coordinator", "worker"})),
                PluginToolDefinition("gzctf_submit_flag", "ctf", "Submit GZCTF flag", "Submit a flag and read its verdict.", frozenset({"coordinator", "worker"})),
                PluginToolDefinition("gzctf_download", "ctf", "Download GZCTF attachment", "Save an authenticated attachment privately.", frozenset({"coordinator", "worker"})),
                PluginToolDefinition("gzctf_start_instance", "ctf", "Start GZCTF instance", "Start a dynamic challenge instance.", frozenset({"coordinator", "worker"})),
                PluginToolDefinition("gzctf_batch_prepare", "ctf", "Prepare GZCTF batch", "Prepare an authorized batch run.", frozenset({"coordinator", "worker"})),
                PluginToolDefinition("gzctf_batch_status", "ctf", "Read GZCTF batch", "Read an authorized batch run.", frozenset({"coordinator", "worker"})),
                PluginToolDefinition("gzctf_instance_acquire", "ctf", "Acquire GZCTF instance", "Acquire a queued dynamic instance.", frozenset({"coordinator", "worker"})),
            ),
        ))
        runtime.register_ui_action("login", GzctfLoginAction(self))

    def teardown(self) -> None:
        """Release the host runtime reference during plugin unload.

        Returns:
            None.
        """
        self._runtime = None

    # ------------------------------------------------------------------
    # shared helpers
    # ------------------------------------------------------------------
    def _session(self) -> _GzctfSession:
        return _GzctfSession(Path(self._runtime.state_path))

    def _config(self, *keys: str, value: str = "") -> str:
        """参数优先，其次回落插件 settings（plugins.json 持久化配置）。"""
        text = str(value or "").strip()
        if text:
            return text
        for key in keys:
            item = self._runtime.setting(key, "")
            if isinstance(item, str) and item.strip():
                return item.strip()
        return ""

    def _login_if_needed(
        self,
        session: _GzctfSession,
        base_url: str,
        username: str,
        password: str,
    ) -> None:
        """优先复用有效 Cookie，否则用账号密码登录。"""
        if session.has_cookies():
            try:
                verify_profile(session, base_url)
                return
            except Exception:
                pass
        if not username or not password:
            raise ValueError("需要 username 与 password 登录（当前 Cookie 无效或缺失）")
        perform_login(session, base_url, username, password)
        session.save()

    def _downloads_dir(self) -> Path:
        return Path(self._runtime.state_path) / "downloads"

    def _run_store(self) -> AutomationRunStore:
        return AutomationRunStore(Path(self._runtime.state_path))

    def _safe_download_leaf(self, dest: str, url_name: str) -> Path:
        """把目标文件名归一化为 downloads 根内的单层路径（拒绝路径穿越）。

        防线与 pofp-ctf 插件 ``_safe_leaf`` 一致：resolve 后必须仍在
        state_dir/downloads 根内，且仅允许单层文件名（不支持子目录）。
        """
        root = self._downloads_dir()
        raw = re.sub(
            r"[\x00-\x1f\x7f]", "", str(dest or "").strip() or url_name
        ).strip()
        if not raw or raw in (".", ".."):
            raise ValueError("附件下载目标无效")
        candidate = (root / raw).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("附件下载路径越界：仅允许写入插件私有 downloads 目录")
        if candidate.parent != root:
            raise ValueError("dest 仅允许文件名，不支持子目录")
        return candidate


    # ------------------------------------------------------------------
    # tool handlers
    # ------------------------------------------------------------------
    def _tool_login(
        self, base_url: str = "", username: str = "", password: str = "", **_kwargs: Any
    ) -> dict:
        base_url = self._config("base_url", "game_url", value=base_url)
        username = self._config("username", value=username)
        password = self._config("password", value=password)
        if not base_url or not username or not password:
            raise ValueError("缺少参数：base_url / username / password")
        base_url, game_id = parse_game_url(base_url)
        session = self._session()
        session.clear()
        profile = perform_login(session, base_url, username, password)
        session.save()
        team = None
        if game_id is not None:
            details = fetch_game_details(session, base_url, game_id)
            team = extract_team_info(details)
        return {
            "ok": True,
            "base_url": base_url,
            "game_id": game_id,
            "username": username,
            "profile": _profile_summary(profile),
            "team": team,
        }

    def _tool_status(self, base_url: str = "", **_kwargs: Any) -> dict:
        base_url = self._config("base_url", "game_url", value=base_url)
        if not base_url:
            raise ValueError("缺少参数：base_url")
        base_url, game_id = parse_game_url(base_url)
        session = self._session()
        result: dict = {
            "ok": True,
            "base_url": base_url,
            "game_id": game_id,
            "has_cookie": session.has_cookies(),
            "logged_in": False,
        }
        if session.has_cookies():
            try:
                profile = verify_profile(session, base_url)
                result["logged_in"] = True
                result["profile"] = _profile_summary(profile)
            except Exception:
                result["logged_in"] = False
                result["message"] = "Cookie 已过期或无效，请重新登录"
        return result

    def _tool_team(
        self,
        base_url: str = "",
        username: str = "",
        password: str = "",
        **_kwargs: Any,
    ) -> dict:
        base_url = self._config("base_url", "game_url", value=base_url)
        username = self._config("username", value=username)
        password = self._config("password", value=password)
        if not base_url:
            raise ValueError("缺少参数：base_url")
        base_url, game_id = parse_game_url(base_url)
        if game_id is None:
            raise ValueError("比赛链接中缺少 gameId")
        session = self._session()
        self._login_if_needed(session, base_url, username, password)
        details = fetch_game_details(session, base_url, game_id)
        return {
            "ok": True,
            "base_url": base_url,
            "game_id": game_id,
            "team": extract_team_info(details),
        }

    def _tool_challenges(
        self,
        base_url: str = "",
        username: str = "",
        password: str = "",
        category: str = "",
        keyword: str = "",
        limit: int = 100,
        **_kwargs: Any,
    ) -> dict:
        base_url = self._config("base_url", "game_url", value=base_url)
        username = self._config("username", value=username)
        password = self._config("password", value=password)
        if not base_url:
            raise ValueError("缺少参数：base_url")
        base_url, game_id = parse_game_url(base_url)
        if game_id is None:
            raise ValueError("比赛链接中缺少 gameId")
        try:
            limit = max(1, min(int(limit or 100), 500))
        except (TypeError, ValueError):
            limit = 100
        session = self._session()
        self._login_if_needed(session, base_url, username, password)
        details = fetch_game_details(session, base_url, game_id)
        keyword_l = (keyword or "").strip().lower()
        category_l = (category or "").strip().lower()
        challenges: List[dict] = []
        for item in list_challenge_candidates(details):
            title = _challenge_title(item)
            cat = _challenge_category(item)
            if category_l and category_l not in cat.lower():
                continue
            if keyword_l and keyword_l not in title.lower() and keyword_l not in cat.lower():
                continue
            challenges.append(
                {
                    "id": _challenge_identifier(item),
                    "title": title,
                    "category": cat,
                    "score": item.get("score")
                    if isinstance(item.get("score"), (int, float))
                    else None,
                    "solved": item.get("solved")
                    if isinstance(item.get("solved"), bool)
                    else None,
                }
            )
            if len(challenges) >= limit:
                break
        challenges.sort(key=lambda item: (item["category"].lower(), item["title"].lower()))
        return {
            "ok": True,
            "game_id": game_id,
            "count": len(challenges),
            "challenges": challenges,
        }

    def _tool_challenge_info(
        self,
        base_url: str = "",
        challenge_id: str = "",
        title: str = "",
        username: str = "",
        password: str = "",
        include_detail: bool = True,
        **_kwargs: Any,
    ) -> dict:
        base_url = self._config("base_url", "game_url", value=base_url)
        username = self._config("username", value=username)
        password = self._config("password", value=password)
        if not base_url:
            raise ValueError("缺少参数：base_url")
        base_url, game_id = parse_game_url(base_url)
        if game_id is None:
            raise ValueError("比赛链接中缺少 gameId")
        session = self._session()
        self._login_if_needed(session, base_url, username, password)
        details = fetch_game_details(session, base_url, game_id)
        challenge = resolve_challenge(details, challenge_id=challenge_id, title=title)
        if challenge is None:
            return {
                "ok": False,
                "reason": "challenge_not_found",
                "challenge_id": challenge_id,
                "title": title,
            }
        info: dict = {
            "id": _challenge_identifier(challenge),
            "title": _challenge_title(challenge),
            "category": _challenge_category(challenge),
        }
        if include_detail:
            merged = dict(challenge)
            cid_int = _parse_int(_challenge_identifier(challenge))
            if cid_int is not None:
                merged = _merge_dicts(
                    merged, fetch_challenge_detail(session, base_url, game_id, cid_int)
                )
            description = _clean_html(
                str(
                    merged.get("description")
                    or merged.get("content")
                    or merged.get("body")
                    or merged.get("html")
                    or merged.get("statement")
                    or ""
                )
            )
            if description:
                info["description"] = description
            if merged.get("score") is not None:
                info["score"] = merged.get("score")
            if merged.get("tags") is not None:
                info["tags"] = merged.get("tags")
            attachments = _collect_attachments(merged, base_url)
            if attachments:
                info["attachments"] = attachments
            hints = _collect_connection_hints(merged)
            if hints:
                info["connection_hints"] = hints
        return {"ok": True, "game_id": game_id, "challenge": info}

    def _tool_submit_flag(
        self,
        base_url: str = "",
        challenge_id: str = "",
        title: str = "",
        flag: str = "",
        username: str = "",
        password: str = "",
        max_polls: int = 8,
        delay: float = 1.0,
        **_kwargs: Any,
    ) -> dict:
        base_url = self._config("base_url", "game_url", value=base_url)
        username = self._config("username", value=username)
        password = self._config("password", value=password)
        flag = str(flag or "").strip()
        if not base_url:
            raise ValueError("缺少参数：base_url")
        if not flag:
            raise ValueError("缺少参数：flag")
        base_url, game_id = parse_game_url(base_url)
        if game_id is None:
            raise ValueError("比赛链接中缺少 gameId")
        try:
            max_polls = max(1, int(max_polls or 8))
        except (TypeError, ValueError):
            max_polls = 8
        try:
            delay = max(0.0, float(delay or 1.0))
        except (TypeError, ValueError):
            delay = 1.0
        session = self._session()
        self._login_if_needed(session, base_url, username, password)
        details = fetch_game_details(session, base_url, game_id)
        challenge = resolve_challenge(details, challenge_id=challenge_id, title=title)
        if challenge is None:
            return {
                "ok": False,
                "attempted": False,
                "reason": "challenge_not_found",
                "challenge_id": challenge_id,
                "title": title,
            }
        cid_int = _parse_int(_challenge_identifier(challenge))
        if cid_int is None:
            return {
                "ok": False,
                "attempted": False,
                "reason": "challenge_id_not_numeric",
                "challenge_id": _challenge_identifier(challenge),
            }
        challenge_name = _challenge_title(challenge)
        _, body = submit_flag(session, base_url, game_id, cid_int, flag)
        submit_id = parse_submit_id(body)
        verdict = None
        if submit_id is not None:
            verdict = poll_submission_status(
                session,
                base_url,
                game_id,
                cid_int,
                submit_id,
                max_polls=max_polls,
                delay=delay,
            )
        return {
            "ok": True,
            "attempted": True,
            "accepted": verdict == "accepted",
            "verdict": verdict or "unknown",
            "game_id": game_id,
            "challenge_id": cid_int,
            "challenge_name": challenge_name,
            "submit_id": submit_id,
        }

    def _tool_download(
        self, base_url: str = "", url: str = "", dest: str = "", **_kwargs: Any
    ) -> dict:
        base_url = self._config("base_url", "game_url", value=base_url)
        if not base_url:
            raise ValueError("缺少参数：base_url")
        if not str(url or "").strip():
            raise ValueError("缺少参数：url")
        base_url, _ = parse_game_url(base_url)
        session = self._session()
        self._login_if_needed(session, base_url, "", "")
        target_url = urllib.parse.urljoin(base_url + "/", str(url).strip())
        target = self._safe_download_leaf(dest, _url_basename(target_url))
        name, size = download_attachment(session, target_url, target)
        return {
            "ok": True,
            "name": name,
            "path": str(target),
            "size_bytes": size,
        }

    def _tool_start_instance(
        self,
        base_url: str = "",
        challenge_id: str = "",
        title: str = "",
        **_kwargs: Any,
    ) -> dict:
        base_url = self._config("base_url", "game_url", value=base_url)
        if not base_url:
            raise ValueError("缺少参数：base_url")
        if not str(challenge_id or "").strip():
            raise ValueError("缺少参数：challenge_id")
        base_url, game_id = parse_game_url(base_url)
        if game_id is None:
            raise ValueError("比赛链接中缺少 gameId")
        session = self._session()
        self._login_if_needed(session, base_url, "", "")
        details = fetch_game_details(session, base_url, game_id)
        challenge = resolve_challenge(details, challenge_id=challenge_id, title=title)
        if challenge is None:
            return {
                "ok": False,
                "reason": "challenge_not_found",
                "challenge_id": challenge_id,
                "title": title,
            }
        cid_int = _parse_int(_challenge_identifier(challenge))
        if cid_int is None:
            return {
                "ok": False,
                "reason": "challenge_id_not_numeric",
                "challenge_id": _challenge_identifier(challenge),
            }
        payload, raw_body = start_challenge_instance(
            session, base_url, game_id, cid_int
        )
        hints = _collect_connection_hints(payload)
        return {
            "ok": True,
            "game_id": game_id,
            "challenge_id": cid_int,
            "challenge_name": _challenge_title(challenge),
            "payload": payload,
            "connection_hints": hints or None,
            "raw_response": raw_body.decode("utf-8", errors="replace"),
        }

    def _tool_batch_prepare(self, base_url: str = "", category: str = "", challenge_ids: list[Any] | None = None, max_instances: int = 1, **_kwargs: Any) -> dict:
        """Create a durable run and prepare attachments without solving anything."""
        listing = self._tool_challenges(base_url=base_url, category=category, limit=500)
        wanted = {str(value) for value in (challenge_ids or []) if str(value).strip()}
        selected = [item for item in listing["challenges"] if item.get("solved") is not True and (not wanted or str(item["id"]) in wanted)]
        run = self._run_store().create(listing["game_id"], selected, max_instances=max_instances)
        for cid, item in run["challenges"].items():
            try:
                info = self._tool_challenge_info(base_url=base_url, challenge_id=cid)
                challenge = info.get("challenge", {})
                for attachment in challenge.get("attachments", []) or []:
                    result = self._tool_download(base_url=base_url, url=str(attachment.get("url", "")), dest=f"{cid}-{attachment.get('name', 'attachment')}")
                    item["attachments"].append({"name": result["name"], "path": result["path"], "size_bytes": result["size_bytes"]})
                item["state"] = "prepared"
            except Exception as exc:
                item["state"] = "failed"; item["error"] = str(exc)
        self._run_store().save(run)
        return self._batch_summary(run)

    def _tool_batch_status(self, run_id: str, **_kwargs: Any) -> dict:
        return self._batch_summary(self._run_store().load(run_id))

    def _tool_instance_acquire(self, run_id: str, challenge_id: str, base_url: str = "", **_kwargs: Any) -> dict:
        store = self._run_store(); run = store.load(run_id); item = run["challenges"].get(str(challenge_id))
        if not isinstance(item, dict): raise ValueError("challenge is not in this automation run")
        if item.get("instance") and item.get("state") == "instance_ready": return {"ok": True, "state": "instance_ready", "reused": True, "instance": item["instance"]}
        now = time.time()
        if now < float(item.get("next_retry_at") or 0): return {"ok": True, "state": "queued", "next_retry_at": item["next_retry_at"]}
        if AutomationRunStore.active_instances(run) >= run["max_instances"]:
            item["state"] = "queued"; item["next_retry_at"] = now + 15; store.save(run)
            return {"ok": True, "state": "queued", "reason": "local_instance_limit", "next_retry_at": item["next_retry_at"]}
        try:
            result = self._tool_start_instance(base_url=base_url, challenge_id=str(challenge_id))
            item["instance"] = result; item["state"] = "instance_ready"; item["error"] = None
        except Exception as exc:
            item["attempts"] = int(item.get("attempts") or 0) + 1; item["state"] = "queued"
            item["error"] = str(exc); item["next_retry_at"] = now + min(300, 5 * (2 ** min(item["attempts"], 6)))
        store.save(run)
        return {"ok": True, "state": item["state"], "instance": item.get("instance"), "error": item.get("error"), "next_retry_at": item.get("next_retry_at")}

    @staticmethod
    def _batch_summary(run: dict) -> dict:
        challenges = list(run.get("challenges", {}).values())
        return {"ok": True, "run_id": run["id"], "game_id": run["game_id"], "completed": AutomationRunStore.complete(run),
                "max_instances": run["max_instances"], "active_instances": AutomationRunStore.active_instances(run),
                "challenges": challenges, "next_actions": [item["id"] for item in challenges if item.get("state") in {"prepared", "queued", "instance_ready", "submitted"}]}


angelus_plugin = GzctfPlugin()
