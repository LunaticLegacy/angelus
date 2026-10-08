"""Report unhandled API failures instead of a bare plain-text 500.

FastAPI answers an unhandled exception with a plain-text ``Internal Server
Error`` body. The console parses response bodies as JSON, so that body reads as
a JSON parse error and hides the real cause. This module answers with a JSON
``detail`` and appends the traceback to a durable log under the state root, so a
failure stays diagnosable without the terminal that launched the server.
"""

from __future__ import annotations

import traceback
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def write_failure(state_root: Path, request: Request, exc: Exception) -> Path:
    """Append one failure and its traceback to the state-root log.

    Args:
        state_root: Angelus-owned state root; the log lives under it.
        request: The request whose handler raised.
        exc: The unhandled exception.

    Returns:
        The log file the failure was appended to.
    """
    log_path = state_root / "logs" / "api-errors.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry = (
        f"{timestamp} {request.method} {request.url.path}\n"
        + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        + "\n"
    )
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    return log_path


def install_error_reporting(app: FastAPI, state_root: Path) -> None:
    """Answer unhandled exceptions with JSON detail and log their traceback.

    Args:
        app: Application receiving the handler.
        state_root: Angelus-owned state root for the failure log.
    """

    async def report(request: Request, exc: Exception) -> JSONResponse:
        # Reporting must never become the failure: a full disk only costs the
        # log location, never the answer that names the exception.
        try:
            location: str | None = str(write_failure(state_root, request, exc))
        except OSError:
            location = None
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(exc).__name__}: {exc}", "log": location},
        )

    app.add_exception_handler(Exception, report)


__all__ = ["install_error_reporting", "write_failure"]
