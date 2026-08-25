"""Regression tests for reusing one completed Swarm run holder."""

from __future__ import annotations

import unittest

from angelus.classes import ActiveRun, BrowserRunControl


class ActiveRunReuseTests(unittest.TestCase):
    """Ensure persistent Swarm callbacks keep a valid control object."""

    def test_reset_for_next_turn_preserves_control_identity_and_clears_state(self) -> None:
        """Reuse must not invalidate tool closures holding ``force_stopped``."""
        active = ActiveRun(control=BrowserRunControl())
        control = active.control
        force_event = control.force_stopped
        active.control.steer("stale steer")
        active.control.force_stop()
        active.events.put({"event": "old"})
        active.done.set()

        active.reset_for_next_turn()

        self.assertIs(active.control, control)
        self.assertIs(active.control.force_stopped, force_event)
        self.assertFalse(active.done.is_set())
        self.assertFalse(active.control.should_stop())
        self.assertFalse(force_event.is_set())
        self.assertEqual(active.control.drain_steers(), [])
        self.assertTrue(active.events.empty())

    def test_reset_rejects_a_still_running_holder(self) -> None:
        """An in-flight run cannot be reset into a competing execution turn."""
        active = ActiveRun(control=BrowserRunControl())
        with self.assertRaisesRegex(RuntimeError, "active"):
            active.reset_for_next_turn()

    def test_stream_fragment_is_marked_live_only(self) -> None:
        """Keep provider deltas out of the durable-event persistence path."""
        active = ActiveRun(control=BrowserRunControl())
        active.publish_ephemeral_event({"type": "agent:stream_delta"})
        self.assertEqual(
            active.events.get_nowait(),
            {"type": "agent:stream_delta", "ephemeral": True},
        )


if __name__ == "__main__":
    unittest.main()
