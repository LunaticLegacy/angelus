"""Regression tests for operating-system-owned directory selection."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from angelus.modules.platform_module import (
    SystemResourceManager,
    SystemResourceManagerError,
    SystemResourceManagerUnavailable,
)


class SystemResourceManagerTests(unittest.TestCase):
    """Keep folder selection out of browser and Tauri runtimes."""

    def test_linux_dispatches_to_installed_system_picker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            selected = Path(temporary)
            calls: list[list[str]] = []

            def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, f"{selected}\n", "")

            manager = SystemResourceManager(
                system_name="Linux",
                which=lambda name: "/usr/bin/zenity" if name == "zenity" else None,
                runner=run,
            )

            self.assertEqual(manager.select_directory(), selected.resolve())
            self.assertEqual(calls[0][0], "/usr/bin/zenity")
            self.assertIn("--directory", calls[0])

    def test_linux_cancel_is_not_an_error(self) -> None:
        command_result = subprocess.CompletedProcess(["zenity"], 1, "", "")
        manager = SystemResourceManager(
            system_name="Linux",
            which=lambda _name: "/usr/bin/zenity",
            runner=lambda *_args, **_kwargs: command_result,
        )

        self.assertIsNone(manager.select_directory())

    def test_linux_without_system_picker_does_not_fallback_to_web_runtime(self) -> None:
        manager = SystemResourceManager(system_name="Linux", which=lambda _name: None)

        with self.assertRaises(SystemResourceManagerUnavailable):
            manager.select_directory()

    def test_non_directory_result_is_rejected(self) -> None:
        with tempfile.NamedTemporaryFile() as selected:
            command_result = subprocess.CompletedProcess(["osascript"], 0, selected.name, "")
            manager = SystemResourceManager(
                system_name="Darwin",
                which=lambda _name: "/usr/bin/osascript",
                runner=lambda *_args, **_kwargs: command_result,
            )

            with self.assertRaises(SystemResourceManagerError):
                manager.select_directory()

    def test_macos_picker_handles_cancel_inside_system_script(self) -> None:
        manager = SystemResourceManager(
            system_name="Darwin",
            which=lambda _name: "/usr/bin/osascript",
        )

        command = manager._picker_command("Choose")

        self.assertIn("on error number -128", command[-1])
        self.assertIn('return ""', command[-1])

    def test_windows_uses_explorer_shell_com_picker(self) -> None:
        manager = SystemResourceManager(
            system_name="Windows",
            which=lambda name: "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
            if name == "powershell.exe"
            else None,
        )

        command = manager._picker_command("Project's folder")

        self.assertIn("Shell.Application", command[-1])
        self.assertIn("BrowseForFolder", command[-1])
        self.assertIn("Project''s folder", command[-1])


if __name__ == "__main__":
    unittest.main()
