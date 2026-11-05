"""Structural guard: the swarm graph has one read and one write adapter."""
from pathlib import Path
import unittest
from unittest.mock import Mock

from angelus.modules.application_module.swarm_graph_service import _rollback_failures


class SwarmGraphSinglePathTests(unittest.TestCase):
    """Ensure console and execution adapters never bypass the gateway."""

    def test_adapters_do_not_bypass_the_gateway(self) -> None:
        """Only SwarmGraphService may read or mutate live topology directly."""
        modules = Path(__file__).resolve().parent.parent / "angelus" / "modules"
        projection_package = modules / "console_module" / "projection_service"
        projection = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(projection_package.glob("*.py"))
        )
        tools = (modules / "console_module" / "console_tools.py").read_text(encoding="utf-8")
        execution = (modules / "application_module" / "execution_service.py").read_text(encoding="utf-8")

        forbidden = (
            (projection, ["view_snapshot(", "dynamic_get_info("]),
            (tools, [
                "view_snapshot(",
                "dynamic_get_info(",
                "self._session.console.add_worker(",
                "self._session.console.remove_worker(",
                "self._session.console.add_connection(",
                "self._session.console.remove_connection(",
                "self._session.console.mapper(",
                "self._session.console.router(",
            ]),
            (execution, ["view_snapshot("]),
        )
        for text, tokens in forbidden:
            for token in tokens:
                self.assertNotIn(token, text)

    def test_rollback_reports_restore_and_cleanup_failures(self) -> None:
        console = Mock()
        console.replace.side_effect = RuntimeError("restore failed")

        failures = _rollback_failures(
            console,
            object(),
            lambda: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
        )

        self.assertEqual([str(error) for error in failures], ["restore failed", "cleanup failed"])


if __name__ == "__main__":
    unittest.main()
