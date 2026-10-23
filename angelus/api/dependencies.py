"""Explicit FastAPI dependencies for application-owned services."""
from __future__ import annotations

from fastapi import Request
from typing import cast

from ..core import AngelusCore


def get_core(request: Request) -> AngelusCore:
    """Return the installed composition root or fail explicitly."""
    try:
        core = request.app.state.angelus_core
    except AttributeError as exc:
        raise RuntimeError("AngelusCore is not installed on this application") from exc
    return cast(AngelusCore, core)


__all__ = ["get_core"]
