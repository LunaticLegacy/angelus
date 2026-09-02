"""Loopback-only host directory selection for creating a Session."""

from __future__ import annotations

from pathlib import Path
import threading

from fastapi import APIRouter, HTTPException


router = APIRouter()
_dialog_lock = threading.Lock()


@router.post("/api/workspace-directory/pick")
def pick_workspace_directory() -> dict[str, bool | str | None]:
    """Open one native directory picker and return a selected absolute path.

    The workbench is a loopback application, so the dialog belongs to the
    same desktop user that started Angelus.  The lock prevents two browser
    clicks from creating competing Tk dialogs.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise HTTPException(status_code=501, detail="native directory picker is unavailable") from exc

    with _dialog_lock:
        root = None
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(parent=root, title="选择 Angelus 项目目录", mustexist=True)
        except tk.TclError as exc:
            raise HTTPException(status_code=503, detail="native directory picker requires a graphical desktop session") from exc
        finally:
            if root is not None:
                root.destroy()
    if not selected:
        return {"cancelled": True, "path": None}
    return {"cancelled": False, "path": str(Path(selected).resolve())}


__all__ = ["router"]
