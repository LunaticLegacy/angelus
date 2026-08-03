# Angelus Security Hardening

This branch applies a security-hardening pass to the Angelus local web console
(originally at `baf30b2` + llmfetcher submodule `3dc8245`). The original files
in `/home/luna/codes/angelus` were **not** modified; this is a standalone clone.

## What was changed

| Area | Change |
|------|--------|
| Authentication | New bearer-token auth. Token auto-generated into `<state>/auth_token` (mode 0600) or via `ANGELUS_TOKEN` env. Every `/api/*` and `/openapi.json` request requires `Authorization: Bearer <token>` (query `?token=` also accepted for SSE/EventSource). |
| API-key masking | `GET /api/connectors` no longer returns plaintext keys: `api_key` is emptied, `has_api_key` / `api_key_hint` are returned instead. |
| Server-side key resolution | Runs may specify `connector_id`; the server fills in the stored key (and empty fields) so the browser never holds the plaintext key. `PUT` preserves the stored key when a masked placeholder is sent. |
| Host-header validation | Requests with non-local `Host` are rejected (400), blocking DNS-rebinding attacks. Matching is hostname-based so any local port works. Override with `ANGELUS_ALLOWED_HOSTS`. |
| SSRF guard | LLM `api_url` is validated before every run/connector write: plain `http` only for loopback hosts, private/link-local/reserved IP ranges blocked (cloud metadata included). Opt-in for private LAN models via `ANGELUS_ALLOW_PRIVATE_LLM_URLS=1`. |
| Shell tool gating | `ANGELUS_DISABLE_SHELL=1` hard-disables the shell tool (`enable_shell=true` -> 403). Default remains opt-in per run. |
| CSRF defence | State-changing requests carrying a cross-origin `Origin` header are rejected (403). |
| Rate limiting | Per-(IP, path-class) fixed-window limits: `/api/runs` default 10/min, other API default 300/min. Tune via `ANGELUS_RUN_RATE_LIMIT` / `ANGELUS_API_RATE_LIMIT`. |
| OpenAPI | `/openapi.json` disabled by default; enable with `ANGELUS_ENABLE_OPENAPI=1`. `/docs`, `/redoc` remain disabled. |
| Security headers | Added `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, a CSP, and `Cache-Control: no-store` on API responses. |
| Frontend | Token prompt dialog, `Authorization` header on all fetches, token via query for EventSource, `connector_id` sent with run config, masked-key hints shown in the connector picker. |

## New files
- `angelus/security.py` — SecurityManager + middleware + SSRF/mask helpers.

## Modified files
- `angelus/webapp.py` — wired middleware, masked connectors, `_resolve_run_config`, startup banner.
- `angelus/classes/run_config.py` — added optional `connector_id`.
- `frontend/static/app.js` — auth + connector_id handling.
- `frontend/templates/index.html` — token unlock dialog.
- `.gitmodules` — submodule URL switched to HTTPS (local convenience; SSH keys are unavailable in this environment).

## Configuration knobs (all optional, environment variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANGELUS_TOKEN` | auto-generated | Access token. Auto-generated token is stored in `workspace/auth_token`. |
| `ANGELUS_ALLOWED_HOSTS` | localhost, 127.0.0.1, ::1 | Extra hosts to allow (comma separated). |
| `ANGELUS_ALLOW_PRIVATE_LLM_URLS` | `0` | Set `1` to allow private-network LLM `api_url` targets. |
| `ANGELUS_DISABLE_SHELL` | `0` | Set `1` to forbid the shell tool entirely. |
| `ANGELUS_ENABLE_OPENAPI` | `0` | Set `1` to expose `/openapi.json`. |
| `ANGELUS_RUN_RATE_LIMIT` | `10` | Max `/api/runs` starts per minute per client. |
| `ANGELUS_API_RATE_LIMIT` | `300` | Max other API calls per minute per client. |

## Verified test results (regression)

