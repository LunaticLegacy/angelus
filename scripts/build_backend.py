"""Build the Tauri Python sidecar without relying on a shell environment."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENTRY_SCRIPT = PROJECT_ROOT / "scripts" / "backend_entry.py"
OUTPUT_DIR = PROJECT_ROOT / "src-tauri" / "binaries"
ARTIFACT_STEM = "angelus-backend"


def add_data(source: Path, destination: str) -> str:
    """Return PyInstaller's platform-native source/destination argument."""
    return f"{source}{os.pathsep}{destination}"


def main() -> None:
    """Package the backend and install the resulting sidecar for Tauri."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        ARTIFACT_STEM,
        "--onefile",
        "--add-data",
        add_data(PROJECT_ROOT / "frontend", "frontend"),
        "--add-data",
        add_data(PROJECT_ROOT / "plugins", "starter-plugins"),
        "--collect-all",
        "angelus",
        "--collect-all",
        "llmfetcher",
        # Collect the complete client transport surface without importing the
        # optional MCP command-line UI (which requires the separate `typer`
        # extra and is not used by the embedded Agent runtime).
        "--collect-submodules",
        "mcp.client",
        "--collect-submodules",
        "mcp.shared",
        "--collect-data",
        "mcp",
        "--collect-all",
        "mcp_types",
        str(ENTRY_SCRIPT),
    ]
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)

    artifact = PROJECT_ROOT / "dist" / (
        f"{ARTIFACT_STEM}.exe" if os.name == "nt" else ARTIFACT_STEM
    )
    if not artifact.is_file():
        raise RuntimeError(f"PyInstaller did not create expected sidecar: {artifact}")
    destination = OUTPUT_DIR / artifact.name
    shutil.copy2(artifact, destination)
    if os.name != "nt":
        destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Built desktop sidecar: {destination}")


if __name__ == "__main__":
    main()
