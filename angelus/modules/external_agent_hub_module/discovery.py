"""Bounded read-only operating-system discovery for External Agent Hub."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import ExternalAgentCandidate, ExternalAgentAdapterKind


@dataclass(frozen=True)
class _ProcessPattern:
    """One safe executable-name mapping used by local process discovery.

    Attributes:
        executable_names: Executable basenames that identify one product.
        adapter_kind: Hub adapter suitable for a later user-created definition.
        product_name: Display name used in candidate projections.
        endpoint: Non-secret endpoint suggestion for a new definition.
    """

    executable_names: tuple[str, ...]
    adapter_kind: ExternalAgentAdapterKind
    product_name: str
    endpoint: str


_PATTERNS = (
    _ProcessPattern(("codex",), "codex_app_server", "Codex", "stdio://"),
    _ProcessPattern(("claude",), "claude_sdk", "Claude Code", ""),
    _ProcessPattern(("opencode",), "opencode", "OpenCode", ""),
)


class ExternalAgentProcessDiscovery:
    """Discover known local Agent processes without attaching or signaling them."""

    def __init__(self, proc_root: Path = Path("/proc"), command_limit: int = 512) -> None:
        """Create a Linux procfs-backed discovery reader.

        Args:
            proc_root: Root of the procfs tree; injectable for deterministic tests.
            command_limit: Maximum characters retained from one command summary.

        Returns:
            None.
        """
        self._proc_root = proc_root
        self._command_limit = command_limit

    def discover(self) -> tuple[ExternalAgentCandidate, ...]:
        """Return known local Agent processes in ascending process-id order.

        Returns:
            Ephemeral candidate observations. The operation only reads procfs;
            it never attaches to, signals, starts, or persists a process.
        """
        if not self._proc_root.is_dir():
            return ()
        candidates: list[ExternalAgentCandidate] = []
        for process_path in sorted(self._proc_root.iterdir(), key=_process_sort_key):
            if not process_path.name.isdigit():
                continue
            candidate = self._read_candidate(process_path)
            if candidate is not None:
                candidates.append(candidate)
        return tuple(candidates)

    def _read_candidate(self, process_path: Path) -> ExternalAgentCandidate | None:
        """Project one readable procfs entry into a known-product candidate.

        Args:
            process_path: Numeric process directory in procfs.

        Returns:
            Candidate when the process command has a known executable basename;
            otherwise ``None``.
        """
        try:
            arguments = tuple(item for item in (process_path / "cmdline").read_bytes().split(b"\0") if item)
        except OSError:
            return None
        if not arguments:
            return None
        executable = Path(arguments[0].decode("utf-8", errors="replace")).name.lower()
        pattern = next((item for item in _PATTERNS if executable in item.executable_names), None)
        if pattern is None:
            return None
        process_id = int(process_path.name)
        command = _safe_command(arguments, self._command_limit)
        working_directory = _working_directory(process_path)
        return ExternalAgentCandidate(
            candidate_id=f"process-{process_id}-{pattern.adapter_kind}",
            adapter_kind=pattern.adapter_kind,
            title=f"{pattern.product_name} process #{process_id}",
            process_id=process_id,
            command=command,
            working_directory=working_directory,
            endpoint=pattern.endpoint,
            attachable=False,
            detail=(
                "A local process was detected. Angelus will not attach to, signal, "
                "or reuse this running instance; adding it only pre-fills a separate Hub definition."
            ),
        )


def _process_sort_key(path: Path) -> int:
    """Return a deterministic numeric sort key for a procfs directory.

    Args:
        path: One filesystem path under procfs.

    Returns:
        Numeric process identifier, or a stable maximum key for non-process paths.
    """
    return int(path.name) if path.name.isdigit() else 2**31 - 1


def _safe_command(arguments: tuple[bytes, ...], limit: int) -> str:
    """Build a bounded command summary while avoiding environment inspection.

    Args:
        arguments: Raw NUL-delimited process arguments from procfs.
        limit: Maximum returned character count.

    Returns:
        Whitespace-normalized command preview with obvious credential arguments
        redacted.
    """
    rendered: list[str] = []
    redact_next = False
    for raw in arguments:
        value = raw.decode("utf-8", errors="replace")
        lowered = value.lower()
        if redact_next:
            rendered.append("[redacted]")
            redact_next = False
        elif lowered in {"--api-key", "--token", "--password", "--secret"}:
            rendered.append(value)
            redact_next = True
        elif any(marker in lowered for marker in ("api_key=", "token=", "password=", "secret=")):
            rendered.append("[redacted-argument]")
        else:
            rendered.append(value)
    return " ".join(rendered)[:limit]


def _working_directory(process_path: Path) -> str:
    """Read one process working directory without failing the whole scan.

    Args:
        process_path: Numeric process directory in procfs.

    Returns:
        Resolved working directory when permission allows, otherwise an empty string.
    """
    try:
        return str((process_path / "cwd").resolve(strict=True))
    except OSError:
        return ""
