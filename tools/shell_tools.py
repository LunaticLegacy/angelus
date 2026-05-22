import asyncio
import os
import re
import shlex
from typing import Any, Dict, List, Optional

from ..tool import Tool


def create_shell_tools(
    allowed_commands: Optional[List[str]] = None,
    max_timeout: float = 60.0,
    sandbox_cwd: Optional[str] = None,
) -> List[Tool]:
    """Create shell execution tool with security controls.
    
    Args:
        allowed_commands: Whitelist of allowed command prefixes (e.g., ["ls", "cat", "grep"]).
                         If None, uses blacklist approach (less secure).
        max_timeout: Maximum allowed timeout in seconds (default: 60).
        sandbox_cwd: Restrict execution to this directory (prevents path traversal).
    
    Returns:
        List containing the shell tool.
    
    Security Features:
        - Command whitelist/blacklist validation
        - Timeout limits
        - Working directory restrictions
        - Dangerous pattern detection
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

    async def _shell(**kwargs: Any) -> str:
        command: str = kwargs["command"]
        timeout: float = min(kwargs.get("timeout", 30.0), max_timeout)
        requested_cwd: Optional[str] = kwargs.get("cwd")

        # Validate working directory
        if sandbox_cwd:
            real_sandbox = os.path.realpath(sandbox_cwd)
            if requested_cwd:
                # Ensure requested cwd is within sandbox
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

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=exec_cwd,
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key not in ["SSH_AUTH_SOCK", "GPG_AGENT_INFO"]
                },
            )
            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            if proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            return f"Error: command timed out after {timeout} seconds"
        except Exception as exc:
            return f"Error: {exc}"

        stdout_text = stdout_data.decode("utf-8", errors="replace") if stdout_data else ""
        stderr_text = stderr_data.decode("utf-8", errors="replace") if stderr_data else ""

        lines: List[str] = []
        if stdout_text:
            lines.append("[stdout]\n" + stdout_text)
        if stderr_text:
            lines.append("[stderr]\n" + stderr_text)
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
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                    "timeout": {
                        "type": "number",
                        "minimum": 1.0,
                        "maximum": max_timeout,
                        "default": 30.0,
                        "description": f"Maximum execution time in seconds (1-{max_timeout}).",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory (may be restricted by security policy).",
                    },
                },
                "required": ["command"],
            },
            handler=_shell,
        ),
    ]
