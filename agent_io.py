"""Filesystem helpers for reading agent runtime state.

This module is intentionally lightweight: it focuses on locating agent
packages under a swarm root, loading their manifests and blueprint files,
and reading runtime-side files such as ``state.json`` or ``context.jsonl``.

The goal is to give the future agent runtime core a single entry point for
filesystem inspection without coupling that core to a specific graph or LLM
implementation.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - fallback for older runtimes
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True)
class AgentWorkspacePolicy:
    """Workspace policy resolved for one agent."""

    mode: str
    root: Path
    raw_root: str


@dataclass(frozen=True)
class AgentFileLocations:
    """Resolved source and runtime paths for one agent."""

    package_root: Path
    manifest_path: Path
    agent_file: Path
    prompt_file: Optional[Path]
    skill_files: List[Path] = field(default_factory=list)
    runtime_root: Path = field(default_factory=Path)
    state_file: Path = field(default_factory=Path)
    context_file: Path = field(default_factory=Path)
    memory_file: Path = field(default_factory=Path)
    log_file: Path = field(default_factory=Path)


@dataclass
class AgentFileSnapshot:
    """A fully loaded view of one agent package and its runtime files."""

    agent_id: str
    package_name: str
    package_root: Path
    manifest_path: Path
    agent_file: Path
    agent_spec: Dict[str, Any]
    swarm_spec: Dict[str, Any]
    workspace: AgentWorkspacePolicy
    prompt_text: str
    prompt_source: Optional[Path]
    skill_sources: List[Path]
    runtime_root: Path
    state_file: Path
    context_file: Path
    memory_file: Path
    log_file: Path
    state: Optional[Dict[str, Any]] = None
    context: List[Dict[str, Any]] = field(default_factory=list)
    memory: Optional[Any] = None
    log_tail: Optional[str] = None


class AgentFileIOManager:
    """Discover agent packages and read agent-related files.

    The manager assumes the swarm root contains package directories like:

    ``agents/<package_name>/swarm.toml``
    ``agents/<package_name>/agents/<agent_file>.py``
    ``agents/<package_name>/skills/<skill_file>.md``
    ``agents/<package_name>/runtime/agents/<agent_id>/state.json``
    """

    def __init__(
        self,
        swarm_root: str | Path = "agents",
        *,
        manifest_name: str = "swarm.toml",
        runtime_dir_name: str = "runtime",
        agent_runtime_dir_name: str = "agents",
    ) -> None:
        self.swarm_root = Path(swarm_root).expanduser().resolve()
        self.manifest_name = manifest_name
        self.runtime_dir_name = runtime_dir_name
        self.agent_runtime_dir_name = agent_runtime_dir_name

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_packages(self) -> List[Path]:
        """Return package roots that contain a manifest file."""
        if not self.swarm_root.exists():
            return []
        packages: List[Path] = []
        for entry in sorted(self.swarm_root.iterdir()):
            if entry.is_dir() and (entry / self.manifest_name).is_file():
                packages.append(entry)
        return packages

    def list_agent_ids(self) -> List[str]:
        """Return all discoverable agent ids across all packages."""
        agent_ids: List[str] = []
        for package_root in self.discover_packages():
            manifest = self._load_manifest(package_root)
            for spec in self._iter_agent_specs(package_root, manifest):
                agent_id = spec.get("agent_id")
                if isinstance(agent_id, str):
                    agent_ids.append(agent_id)
        return sorted(dict.fromkeys(agent_ids))

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def read_agent_snapshot(
        self,
        agent_id: str,
        *,
        package_name: Optional[str] = None,
        include_runtime_files: bool = True,
    ) -> AgentFileSnapshot:
        """Load a complete snapshot for one agent.

        Args:
            agent_id: Stable agent identifier.
            package_name: Optional package to restrict the search to.
            include_runtime_files: If True, read state/context/memory/log files.
        """
        record = self.get_agent_record(agent_id, package_name=package_name)
        locations = self._resolve_locations(record)
        prompt_text, prompt_source = self._resolve_prompt_text(record, locations)
        workspace = self._resolve_workspace(record)

        snapshot = AgentFileSnapshot(
            agent_id=record["agent_id"],
            package_name=record["package_name"],
            package_root=record["package_root"],
            manifest_path=locations.manifest_path,
            agent_file=locations.agent_file,
            agent_spec=record["agent_spec"],
            swarm_spec=record["manifest"].get("swarm", {}),
            workspace=workspace,
            prompt_text=prompt_text,
            prompt_source=prompt_source,
            skill_sources=locations.skill_files,
            runtime_root=locations.runtime_root,
            state_file=locations.state_file,
            context_file=locations.context_file,
            memory_file=locations.memory_file,
            log_file=locations.log_file,
        )

        if include_runtime_files:
            snapshot.state = self._read_json_if_exists(locations.state_file)
            snapshot.context = self._read_jsonl_if_exists(locations.context_file)
            snapshot.memory = self._read_json_or_text_if_exists(locations.memory_file)
            snapshot.log_tail = self._read_log_tail_if_exists(locations.log_file)

        return snapshot

    def read_agent_state(
        self,
        agent_id: str,
        *,
        package_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the decoded ``state.json`` payload for an agent if present."""
        snapshot = self.read_agent_snapshot(agent_id, package_name=package_name)
        return snapshot.state

    def read_agent_context(
        self,
        agent_id: str,
        *,
        package_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return the decoded ``context.jsonl`` payload for an agent."""
        snapshot = self.read_agent_snapshot(agent_id, package_name=package_name)
        return snapshot.context

    def read_agent_prompt(
        self,
        agent_id: str,
        *,
        package_name: Optional[str] = None,
    ) -> str:
        """Return the resolved prompt text for an agent."""
        snapshot = self.read_agent_snapshot(
            agent_id,
            package_name=package_name,
            include_runtime_files=False,
        )
        return snapshot.prompt_text

    def read_agent_log_tail(
        self,
        agent_id: str,
        *,
        package_name: Optional[str] = None,
        max_lines: int = 200,
    ) -> Optional[str]:
        """Return the tail of the agent log file if it exists."""
        record = self.get_agent_record(agent_id, package_name=package_name)
        locations = self._resolve_locations(record)
        return self._read_log_tail_if_exists(locations.log_file, max_lines=max_lines)

    def get_agent_record(
        self,
        agent_id: str,
        package_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Find the manifest record for one agent."""
        packages = self.discover_packages()
        if package_name is not None:
            packages = [p for p in packages if p.name == package_name]

        matches: List[Dict[str, Any]] = []
        for package_root in packages:
            manifest = self._load_manifest(package_root)
            for record in self._iter_loaded_agent_records(package_root, manifest):
                if record["agent_id"] == agent_id:
                    matches.append(record)

        if not matches:
            scope = f" in package '{package_name}'" if package_name else ""
            raise KeyError(f"Agent '{agent_id}' not found{scope}.")
        if len(matches) > 1 and package_name is None:
            package_names = ", ".join(sorted(r["package_name"] for r in matches))
            raise ValueError(
                f"Agent '{agent_id}' is ambiguous across packages: {package_names}. "
                "Pass package_name to disambiguate."
            )
        return matches[0]

    # ------------------------------------------------------------------
    # Internal manifest loading
    # ------------------------------------------------------------------

    def _load_manifest(self, package_root: Path) -> Dict[str, Any]:
        manifest_path = package_root / self.manifest_name
        with manifest_path.open("rb") as handle:
            return tomllib.load(handle)

    def _iter_agent_specs(
        self,
        package_root: Path,
        manifest: Dict[str, Any],
    ) -> Iterable[Dict[str, Any]]:
        swarm_block = manifest.get("swarm", {})
        agent_files = swarm_block.get("agent_files", [])
        if not isinstance(agent_files, list):
            return []
        specs: List[Dict[str, Any]] = []
        for rel_path in agent_files:
            agent_file = (package_root / rel_path).resolve()
            specs.extend(self._load_agent_specs(agent_file))
        return specs

    def _iter_loaded_agent_records(
        self,
        package_root: Path,
        manifest: Dict[str, Any],
    ) -> Iterable[Dict[str, Any]]:
        swarm_block = manifest.get("swarm", {})
        agent_files = swarm_block.get("agent_files", [])
        if not isinstance(agent_files, list):
            return []

        records: List[Dict[str, Any]] = []
        for rel_path in agent_files:
            agent_file = (package_root / rel_path).resolve()
            for spec in self._load_agent_specs(agent_file):
                agent_id = spec.get("agent_id")
                if not isinstance(agent_id, str) or not agent_id.strip():
                    continue
                records.append(
                    {
                        "agent_id": agent_id,
                        "agent_spec": spec,
                        "agent_file": agent_file,
                        "package_root": package_root,
                        "package_name": package_root.name,
                        "manifest": manifest,
                    }
                )
        return records

    def _load_agent_specs(self, agent_file: Path) -> List[Dict[str, Any]]:
        specs = self._extract_agent_specs_from_source(agent_file)
        if specs:
            return specs

        module = self._load_agent_module(agent_file)
        return self._extract_agent_specs_from_module(module, agent_file)

    def _extract_agent_specs_from_source(self, agent_file: Path) -> List[Dict[str, Any]]:
        if not agent_file.is_file():
            return []
        try:
            source = agent_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return []
        try:
            tree = ast.parse(source, filename=str(agent_file))
        except SyntaxError:
            return []

        specs: List[Dict[str, Any]] = []
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id not in {"AGENT", "AGENT_SPEC", "AGENTS"}:
                    continue
                try:
                    payload = ast.literal_eval(node.value)
                except Exception:
                    continue
                specs.extend(self._coerce_agent_payload(payload, agent_file))
        return specs

    def _extract_agent_specs_from_module(
        self,
        module: ModuleType,
        agent_file: Path,
    ) -> List[Dict[str, Any]]:
        if hasattr(module, "AGENTS"):
            payload = getattr(module, "AGENTS")
        elif hasattr(module, "AGENT_SPEC"):
            payload = getattr(module, "AGENT_SPEC")
        elif hasattr(module, "AGENT"):
            payload = getattr(module, "AGENT")
        else:
            return []

        if isinstance(payload, dict):
            return self._coerce_agent_payload(payload, agent_file)
        return []

    def _coerce_agent_payload(self, payload: Any, agent_file: Path) -> List[Dict[str, Any]]:
        if isinstance(payload, dict):
            return [self._normalize_agent_spec(payload, agent_file)]
        if isinstance(payload, list):
            specs: List[Dict[str, Any]] = []
            for item in payload:
                if isinstance(item, dict):
                    specs.append(self._normalize_agent_spec(item, agent_file))
            return specs
        return []

    def _normalize_agent_spec(self, spec: Dict[str, Any], agent_file: Path) -> Dict[str, Any]:
        normalized = dict(spec)
        if not isinstance(normalized.get("agent_id"), str) or not normalized["agent_id"].strip():
            normalized["agent_id"] = agent_file.stem
        return normalized

    def _load_agent_module(self, agent_file: Path) -> ModuleType:
        if not agent_file.is_file():
            raise FileNotFoundError(f"Agent file not found: {agent_file}")
        module_name = f"_angelus_agent_{abs(hash(agent_file.as_posix()))}"
        spec = importlib.util.spec_from_file_location(module_name, agent_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load agent file: {agent_file}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def _resolve_locations(self, record: Dict[str, Any]) -> AgentFileLocations:
        package_root: Path = record["package_root"]
        agent_file: Path = record["agent_file"]
        manifest: Dict[str, Any] = record["manifest"]
        agent_spec: Dict[str, Any] = record["agent_spec"]

        manifest_path = package_root / self.manifest_name
        skill_files = self._resolve_skill_files(package_root, manifest, agent_spec)
        prompt_file = self._resolve_prompt_file(package_root, agent_spec, skill_files)

        runtime_root = self._resolve_runtime_root(package_root, record["agent_id"])
        return AgentFileLocations(
            package_root=package_root,
            manifest_path=manifest_path,
            agent_file=agent_file,
            prompt_file=prompt_file,
            skill_files=skill_files,
            runtime_root=runtime_root,
            state_file=runtime_root / "state.json",
            context_file=runtime_root / "context.jsonl",
            memory_file=runtime_root / "memory.json",
            log_file=runtime_root / "agent.log",
        )

    def _resolve_workspace(self, record: Dict[str, Any]) -> AgentWorkspacePolicy:
        manifest = record["manifest"]
        package_root: Path = record["package_root"]
        agent_id: str = record["agent_id"]

        workspace_block = manifest.get("workspace", {}) if isinstance(manifest, dict) else {}
        agent_overrides = workspace_block.get("agents", {}) if isinstance(workspace_block, dict) else {}
        override = agent_overrides.get(agent_id, {}) if isinstance(agent_overrides, dict) else {}

        mode = str(override.get("mode") or workspace_block.get("default_mode") or "workspace")
        raw_root = str(override.get("root") or workspace_block.get("default_root") or ".")

        workspace_dir = package_root / "workspace"
        root = Path(raw_root)
        if root.is_absolute():
            resolved_root = root.resolve()
        else:
            resolved_root = (workspace_dir / root).resolve()

        return AgentWorkspacePolicy(mode=mode, root=resolved_root, raw_root=raw_root)

    def _resolve_runtime_root(self, package_root: Path, agent_id: str) -> Path:
        return (package_root / self.runtime_dir_name / self.agent_runtime_dir_name / agent_id).resolve()

    def _resolve_skill_files(
        self,
        package_root: Path,
        manifest: Dict[str, Any],
        agent_spec: Dict[str, Any],
    ) -> List[Path]:
        candidates: List[Path] = []
        swarm_block = manifest.get("swarm", {})
        skill_files = swarm_block.get("skill_files", [])
        if isinstance(skill_files, list):
            for rel_path in skill_files:
                path = (package_root / rel_path).resolve()
                if path.is_file():
                    candidates.append(path)

        skill_name = agent_spec.get("skill_name")
        if isinstance(skill_name, str) and skill_name:
            for suffix in (".prompt.md", ".prompt.txt", ".md", ".txt", ".toml"):
                path = (package_root / "skills" / f"{skill_name}{suffix}").resolve()
                if path.is_file():
                    candidates.append(path)
                    break

        # Deduplicate while preserving order.
        seen: set[Path] = set()
        ordered: List[Path] = []
        for path in candidates:
            if path not in seen:
                seen.add(path)
                ordered.append(path)
        return ordered

    def _resolve_prompt_file(
        self,
        package_root: Path,
        agent_spec: Dict[str, Any],
        skill_files: Sequence[Path],
    ) -> Optional[Path]:
        prompt_file = agent_spec.get("prompt_file")
        if isinstance(prompt_file, str) and prompt_file.strip():
            path = (package_root / prompt_file).resolve()
            if path.is_file():
                return path
        if skill_files:
            for path in skill_files:
                if path.suffix in {".md", ".txt"}:
                    return path
        return None

    def _resolve_prompt_text(
        self,
        record: Dict[str, Any],
        locations: AgentFileLocations,
    ) -> tuple[str, Optional[Path]]:
        spec = record["agent_spec"]

        prompt_text = spec.get("prompt_text")
        if isinstance(prompt_text, str) and prompt_text.strip():
            return prompt_text, None

        if locations.prompt_file and locations.prompt_file.is_file():
            return locations.prompt_file.read_text(encoding="utf-8"), locations.prompt_file

        parts: List[str] = []
        character_prompt = spec.get("character_prompt")
        if isinstance(character_prompt, str) and character_prompt.strip():
            parts.append(character_prompt.strip())

        for skill_file in locations.skill_files:
            if skill_file.is_file():
                try:
                    parts.append(skill_file.read_text(encoding="utf-8").strip())
                except UnicodeDecodeError:
                    parts.append(f"[binary skill file: {skill_file.name}]")

        return "\n\n".join(part for part in parts if part), locations.prompt_file

    # ------------------------------------------------------------------
    # File readers
    # ------------------------------------------------------------------

    def _read_json_if_exists(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        return {"value": data}

    def _read_jsonl_if_exists(self, path: Path) -> List[Dict[str, Any]]:
        if not path.is_file():
            return []
        rows: List[Dict[str, Any]] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
            else:
                rows.append({"value": payload})
        return rows

    def _read_json_or_text_if_exists(self, path: Path) -> Optional[Any]:
        if not path.is_file():
            return None
        raw_text = path.read_text(encoding="utf-8")
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            return raw_text

    def _read_log_tail_if_exists(self, path: Path, max_lines: int = 200) -> Optional[str]:
        if not path.is_file():
            return None
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if max_lines <= 0:
            return ""
        return "\n".join(lines[-max_lines:])
