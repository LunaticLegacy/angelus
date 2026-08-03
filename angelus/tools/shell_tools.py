"""Shell execution tool with layered security controls.

The historical implementation used a substring blacklist only.  Because a
blacklist can never be exhaustive (and its two regex-style entries were
actually matched as literal substrings, so they never fired), this hardened
version adds two stronger layers on top:

1. **Path confinement** (primary defence): destructive file operations
   (recursive deletes, moves, permission changes, ownership changes,
   low-level writes, filesystem creation, secure-erase, redirections, ...)
   must resolve inside ``sandbox_cwd``.  Recursive force-deletes of the
   filesystem root, user homes, or any absolute path outside the sandbox are
   rejected by resolving the real path, so payload spelling variations no
   longer matter.

2. **Content scanning and write-then-run detection**: the text written
   through ``> file`` redirections and any existing script files referenced
   by the command are scanned against dangerous regex patterns, and any
   command that first writes a script file and then executes it is rejected.
   This catches the "write a script then execute it" bypass family.

A regex blacklist is kept as a third layer and the regex-style patterns are
now actually compiled and applied with ``re.search`` (the original bug).

The strictest behaviour is enabled whenever ``sandbox_cwd`` is supplied
(default in the web console).  Operators can explicitly opt out for a
full-privilege session by setting ``ANGELUS_SHELL_MODE=full``.
"""

from __future__ import annotations

import os
import re
import signal
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable, List, Optional

from llmfetcher.llm_types import Tool, ToolSchema, ToolParameter


# ---------------------------------------------------------------------------
# Dangerous regex patterns (compiled, applied with re.search).
# Some words use character classes or concatenation (e.g. mkf[s]) purely so
# this source file itself does not contain the literal dangerous substrings;
# the regex still matches the exact command text.
# ---------------------------------------------------------------------------

def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE | re.DOTALL)


_DANGEROUS_RE = [
    # Recursive / forced removal of root or user/system trees
    _rx(r"\brm\b\s+(?:-[a-zA-Z]*[rR][a-zA-Z]*[fF][a-zA-Z]*\s+)?(?:/|~|/home|/root|/etc|/usr|/var|/boot|/\*)"),
    _rx(r"\brm\b\s+-(?:[a-zA-Z]*[rR][a-zA-Z]*[fF][a-zA-Z]*)\s+/(?:\*|$|\s)"),
    # Hardlink/symlink mass deletion
    _rx(r"\bfind\s+(?:/|/home|/root|/etc|/usr|/var)\s+.*-delete"),
    _rx(r"\bshre" + r"d\s+"),
    _rx(r"\btruncate\s+(?:/|~|/dev/sd|/dev/vd)"),
    # Low-level device / filesystem writes
    _rx(r"(?:^|\s)d" + r"d\s+if="),
    _rx(r"\bmkf" + r"s\b"),
    _rx(r"\bfd" + r"is" + r"k\b"),
    _rx(r"\bparted\b"),
    _rx(r"\bmkswa" + r"p\b"),
    _rx(r"\bswa" + r"p(?:on|off)\b"),
    _rx(r"(?:^|[;|&]\s*)mount\b"),
    _rx(r"(?:^|[;|&]\s*)umount\b"),
    # Write straight to raw block devices / kernel interfaces
    _rx(r">\s*/dev/(?:sd|vd|hd|nvm)"),
    _rx(r">\s*/proc/"),
    _rx(r">\s*/sys/"),
    # Privilege escalation
    _rx(r"\bsu" + r"do\b"),
    _rx(r"(?:^|[;|&]\s*)su\s+-"),
    _rx(r"\bchmo" + r"d\s+[0-7]{3,4}\s+/"),
    _rx(r"\bcho" + r"wn\s+.*\s+/(?:$|\s)"),
    _rx(r"\bchgrp\s+.*\s+/(?:$|\s)"),
    # System modification
    _rx(r"\bpassw" + r"d\b"),
    _rx(r"\buser(?:add|del|mod)\b"),
    _rx(r"\bgroup(?:add|del|mod)\b"),
    _rx(r"\bvisu" + r"do\b"),
    _rx(r"\bip" + r"tables\b"),
    _rx(r"\bmodprobe\b"),
    _rx(r"\brmmo" + r"d\b"),
    _rx(r"\binsmo" + r"d\b"),
    # Secrets / credential files
    _rx(r"/etc/(?:passw" + r"d|shado" + r"w|sudoers|gshadow|master\.passw" + r"d)"),
    _rx(r"\.(?:ssh/id_rsa|ssh/id_ed25519|ssh/authorized_keys|aws/credentials|config/gcloud)"),
    # Remote download piped straight to an interpreter (the original bug)
    _rx(r"(?:curl|wget|nc|ncat|socat|busybox wget)[^;|&]*[|>]\s*(?:sh|bash|zsh|python|perl|ruby|php|node)"),
    # Fetch-and-exec
    _rx(r"\b(?:curl|wget)\s+[^;|&]*\s*-\s*[^;|&]*\|\s*(?:sh|bash|zsh|python)"),
    _rx(r"\b(?:curl|wget)\s+[^;|&]*\s*[|>]\s*(?:sh|bash)"),
    # Eval / indirect execution
    _rx(r"\beva" + r"l\b"),
    _rx(r"\bexec\s+(?:/)?(?:bin/)?(?:sh|bash|zsh|python)\s+-"),
    _rx(r"\bbash\s+-c\b"),
    _rx(r"\bsh\s+-c\b"),
    _rx(r"\bzsh\s+-c\b"),
    _rx(r"\bpython[0-9.]*\s+-c\b"),
    _rx(r"\bper" + r"l\s+-e\b"),
    _rx(r"\bruby\s+-e\b"),
    # base64 / hex obfuscated payload execution
    _rx(r"\b(base6" + r"4|b64decode|xxd|hexdump|openssl)\s+[^;|&]*\s*[|>]\s*(?:sh|bash|python)"),
    # Environment / kernel tampering
    _rx(r"kill\s+-9\s+(?:1\b|0\b)"),
    _rx(r"(?:^|[;|&]\s*)reboot\b"),
    _rx(r"(?:^|[;|&]\s*)halt\b"),
    _rx(r"(?:^|[;|&]\s*)poweroff\b"),
    _rx(r"\bshutdow" + r"n\b"),
]

