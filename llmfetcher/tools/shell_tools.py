import os
import re
import signal
import shlex
import subprocess
from typing import Any, Callable, Dict, List, Optional

from ..llm_types import Tool, ToolSchema, ToolParameter


def _kill_process_group(process: subprocess.Popen) -> None:
    """Terminate a shell command and descendants when possible."""
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            pass


def create_shell_tools(
    allowed_commands: Optional[List[str]] = None,
    max_timeout: float = 60.0,
    sandbox_cwd: Optional[str] = None,
    register_process: Optional[Callable[[subprocess.Popen], None]] = None,
    unregister_process: Optional[Callable[[subprocess.Popen], None]] = None,
    force_stop_event: Any = None,
) -> List[Tool]:
    """Create shell execution tool with security controls.

    Args:
        allowed_commands: Whitelist of allowed command prefixes (e.g., ["ls", "cat", "grep"]).
                         If None, uses blacklist approach (less secure).
        max_timeout: Maximum allowed timeout in seconds (default: 60).
        sandbox_cwd: Restrict execution to this directory (prevents path traversal).

    Returns:
        List containing the shell tool.
    """

    # Default blacklist for dangerous operations
    DANGEROUS_PATTERNS = [
        "rm -rf /", "rm -rf /*", "> /dev/sda",
        ":(){ :|:& };:",  # fork bomb
        "chmod 777 /", "chown -R",
        "dd if=", "mkfs", "fdisk",
        "wget.*\\|.*sh", "curl.*\\|.*bash",  # pipe to shell
        "/etc/passwd", "/etc/shadow",
        "sudo ", "su ",
    ]

    def _shell(**kwargs: Any) -> str:
        command: str = kwargs["command"]
        timeout: float = min(kwargs.get("timeout", 30.0), max_timeout)
        requested_cwd: Optional[str] = kwargs.get("cwd")

        # Validate working directory
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

        # Security check 1: Blacklist validation
        stripped = command.strip().lower()
        for pattern in DANGEROUS_PATTERNS:
            if pattern.lower() in stripped:
                return f"Error: dangerous command blocked (pattern: {pattern!r})"

        # Security check 2: Whitelist validation (if configured)
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
                "execution time is limited, and working directory may be restricted."
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
