"""Coverage for module-owned Composer context sources."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from llmfetcher.context_handlers import (
    ContextBlock,
    ContextComposer,
    ContextPosition,
    ContextSnapshot,
)

from angelus.modules.application_module.context_provider import (
    workspace_context_registration,
)
from angelus.modules.console_module import ConsoleState
from angelus.modules.console_module.context_provider import (
    PlanContextProvider,
    plan_context_registration,
)
from angelus.modules.context_module import (
    ContextProviderRegistration,
    ContextProviderRegistry,
    ContextProviderRequest,
)
from angelus.modules.note_module import note_context_registration
from angelus.modules.session_module import Session, SessionHandler
from angelus.modules.tool_module import ToolPolicy
from angelus.modules.workspace_module import Workspace


class _Source:
    """Minimal provider used to observe registry filtering."""

    def __init__(self, source_id: str) -> None:
        self.provider_id = source_id

    @property
    def source_id(self) -> str:
        return self.provider_id

    def build_blocks(self, snapshot: ContextSnapshot) -> tuple[ContextBlock, ...]:
        return ()


class _Factory:
    """Materialize one named source, whatever the request contains."""

    def __init__(self, source_id: str) -> None:
        self._source_id = source_id

    def build(self, request: ContextProviderRequest) -> tuple[_Source, ...]:
        return (_Source(self._source_id),)


class _HistorySource:
    """Stand-in for the transcript source the Agent registers first."""

    source_id = "history"

    def build_blocks(self, snapshot: ContextSnapshot) -> tuple[ContextBlock, ...]:
        return (ContextBlock(
            role="user",
            content="earlier turn",
            source=self.source_id,
            position=ContextPosition.PREVIOUS,
        ),)


def _session(directory: Path) -> Session:
    return SessionHandler().create("session_plan", execution_root=directory)


def _workspace(directory: Path) -> Workspace:
    return Workspace("session_plan", "plan test", None, directory)


def _request(
    session: Session,
    workspace: Workspace,
    policy: ToolPolicy,
    role: str = "coordinator",
) -> ContextProviderRequest:
    return ContextProviderRequest(session, workspace, policy, role, role)


class PlanContextProviderTests(unittest.TestCase):
    def test_empty_plan_injects_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            console = ConsoleState(Path(directory))
            provider = PlanContextProvider(console, "coordinator")

            self.assertEqual(
                list(provider.build_blocks(ContextSnapshot(handler=None))), []
            )

    def test_plan_block_renders_tree_at_request_tail(self) -> None:
        with TemporaryDirectory() as directory:
            console = ConsoleState(Path(directory))
            console.set_plan("coordinator", "Ship v2", "Keep scope tight", [
                {"id": "build", "title": "Build parser", "subtasks": [
                    {"id": "lex", "title": "Tokenize", "status": "completed"},
                    {"id": "grammar", "title": "Parse", "status": "in_progress"},
                ]},
            ])

            blocks = PlanContextProvider(console, "coordinator").build_blocks(
                ContextSnapshot(handler=None)
            )

            self.assertEqual(len(blocks), 1)
            block = blocks[0]
            self.assertEqual(block.role, "system")
            self.assertEqual(block.position, ContextPosition.SESSION_STATE)
            self.assertIn("<goal>Ship v2</goal>", block.content)
            self.assertIn("<summary>Keep scope tight</summary>", block.content)
            self.assertIn("- [in_progress] build | Build parser", block.content)
            self.assertIn("  - [completed] lex | Tokenize", block.content)
            self.assertEqual(block.metadata["task_count"], 3)
            self.assertFalse(block.metadata["truncated"])

    def test_plan_update_reaches_the_next_request_without_rebuilding(self) -> None:
        with TemporaryDirectory() as directory:
            console = ConsoleState(Path(directory))
            console.set_plan("coordinator", "Ship v2", "", [
                {"id": "build", "title": "Build parser", "status": "in_progress"},
            ])
            provider = PlanContextProvider(console, "coordinator")
            snapshot = ContextSnapshot(handler=None)

            before = provider.build_blocks(snapshot)[0].content
            console.update_task_status("coordinator", "build", "completed")
            after = provider.build_blocks(snapshot)[0].content

            self.assertIn("[in_progress]", before)
            self.assertIn("- [completed] build", after)

    def test_truncation_is_declared_in_content_and_metadata(self) -> None:
        with TemporaryDirectory() as directory:
            console = ConsoleState(Path(directory))
            console.set_plan("coordinator", "Ship v2", "", [
                {"id": f"task-{index}", "title": "x" * 80} for index in range(40)
            ])

            block = PlanContextProvider(
                console, "coordinator", max_characters=1_000,
            ).build_blocks(ContextSnapshot(handler=None))[0]

            self.assertTrue(block.metadata["truncated"])
            self.assertIn("<truncated shown=", block.content)
            self.assertLessEqual(len(block.content), 1_100)
            task_count = block.metadata["task_count"]
            if not isinstance(task_count, int):
                self.fail("task_count must be an integer")
            self.assertLess(task_count, 40)


class ContextProviderRegistryTests(unittest.TestCase):
    def test_duplicate_registration_is_rejected(self) -> None:
        registry = ContextProviderRegistry()
        registry.register(ContextProviderRegistration("duplicate", _Factory("duplicate")))

        with self.assertRaises(ValueError):
            registry.register(
                ContextProviderRegistration("duplicate", _Factory("duplicate"))
            )

    def test_empty_registration_identity_is_rejected(self) -> None:
        registry = ContextProviderRegistry()

        with self.assertRaises(ValueError):
            registry.register(ContextProviderRegistration(" ", _Factory("blank")))

    def test_roles_and_tool_gates_filter_registrations(self) -> None:
        registry = ContextProviderRegistry()
        registry.register(ContextProviderRegistration("all", _Factory("all")))
        registry.register(ContextProviderRegistration(
            "workers", _Factory("workers"), roles=frozenset({"worker"}),
        ))
        registry.register(ContextProviderRegistration(
            "gated",
            _Factory("gated"),
            gates=(("planning", "read_task_plan"),),
        ))
        with TemporaryDirectory() as directory:
            session = _session(Path(directory))
            workspace = _workspace(Path(directory))
            denied = ToolPolicy(frozenset(), frozenset())
            granted = ToolPolicy(
                frozenset({"planning"}), frozenset({"read_task_plan"}),
            )

            def materialized(policy: ToolPolicy, role: str) -> list[str]:
                return [
                    provider.provider_id
                    for provider in registry.materialize(
                        _request(session, workspace, policy, role)
                    )
                ]

            self.assertEqual(materialized(denied, "coordinator"), ["all"])
            self.assertEqual(
                materialized(granted, "coordinator"), ["all", "gated"]
            )
            self.assertEqual(
                materialized(granted, "worker"), ["all", "workers", "gated"]
            )

    def test_shipped_registrations_follow_the_planning_grant(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            session = _session(root)
            assert session.console is not None
            session.console.set_plan("coordinator", "Ship v2", "", [
                {"id": "build", "title": "Build parser"},
            ])
            registry = ContextProviderRegistry()
            for registration in (
                workspace_context_registration(),
                note_context_registration(root),
                plan_context_registration(),
            ):
                registry.register(registration)
            granted = ToolPolicy(
                frozenset({"planning"}), frozenset({"read_task_plan"}),
            )

            self.assertEqual(
                [provider.source_id for provider in registry.materialize(
                    _request(session, _workspace(root), granted)
                )],
                ["angelus.workspace", "angelus.notes", "angelus.plan"],
            )
            self.assertEqual(
                [provider.source_id for provider in registry.materialize(
                    _request(session, _workspace(root), ToolPolicy(frozenset(), frozenset()))
                )],
                ["angelus.workspace", "angelus.notes"],
            )

    def test_plan_sits_after_workspace_and_before_history(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            session = _session(root)
            assert session.console is not None
            session.console.set_plan("coordinator", "Ship v2", "", [
                {"id": "build", "title": "Build parser"},
            ])
            registry = ContextProviderRegistry()
            registry.register(workspace_context_registration())
            registry.register(plan_context_registration())
            providers = registry.materialize(_request(
                session,
                _workspace(root),
                ToolPolicy(frozenset({"planning"}), frozenset({"read_task_plan"})),
            ))

            rows = ContextComposer((*providers, _HistorySource())).describe(
                snapshot=ContextSnapshot(handler=None)
            )

            self.assertEqual(
                [row["source"] for row in rows],
                ["angelus.workspace", "angelus.plan", "history"],
            )


if __name__ == "__main__":
    unittest.main()
