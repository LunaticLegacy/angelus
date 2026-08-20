"""Executable entry point for the Tauri Python sidecar."""

import os
import sys


# PyInstaller exposes bundled data through ``_MEIPASS``; source execution
# continues to use the repository's normal frontend directory.
if hasattr(sys, "_MEIPASS"):
    os.environ.setdefault("ANGELUS_FRONTEND_ROOT", os.path.join(sys._MEIPASS, "frontend"))
    os.environ.setdefault("ANGELUS_BUNDLED_PLUGIN_ROOT", os.path.join(sys._MEIPASS, "starter-plugins"))

from angelus.cli import main


if __name__ == "__main__":
    main(["web", *(__import__("sys").argv[1:])])
