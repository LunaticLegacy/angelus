"""Regression coverage for the CLI state-root contract."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

from angelus.cli import _configure_state_root


def test_cli_state_dir_synchronizes_plugin_and_registry_roots() -> None:
    """``--state-dir`` must give the CLI one application root for both stores."""
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory) / "workspace"
        with mock.patch.dict(os.environ, {}, clear=True):
            _configure_state_root(str(workspace))

            expected = str(workspace.resolve())
            assert os.environ["ANGELUS_STATE_DIR"] == expected
            assert os.environ["LLMFETCHER_STATE_DIR"] == expected


def test_cli_state_dir_leaves_environment_untouched_when_omitted() -> None:
    """The source-checkout default remains available without an explicit flag."""
    with mock.patch.dict(os.environ, {"ANGELUS_STATE_DIR": "/kept"}, clear=True):
        _configure_state_root(None)
        assert os.environ["ANGELUS_STATE_DIR"] == "/kept"
