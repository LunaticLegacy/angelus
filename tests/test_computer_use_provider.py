import io
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from angelus.modules.attachment_module import ImageAttachmentStore
from angelus.modules.computer_use_module import ComputerUseProvider, ScreenCapture
from angelus.modules.tool_module import ToolPolicy


class FakeBackend:
    def __init__(self):
        self.calls = []

    def screenshot(self):
        output = io.BytesIO()
        Image.new("RGB", (8, 6), "blue").save(output, format="PNG")
        return ScreenCapture(output.getvalue(), 8, 6)

    def screen_size(self):
        return (8, 6)

    def click(self, x, y, button="left"): self.calls.append(("click", x, y, button))
    def double_click(self, x, y, button="left"): self.calls.append(("double_click", x, y, button))
    def type_text(self, text): self.calls.append(("type", text))
    def press_key(self, key): self.calls.append(("key", key))
    def scroll(self, dx=0, dy=0): self.calls.append(("scroll", dx, dy))


class ComputerUseProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.backend = FakeBackend()
        self.store = ImageAttachmentStore(self.tmp / "attachments")
        workspace = SimpleNamespace(project_path=None)
        core = SimpleNamespace(workspaces=SimpleNamespace(get=lambda _sid: workspace))
        self.provider = ComputerUseProvider(core, self.backend)
        self.session = SimpleNamespace(attachments=self.store, execution=SimpleNamespace(session_id="s1"))
        self.policy = ToolPolicy(frozenset({"vision"}), frozenset({"computer"}))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_requires_explicit_permission(self):
        self.assertEqual(self.provider.materialize(self.session, ToolPolicy(frozenset({"vision"}), frozenset()), "coordinator"), [])

    def test_screenshot_is_stored_as_native_image_result(self):
        tool = self.provider.materialize(self.session, self.policy, "coordinator")[0]
        result = tool.handler(action="screenshot")
        self.assertEqual(result.images[0]["media_type"], "image/png")
        self.assertEqual(self.store.get(result.images[0]["attachment_id"])["width"], 8)

    def test_actions_are_dispatched_and_coordinates_are_checked(self):
        tool = self.provider.materialize(self.session, self.policy, "worker")[0]
        tool.handler(action="click", x=1, y=2)
        tool.handler(action="type", text="hello")
        tool.handler(action="key", key="ENTER")
        tool.handler(action="scroll", dy=-3)
        self.assertEqual(self.backend.calls, [("click", 1, 2, "left"), ("type", "hello"), ("key", "ENTER"), ("scroll", 0, -3)])
        with self.assertRaisesRegex(ValueError, "outside"):
            tool.handler(action="click", x=8, y=0)


if __name__ == "__main__":
    unittest.main()
