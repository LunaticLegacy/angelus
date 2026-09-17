"""End-to-end provider payloads: Session store -> resolver -> SDK wire.

This complements ``llmfetcher/tests/test_multimodal.py`` by driving the real
Session-owned ``ImageAttachmentStore.resolve`` through the real OpenAI and
Anthropic handlers into a fake SDK transport.  It proves the durable bytes
exist only at the wire boundary and never leak into request snapshots.
"""
from __future__ import annotations

import base64
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from PIL import Image

from angelus.core import AngelusCore
from llmfetcher.context_handlers.linear import ContextHandlerLinear
from llmfetcher.llm_fetcher import LLMFetcher
from llmfetcher.llm_types import LLMBackendConfig
from llmfetcher.multimodal import UserMessage


def _png() -> bytes:
    """Return one small valid PNG payload.

    Returns:
        Encoded 3x4 red PNG bytes used as the durable attachment body.
    """
    buffer = io.BytesIO()
    Image.new("RGB", (3, 4), "red").save(buffer, format="PNG")
    return buffer.getvalue()


class NativeVisionPayloadTests(unittest.TestCase):
    """Provider wire conversion happens from durable references, not history."""

    def _session(self, directory: str) -> tuple[AngelusCore, object]:
        """Create a Session owning a real attachment store.

        Args:
            directory: Temporary directory owning project and state roots.

        Returns:
            The process core and its registered Session aggregate.
        """
        root = Path(directory)
        (root / "project").mkdir()
        core = AngelusCore(state_root=root / "state")
        core.session_service.create("demo", "Demo", root / "project")
        return core, core.sessions.get("demo")

    def _handler(self, provider: str, resolver):
        """Build a real provider handler with a fake SDK client.

        Args:
            provider: Backend provider name (``openai`` or ``anthropic``).
            resolver: Session-owned ``resolve`` callback for durable refs.

        Returns:
            Tuple of the fetcher, its handler and the backend configuration.
        """
        backend = LLMBackendConfig("fake", provider, "vision-model", api_key="test")
        fetcher = LLMFetcher(backends=[backend], image_resolver=resolver)
        handler = fetcher._handler_for_backend(backend)
        handler.client = MagicMock()
        return fetcher, handler, backend

    def _messages(self, metadata: dict, text: str = "describe") -> tuple[list, dict]:
        """Assemble one user turn referencing an already-stored attachment.

        Args:
            metadata: Attachment metadata returned by the Session store.
            text: Accompanying user text for the turn.

        Returns:
            Provider-neutral messages and the reference they were built from.
        """
        ref = {"attachment_id": metadata["attachment_id"], "media_type": "image/png", "detail": "high"}
        context = ContextHandlerLinear(MagicMock())
        context.add_user_message(UserMessage(text, [ref]))
        return context.build_messages(), ref

    def test_openai_wire_carries_durable_bytes(self) -> None:
        """OpenAI receives a base64 data URL built from the stored bytes."""
        with TemporaryDirectory() as directory:
            _core, session = self._session(directory)
            body = _png()
            metadata = session.attachments.put(body)
            messages, ref = self._messages(metadata)
            _fetcher, handler, _backend = self._handler("openai", session.attachments.resolve)

            handler.create_completion(messages=messages, temperature=0.2, max_tokens=50, stream=False)

            wire = handler.client.chat.completions.create.call_args.kwargs["messages"]
            content = wire[0]["content"]
            self.assertIsInstance(content, list)
            self.assertEqual(content[0], {"type": "text", "text": "describe"})
            image_block = next(block for block in content if block["type"] == "image_url")
            self.assertEqual(
                image_block["image_url"]["url"],
                "data:image/png;base64," + base64.b64encode(body).decode("ascii"),
            )
            self.assertEqual(image_block["image_url"]["detail"], "high")
            # The durable reference travels, the bytes do not.
            self.assertNotIn(base64.b64encode(body).decode("ascii"), json.dumps(messages))

    def test_anthropic_wire_carries_durable_bytes(self) -> None:
        """Anthropic receives a native base64 image source block."""
        with TemporaryDirectory() as directory:
            _core, session = self._session(directory)
            body = _png()
            metadata = session.attachments.put(body)
            messages, _ref = self._messages(metadata)
            _fetcher, handler, _backend = self._handler("anthropic", session.attachments.resolve)

            handler.create_completion(messages=messages, temperature=0.2, max_tokens=50, stream=False)

            wire = handler.client.messages.create.call_args.kwargs["messages"]
            blocks = wire[0]["content"]
            image_block = next(block for block in blocks if block["type"] == "image")
            self.assertEqual(image_block["source"], {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(body).decode("ascii"),
            })

    def test_request_snapshot_stays_byte_free(self) -> None:
        """The prepared request snapshot keeps references and never bytes."""
        with TemporaryDirectory() as directory:
            _core, session = self._session(directory)
            body = _png()
            metadata = session.attachments.put(body)
            messages, ref = self._messages(metadata)
            fetcher, _handler, _backend = self._handler("openai", session.attachments.resolve)

            # Drive the real dispatch-preparation seam with image-bearing
            # messages so the snapshot reflects what the provider would send.
            snapshot = fetcher._prepare_backend_request(
                fetcher.backends["fake"], messages, 0.2, 50, None, False,
            )[1]
            serialized = json.dumps(snapshot.to_dict())
            self.assertNotIn(base64.b64encode(body).decode("ascii"), serialized)
            self.assertEqual(snapshot.messages[0]["images"][0]["attachment_id"], ref["attachment_id"])

    def test_text_only_turn_never_resolves_bytes(self) -> None:
        """A text-only turn keeps a plain string content and calls no resolver."""
        with TemporaryDirectory() as directory:
            _core, session = self._session(directory)
            resolver = MagicMock(wraps=session.attachments.resolve)
            _fetcher, handler, _backend = self._handler("openai", resolver)

            handler.create_completion(
                messages=[{"role": "user", "content": "hello"}],
                temperature=0.2, max_tokens=50, stream=False,
            )

            wire = handler.client.chat.completions.create.call_args.kwargs["messages"]
            self.assertEqual(wire, [{"role": "user", "content": "hello"}])
            resolver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