- No token / wrong token -> `401`; correct token -> `200`.
- `Host: evil.example.com` -> `400`; `localhost:<any port>` -> `200`.
- `/openapi.json`, `/docs`, `/redoc` -> `404` by default.
- `GET /api/connectors` returns masked keys only (`has_api_key`, `api_key_hint`).
- Run with `connector_id` and empty key: server fills stored key (observed key used in upstream request = stored key).
- `PUT` connector with masked key preserves stored key.
- Create connector with masked key -> `422`.
- `api_url=http://10.0.0.1`, `http://169.254.169.254`, `http://<remote>` -> `422`; `https://api.deepseek.com` -> accepted.
- Cross-origin `Origin` on POST -> `403`.
- `/api/runs` burst > limit -> `429`.
- `ANGELUS_DISABLE_SHELL=1` + `enable_shell=true` -> `403`.

## Run it

```bash
cd /home/luna/codes/angelus-secure
python3 -m venv .venv && . .venv/bin/activate
pip install -e .            # llmfetcher is a local submodule
LLMFETCHER_STATE_DIR=/home/luna/codes/angelus-secure/workspace \
  .venv/bin/python3 -m uvicorn angelus.webapp:app --host 127.0.0.1 --port 8766
# Open http://localhost:8766 and enter the token shown at startup
# (also available in workspace/auth_token).
```

> Note: `migrate_legacy_state()` runs at import. Point `LLMFETCHER_STATE_DIR`
> at a fresh directory so the hardened instance never reads the original
> checkout's `workspace/`.


## Shell tool safety group (added later)

The web console's shell tool (`angelus/tools/shell_tools.py`) previously relied
on a substring blacklist only (and its two regex-style entries were matched as
literal substrings, so they never fired). It is now a layered safety group:

1. **Path confinement** (primary): destructive file operations (`rm`, `mv`,
   `chmod`, `chown`, `dd`, `shred`, `truncate`, `ln`, `touch`, `install`, `cp`,
   redirections) must resolve inside the session sandbox directory. Targets
   outside it — including `../` escapes and absolute paths — are rejected by
   real-path resolution, so payload spelling (`rm -r` vs `rm -rf`, etc.) no
   longer matters.
2. **Write-then-run detection**: any command that writes a script file
   (`echo ... > x.sh`) and then executes it (`sh x.sh`, `./x.sh`,
   `python3 x.py`) is rejected outright — the exact bypass family you asked
   about.
3. **Content scanning**: text written via redirections and existing script
   files referenced by the command are scanned against a fixed dangerous-regex
   set.
4. **Regex blacklist (fixed)**: the two broken regex-style entries are now
   compiled and applied with `re.search`; the list is also expanded
   (`sudo`, `su -`, `mkfs`, `fdisk`, `dd`, `curl|bash`, `bash -c`, `eval`,
   base64-piped-to-shell, `/etc/passwd|shadow`, device/kernel writes, reboot/
   shutdown, ...).
5. **Optional command-name whitelist** via `allowed_commands`.

Normal in-sandbox work (write/read/delete files in the session directory) is
unaffected. Operators who explicitly need a full-privilege shell can opt out
with `ANGELUS_SHELL_MODE=full` (blacklist only). The global
`ANGELUS_DISABLE_SHELL=1` switch still fully disables the tool.

Verified matrix (sandboxed test):

| Case | Result |
|------|--------|
| `echo "` + D + `" > file1.sh && chmod +x ./file1.sh && ./file1.sh` | blocked |
| `echo "rm -r /outside" > s.sh && sh s.sh` | blocked (write-then-run) |
| `rm -r /tmp/outside` / `rm -r ../outside` | blocked (path confinement) |
| `echo "import os..." > s.py && python3 s.py` | blocked (write-then-run) |
| `curl http://x | bash` / `sudo id` / base64-piped-to-shell | blocked (regex) |
| in-sandbox `echo`, `cat`, `ls`, `mkdir`, `rm ./file` | allowed |
| `ANGELUS_SHELL_MODE=full` + `rm -r /outside` | allowed (explicit opt-out) |

> Note: this is application-level containment. The remaining hard boundary
> against arbitrary interpreter payloads is OS-level sandboxing (Landlock /
> bubblewrap / container), which is not available in this WSL2 environment;
> it is recommended for deployments where the agent is exposed to untrusted
> input.
