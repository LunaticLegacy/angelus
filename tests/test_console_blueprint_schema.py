"""Schema symmetry between ConsoleBlueprint.to_json and from_json."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from angelus.modules.console_module.console_state import (
    ConnectionBlueprint,
    ConsoleBlueprint,
    ConsoleDomainError,
    ConsoleState,
    PlanExecution,
    PlanItem,
    TaskPlan,
    WorkerBlueprint,
)


class ConsoleBlueprintRoundTripTests(unittest.TestCase):
    def test_round_trip_preserves_every_written_field(self) -> None:
        blueprint = ConsoleBlueprint(
            workers={
                "worker": WorkerBlueprint("worker", "stay focused", "mapper"),
                "reviewer": WorkerBlueprint("reviewer", role="reviewer"),
            },
            connections=[ConnectionBlueprint("coordinator", "worker")],
            mappers={"worker": "json"},
            routers={"worker": ["reviewer"]},
            plans={
                "coordinator": TaskPlan(
                    goal="ship",
                    summary="one step",
                    tasks=(
                        PlanItem(
                            id="t1",
                            title="write the codec",
                            description="strict decode",
                            status="in_progress",
                            priority="high",
                            estimated_minutes=12.5,
                            subtasks=(PlanItem(id="t1.1", title="add role"),),
                            execution=PlanExecution(
                                assignment_ids=("a1",),
                                active_assignment_id="a1",
                                updated_at="2026-10-21T00:00:00+00:00",
                            ),
                        ),
                    ),
                    updated_at="2026-10-21T00:00:00+00:00",
                )
            },
        )

        decoded = ConsoleBlueprint.from_json(json.loads(json.dumps(blueprint.to_json())))

        self.assertEqual(decoded, blueprint)
        self.assertEqual(decoded.workers["worker"].role, "mapper")
        self.assertEqual(decoded.workers["reviewer"].role, "reviewer")
        self.assertEqual(decoded.plans["coordinator"].tasks[0].subtasks[0].id, "t1.1")

    def test_role_survives_a_real_disk_round_trip(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = ConsoleState(root)
            state.replace(
                ConsoleBlueprint(
                    workers={"worker": WorkerBlueprint("worker", "role test", "mapper")}
                )
            )

            reopened = ConsoleState(root)

            self.assertEqual(reopened.blueprint().workers["worker"].role, "mapper")
            document = json.loads((root / "console" / "state.json").read_text("utf-8"))
            self.assertEqual(document["schema_version"], 2)

    def test_legacy_v1_flat_plan_keeps_its_owner(self) -> None:
        decoded = ConsoleBlueprint.from_json(
            {
                "workers": {},
                "connections": [],
                "mappers": {},
                "routers": {},
                "plan": [
                    {"id": "t1", "title": "owned", "agent": "worker"},
                    {"id": "t2", "title": "unowned"},
                ],
            }
        )

        self.assertNotIn("plan", decoded.to_json())
        self.assertEqual(
            [item.id for item in decoded.plans["worker"].tasks], ["t1"]
        )
        self.assertEqual(
            [item.id for item in decoded.plans["coordinator"].tasks], ["t2"]
        )


class ConsoleBlueprintRejectionTests(unittest.TestCase):
    def test_unknown_top_level_field_is_rejected(self) -> None:
        with self.assertRaises(ConsoleDomainError):
            ConsoleBlueprint.from_json({"schema_version": 2, "workers": {}, "extra": 1})

    def test_unsupported_schema_version_is_rejected(self) -> None:
        with self.assertRaises(ConsoleDomainError):
            ConsoleBlueprint.from_json({"schema_version": 3})

    def test_worker_name_must_match_its_key(self) -> None:
        with self.assertRaises(ConsoleDomainError):
            ConsoleBlueprint.from_json(
                {"schema_version": 2, "workers": {"a": {"name": "b"}}}
            )

    def test_unknown_worker_field_is_rejected(self) -> None:
        with self.assertRaises(ConsoleDomainError):
            ConsoleBlueprint.from_json(
                {"schema_version": 2, "workers": {"a": {"unknown": True}}}
            )

    def test_unsupported_task_status_is_rejected(self) -> None:
        with self.assertRaises(ConsoleDomainError):
            ConsoleBlueprint.from_json(
                {
                    "schema_version": 2,
                    "plans": {
                        "coordinator": {
                            "tasks": [{"id": "t1", "status": "finished"}]
                        }
                    },
                }
            )

    def test_corrupt_document_isolated_before_raising(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "console").mkdir()
            path = root / "console" / "state.json"
            path.write_text(
                '{"schema_version": 9}', encoding="utf-8"
            )

            with self.assertRaises(ConsoleDomainError):
                ConsoleState(root)

            self.assertFalse(path.exists())
            quarantined = list((root / "console").glob("state.json.corrupt-*"))
            self.assertEqual(len(quarantined), 1)
            self.assertEqual(quarantined[0].read_text("utf-8"), '{"schema_version": 9}')


if __name__ == "__main__":
    unittest.main()
