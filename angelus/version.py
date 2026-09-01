"""Runtime version projection for diagnostics and HTTP clients."""
from __future__ import annotations

from dataclasses import dataclass

from llmfetcher import __version__ as llmfetcher_version

from ._version import ANGELUS_VERSION


@dataclass(frozen=True)
class RuntimeVersions:
    """Independent application and orchestration-library version metadata.

    Attributes:
        angelus_version: Running Angelus distribution version.
        llmfetcher_version: Running independent llmfetcher distribution version.
        llmfetcher_compatibility: Angelus dependency range accepted by this build.
    """

    angelus_version: str
    llmfetcher_version: str
    llmfetcher_compatibility: str


def runtime_versions() -> RuntimeVersions:
    """Return version information from independent runtime authorities.

    Returns:
        Non-secret immutable version metadata for diagnostics and clients.
    """
    return RuntimeVersions(
        angelus_version=ANGELUS_VERSION,
        llmfetcher_version=llmfetcher_version,
        llmfetcher_compatibility=">=0.4.0,<0.5.0",
    )