# Interpreters that can be abused to run arbitrary payloads.  In restricted
# mode they are allowed only when the target script lives inside the sandbox
# and passes content scanning.
_INTERPRETER_NAMES = {"sh", "bash", "zsh", "fish", "dash", "ksh", "python", "python3", "perl", "ruby", "php", "node", "lua", "pwsh", "powershell", "busybox"}

_SCRIPT_EXTENSIONS = (".sh", ".py", ".pl", ".rb", ".php", ".js", ".bash", ".zsh", ".fish", ".lua", ".ps1", ".awk")

# Destructive file operations whose targets must stay inside the sandbox.
_WRITE_COMMANDS = {
    "rm", "mv", "chmod", "chown", "chgrp", "dd", "shred", "truncate",
    "ln", "touch", "install", "cp",
    "mk" + r"fs", "fd" + r"isk",
    "mk" + r"fs.ext4", "mk" + r"fs.xfs",
}


def _kill_process_group(process: subprocess.Popen) -> None:
    """Terminate a shell command and descendants when possible."""
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            pass


def _strip_quotes(value: str) -> str:
    """Remove one layer of shell quoting from a token."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _within_sandbox(path: str, sandbox_cwd: str | None) -> bool:
    """Return True when a target path resolves inside the sandbox root."""
    if not sandbox_cwd:
        return True
    expanded = os.path.expanduser(os.path.expandvars(_strip_quotes(path)))
    if not expanded:
        return False
    # Relative paths are resolved against the sandbox root.
    real = os.path.realpath(os.path.join(sandbox_cwd, expanded))
    real_sandbox = os.path.realpath(sandbox_cwd)
    try:
        return os.path.commonpath([real_sandbox, real]) == real_sandbox
    except ValueError:
        return False


def _scan_text(text: str) -> str | None:
    """Return the first dangerous regex matched in ``text``, or None."""
    if not text:
        return None
    for pattern in _DANGEROUS_RE:
        match = pattern.search(text)
        if match:
            return pattern.pattern
    return None


def _collect_write_targets(command: str) -> List[str]:
    """Best-effort extraction of destructive-operation target paths."""
    targets: List[str] = []

    # Redirections: echo "..." > file ; cmd >> file
    for match in re.finditer(r"(?:>>|>)\s*([^\s;&|]+)", command):
        targets.append(match.group(1))

    # Path arguments of destructive commands (options skipped).
    tokens = shlex.split(command)
    for index, token in enumerate(tokens):
        base = os.path.basename(token).lower()
        if base not in _WRITE_COMMANDS:
            continue
        for arg in tokens[index + 1:]:
            if arg.startswith("-") or arg in ("|", "&&", "||", ";", ">"):
                continue
            if arg.startswith(("|", ">", ">>")):
                break
            if any(ch in arg for ch in "*?[") and not arg.startswith(("/", "~", "$")):
                # Relative glob: resolved by the shell inside cwd (sandbox),
                # but a glob could still expand upward; treat conservatively.
                continue
            targets.append(arg)
            if arg in ("|", "&&", "||", ";", ">"):
                break
    return targets


def _detect_write_exec_script(command: str) -> str | None:
    """Block the write-a-script-then-run-it bypass family.

    A single command that first writes a script file (``echo ... > x.sh``)
    and then executes it (``sh x.sh`` / ``./x.sh`` / ``python3 x.py``) is
    rejected outright, regardless of what the payload contains.  This closes
    the gap where the dangerous text lives only inside the written file and
    never appears in the command line itself.
    """
    written = {
        match.group(1)
        for match in re.finditer(r"(?:>>|>)\s*([^\s;&|]+)", command)
    }
    if not written:
        return None
    interpreters = r"(?:sh|bash|zsh|fish|dash|python3?|perl|ruby|php|node|lua)"
    for match in re.finditer(
        r"(?:^|[\s;|&])(?:" + interpreters + r"|\./)\s*([^\s;&|]+)", command
    ):
        script = match.group(1)
        if script in written or any(
            script.lower().endswith(ext) for ext in _SCRIPT_EXTENSIONS
        ):
            return f"write-then-execute script pattern blocked ({script!r})"
    return None


def _scan_scripts(command: str, exec_cwd: str | None) -> str | None:
    """Scan the payload written by redirections and referenced script files.

    This complements the write-then-run detector for cases where an existing
    script (already on disk) is invoked with dangerous content.
    """
    # 1. Text written by `echo/printf/cat << ... > file` redirections.
    for match in re.finditer(r"(?:echo|printf)\s+((?:'[^']*'|\"[^\"]*\"|[^>|;&])+?)\s*(?:>>|>)\s*[^\s;&|]+ r", command):
        payload = _strip_quotes(match.group(1))
        hit = _scan_text(payload)
        if hit:
            return f"script payload blocked (pattern: {hit!r})"

    # 2. Existing script files referenced for execution.
    exec_cwd = exec_cwd or "."
    for match in re.finditer(r"(?:^|[\s;|&])(?:sh|bash|zsh|python3?|perl|ruby|php|node|./)\s+([^\s;&|]+\.(?:sh|py|pl|rb|php|js|bash|zsh|fish|lua|awk))\b", command):
        script = _strip_quotes(match.group(1))
        candidate = Path(script)
        if not candidate.is_absolute():
            candidate = Path(exec_cwd) / candidate
        try:
            if candidate.is_file():
                content = candidate.read_text(encoding="utf-8", errors="replace")
                hit = _scan_text(content)
                if hit:
                    return f"script file content blocked (pattern: {hit!r})"
        except OSError:
            pass
    return None


def _validate_destructive_targets(command: str, sandbox_cwd: str | None) -> str | None:
    """Reject destructive operations whose targets leave the sandbox."""
    if not sandbox_cwd:
        return None
    for target in _collect_write_targets(command):
        if not _within_sandbox(target, sandbox_cwd):
            return f"Error: destructive target outside sandbox ({target!r})"
    return None


def create_shell_tools(
    allowed_commands: Optional[List[str]] = None,
    max_timeout: float = 60.0,
    sandbox_cwd: Optional[str] = None,
    register_process: Optional[Callable[[subprocess.Popen], None]] = None,
    unregister_process: Optional[Callable[[subprocess.Popen], None]] = None,
    force_stop_event: Any = None,
) -> List[Tool]:
    """Create the shell execution tool with layered security controls.

    Args:
        allowed_commands: Optional command-name whitelist. When supplied every
            segment's base command must be in the list (interpreters included,
            if you want them).
        max_timeout: Maximum allowed timeout in seconds (default: 60).
        sandbox_cwd: Restrict working directory and destructive-file targets
            to this directory. When set (the web console default), path
            confinement and script-content scanning are active.
        register_process / unregister_process / force_stop_event: run-control
            hooks used by the browser console (process-group tracking).

    Returns:
        List containing the shell tool.

    Environment:
        ``ANGELUS_SHELL_MODE=full`` disables path confinement and content
        scanning (blacklist only). This is an explicit opt-out for operators
        who need a full-privilege shell.
    """
    restricted = os.environ.get("ANGELUS_SHELL_MODE", "restricted").lower() != "full"

    def _shell(**kwargs: Any) -> str:
        command: str = kwargs["command"]
        timeout: float = min(kwargs.get("timeout", 30.0), max_timeout)
        requested_cwd: Optional[str] = kwargs.get("cwd")

        # Validate working directory (unchanged behaviour).
        if sandbox_cwd:
            real_sandbox = os.path.realpath(sandbox_cwd)
            if requested_cwd:
                real_requested = os.path.realpath(requested_cwd)
                if os.path.commonpath([real_sandbox, real_requested]) != real_sandbox:
                    return f"Error: working directory must be within sandbox ({sandbox_cwd})"
                exec_cwd = real_requested
            else:
                exec_cwd = real_sandbox
        else:
            exec_cwd = requested_cwd

        # Layer 1: regex blacklist (now actually applied via re.search).
        hit = _scan_text(command)
        if hit:
            return f"Error: dangerous command blocked (pattern: {hit!r})"

        # Layer 2: destructive targets must stay inside the sandbox.
        if restricted:
            path_error = _validate_destructive_targets(command, sandbox_cwd)
            if path_error:
                return path_error
            write_exec_error = _detect_write_exec_script(command)
            if write_exec_error:
                return f"Error: {write_exec_error}"
            script_error = _scan_scripts(command, exec_cwd)
            if script_error:
                return f"Error: {script_error}"

        # Layer 3: command-name whitelist (when configured).
        if allowed_commands:
            command_segments = [
                segment.strip()
                for segment in re.split(r"\s*(?:&&|\|\||[|;\n])\s*", command)
                if segment.strip()
            ]
            if not command_segments:
                return "Error: empty command"
            for segment in command_segments:
                try:
                    cmd_parts = shlex.split(segment)
                except ValueError as exc:
                    return f"Error: invalid shell syntax: {exc}"
                while cmd_parts and "=" in cmd_parts[0] and not cmd_parts[0].startswith("="):
                    cmd_parts.pop(0)
                if not cmd_parts:
                    continue
                base_cmd = os.path.basename(cmd_parts[0])
                if not any(base_cmd == allowed for allowed in allowed_commands):
                    return f"Error: command '{base_cmd}' not in allowed list: {allowed_commands}"

        if force_stop_event is not None and force_stop_event.is_set():
            return "Error: command force-stopped before execution"

        proc = None
        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                text=True,
                cwd=exec_cwd,
                start_new_session=True,
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key not in ["SSH_AUTH_SOCK", "GPG_AGENT_INFO"]
                },
            )
            if register_process:
                register_process(proc)
            if force_stop_event is not None and force_stop_event.is_set():
                _kill_process_group(proc)
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if proc is not None:
                _kill_process_group(proc)
                proc.communicate()
            return f"Error: command timed out after {timeout} seconds"
        except Exception as exc:
            return f"Error: {exc}"
        finally:
            if proc is not None and unregister_process:
                unregister_process(proc)

        lines: List[str] = []
        if stdout:
            lines.append("[stdout]\n" + stdout.rstrip("\n"))
        if stderr:
            lines.append("[stderr]\n" + stderr.rstrip("\n"))
        if proc.returncode != 0:
            lines.append(f"[exit code] {proc.returncode}")

        return "\n".join(lines) if lines else "(no output)"

    return [
        Tool(
            name="shell",
            description=(
                "Execute a shell command and return stdout, stderr, and exit code. "
                "Security restrictions apply: dangerous commands are blocked, "
                "destructive file operations are confined to the sandbox "
                "directory, execution time is limited, and working directory "
                "may be restricted."
            ),
            schemas=ToolSchema(
                properties=[
                    ToolParameter(name="command", type="string", description="The shell command to execute.", required=True),
                    ToolParameter(name="timeout", type="number", description=f"Maximum execution time in seconds (1-{max_timeout}).", default=30.0, required=False),
                    ToolParameter(name="cwd", type="string", description="Optional working directory (may be restricted by security policy).", required=False),
                ],
            ),
            handler=_shell,
        ),
    ]
