"""Check that Angelus distribution manifests match its runtime version."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def npm_version(pepit: str) -> str:
    """Convert the supported PEP 440 release-candidate form to SemVer.

    Args:
        pepit: Angelus PEP 440 version value.

    Returns:
        Equivalent SemVer string used by npm, Cargo, and Tauri.

    Raises:
        ValueError: If the version uses a prerelease form this checker cannot
            map without ambiguity.
    """
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:rc(\d+))?", pepit)
    if match is None:
        raise ValueError(f"unsupported Angelus version: {pepit}")
    return match.group(1) if match.group(2) is None else f"{match.group(1)}-rc.{match.group(2)}"


def check_versions() -> list[str]:
    """Return one mismatch description for every stale version manifest.

    Returns:
        Empty list when all independent package manifests match Angelus.
    """
    from angelus._version import ANGELUS_VERSION

    expected_semver = npm_version(ANGELUS_VERSION)
    expected_wix = ANGELUS_VERSION.split("rc", 1)[0] + ".0"
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    tauri = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    cargo = (ROOT / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    errors: list[str] = []
    if pyproject.get("project", {}).get("dynamic") != ["version"]:
        errors.append("pyproject.toml must read Angelus version dynamically")
    if package.get("version") != expected_semver:
        errors.append("package.json version differs from Angelus version")
    if tauri.get("version") != expected_semver:
        errors.append("tauri.conf.json version differs from Angelus version")
    if tauri.get("bundle", {}).get("windows", {}).get("wix", {}).get("version") != expected_wix:
        errors.append("Tauri WiX version differs from Angelus version")
    if re.search(r'^version\s*=\s*"' + re.escape(expected_semver) + r'"$', cargo, re.MULTILINE) is None:
        errors.append("Cargo.toml version differs from Angelus version")
    return errors


def main() -> int:
    """Print version drift and return a conventional process status.

    Returns:
        Zero when every manifest is aligned, otherwise one.
    """
    errors = check_versions()
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
