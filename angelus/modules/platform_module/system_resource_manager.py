"""Dispatch folder selection to the host operating system's desktop shell."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import platform
import shutil
import subprocess
import threading
from typing import Any


class SystemResourceManagerError(RuntimeError):
    """The operating-system folder picker could not complete successfully."""


class SystemResourceManagerUnavailable(SystemResourceManagerError):
    """The host has no supported operating-system folder picker."""


class SystemResourceManager:
    """Select directories through the system desktop, never the web runtime."""

    def __init__(
        self,
        *,
        system_name: str | None = None,
        which: Callable[[str], str | None] = shutil.which,
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self._system_name = system_name or platform.system()
        self._which = which
        self._runner = runner
        self._dialog_lock = threading.Lock()

    def select_directory(self, *, title: str = "选择 Angelus 项目目录") -> Path | None:
        """Return one existing directory selected by the host desktop shell."""
        command = self._picker_command(title)
        with self._dialog_lock:
            try:
                result = self._runner(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
            except OSError as exc:
                raise SystemResourceManagerUnavailable(
                    "unable to start the operating-system resource manager"
                ) from exc

        if result.returncode != 0:
            if self._is_cancelled(result.returncode, str(result.stderr or "")):
                return None
            detail = str(result.stderr or "").strip()
            raise SystemResourceManagerError(
                detail or "the operating-system resource manager failed"
            )

        selected = str(result.stdout or "").strip()
        if not selected:
            return None
        path = Path(selected).expanduser()
        if not path.is_dir():
            raise SystemResourceManagerError(
                "the operating-system resource manager returned a non-directory path"
            )
        return path.resolve()

    def _picker_command(self, title: str) -> list[str]:
        """Build the command for the current host without invoking it."""
        if self._system_name == "Windows":
            executable = self._first_available("powershell.exe", "powershell")
            script = (
                "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
                "$shell=New-Object -ComObject Shell.Application;"
                f"$folder=$shell.BrowseForFolder(0,'{_powershell_literal(title)}',1,0);"
                "if($null-ne $folder){[Console]::Out.Write($folder.Self.Path)}"
            )
            return [executable, "-NoProfile", "-NonInteractive", "-STA", "-Command", script]
        if self._system_name == "Darwin":
            executable = self._first_available("osascript")
            script = (
                "try\n"
                f'  set chosenFolder to choose folder with prompt "{_applescript_literal(title)}"\n'
                "  POSIX path of chosenFolder\n"
                "on error number -128\n"
                '  return ""\n'
                "end try"
            )
            return [executable, "-e", script]
        if self._system_name == "Linux":
            return self._linux_picker_command(title)
        raise SystemResourceManagerUnavailable(
            f"unsupported operating system: {self._system_name or 'unknown'}"
        )

    def _linux_picker_command(self, title: str) -> list[str]:
        """Use an installed desktop chooser belonging to the Linux session."""
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        candidates = ("kdialog", "zenity") if "kde" in desktop else ("zenity", "kdialog")
        for name in candidates:
            executable = self._which(name)
            if not executable:
                continue
            if name == "kdialog":
                return [executable, "--title", title, "--getexistingdirectory", str(Path.home())]
            return [executable, "--file-selection", "--directory", f"--title={title}"]
        raise SystemResourceManagerUnavailable(
            "no supported Linux system resource manager is available (install zenity or kdialog)"
        )

    def _first_available(self, *names: str) -> str:
        for name in names:
            executable = self._which(name)
            if executable:
                return executable
        raise SystemResourceManagerUnavailable(
            f"operating-system resource manager executable is unavailable: {names[0]}"
        )

    def _is_cancelled(self, returncode: int, stderr: str) -> bool:
        if self._system_name == "Linux" and returncode == 1:
            return True
        return self._system_name == "Darwin" and (
            returncode == 1 and ("-128" in stderr or "user canceled" in stderr.lower())
        )


def _powershell_literal(value: str) -> str:
    """Escape a value for a single-quoted PowerShell literal."""
    return value.replace("'", "''")


def _applescript_literal(value: str) -> str:
    """Escape a value embedded in an AppleScript string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
