"""ONNX Runtime GenAI handler for decoder-only LLMs."""

from __future__ import annotations

import ctypes
import json
import os
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence, TypeAlias


# ── Pre-load CUDA compat libraries (no env var pollution) ───────────────
# onnxruntime-genai was compiled against CUDA 12 but the system may have
# CUDA 13.  The nvidia-*-cu12 pip packages provide the CUDA 12 .so files
# inside site-packages/nvidia/.  Pre-load them with RTLD_GLOBAL so that
# onnxruntime-genai's dlopen("libcublasLt.so.12") finds them without
# needing LD_LIBRARY_PATH, symlinks, or system-level changes.
def _ensure_cuda_runtime() -> bool:
    """Pre-load CUDA 12 compat .so files from nvidia pip packages.

    Returns True if any libraries were loaded, False otherwise.
    """
    try:
        import nvidia.cublas  # noqa: F811
        import nvidia.cuda_runtime  # noqa: F811
        import nvidia.cufft  # noqa: F811
        import nvidia.cudnn  # noqa: F811
    except ImportError:
        return False

    loaded = False
    for mod in (nvidia.cublas, nvidia.cuda_runtime, nvidia.cufft, nvidia.cudnn):  # noqa: F821
        mod_dir = mod.__path__[0]
        lib_dir = os.path.join(mod_dir, "lib")
        if not os.path.isdir(lib_dir):
            continue
        for entry in sorted(os.listdir(lib_dir)):
            if not (entry.endswith(".so") or ".so." in entry):
                continue
            try:
                ctypes.CDLL(os.path.join(lib_dir, entry), mode=ctypes.RTLD_GLOBAL)
                loaded = True
            except OSError:
                pass
    return loaded

from ..llm_types import LLMBackendConfig, LLMOutput, TokenUsage
from ._tool_schemas import to_openai_tool_schemas
from .base import LLMBackendHandler, ToolDefinition, ToolSchema


# ── Internal types ──────────────────────────────────────────────────────


JSONValue: TypeAlias = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]
StreamQueueItem: TypeAlias = str | BaseException


class _StreamSentinel:
    pass


@dataclass
class _ONNXCompletionResponse:
    """Lightweight container returned by non-streaming create_completion."""

    content: str
    raw: str = ""
    usage: JSONObject = field(default_factory=dict)
    stop_reason: Optional[str] = None


# ── Device resolution ───────────────────────────────────────────────────


def _resolve_model_options(device: str) -> dict[str, Any]:
    """Map a human-readable device name to onnxruntime-genai model options.

    Supported device values (case-insensitive):
      - ``"cpu"`` (default)   → CPU execution provider
      - ``"cuda"``, ``"gpu"`` → CUDA EP (NVIDIA GPU)
      - ``"GPU.0"``, ``"GPU.1"``, etc. → CUDA EP with specific device_id
    """
    normalized = device.strip().lower()

    # Match patterns like "gpu.0", "gpu.1", "cuda:0", etc.
    device_id = 0
    if "." in normalized:
        parts = normalized.split(".")
        normalized = parts[0]
        try:
            device_id = int(parts[1])
        except (ValueError, IndexError):
            pass
    elif ":" in normalized:
        parts = normalized.split(":")
        normalized = parts[0]
        try:
            device_id = int(parts[1])
        except (ValueError, IndexError):
            pass

    if normalized in ("cuda", "gpu"):
        return {"provider": "cuda", "device_id": device_id}
    # CPU fallback
    return {"provider": "cpu"}


def _resolve_search_options(
    temperature: float,
    max_tokens: int,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build the search-options dict passed to ``GeneratorParams.set_search_options``."""
    options: dict[str, Any] = dict(extra or {})
    options.setdefault("max_length", max_tokens)
    options.setdefault("temperature", temperature)

    if temperature > 0:
        options.setdefault("do_sample", True)
    else:
        options["do_sample"] = False

    return options


# ── Handler ─────────────────────────────────────────────────────────────


class OnnxRuntimeGenAIHandler(LLMBackendHandler):
    """Backend handler for decoder-only LLMs via onnxruntime-genai.

    Uses ``onnxruntime_genai.Model``, ``Tokenizer``, and ``Generator``
    under the hood.  Supports CPU and CUDA execution providers.

    Provider names
    --------------
    - ``"onnxruntime"``
    - ``"ort"``

    Expected ``LLMBackendConfig`` fields
    ------------------------------------
    ``model`` (or ``extra["model_path"]``)
        Path to the onnxruntime-genai model directory containing
        ``model.onnx``, ``genai_config.json``, and tokenizer files.
    ``extra["device"]``
        ``"cpu"``, ``"cuda"``, or ``"gpu"`` (default ``"cpu"``).
    ``extra["generation_config"]``
        Optional dict of search options forwarded to
        ``GeneratorParams.set_search_options``.
    """

    provider_names = frozenset({"onnxruntime", "ort"})

    def __init__(self, fetcher, backend: LLMBackendConfig) -> None:
        super().__init__(fetcher, backend)

        _ensure_cuda_runtime()
        import onnxruntime_genai as ort_genai

        model_path = backend.extra.get("model_path") or backend.api_url or backend.model
        device = backend.extra.get("device", "cpu")
        model_options = _resolve_model_options(device)

        self.ort_genai = ort_genai
        config = ort_genai.Config(str(model_path))
        provider = model_options.get("provider", "cpu")
        device_id = model_options.get("device_id", 0)
        if provider != "cpu":
            config.append_provider(provider)
            config.set_provider_option(provider, "device_id", str(device_id))
        self.model = ort_genai.Model(config)
        self.tokenizer = ort_genai.Tokenizer(self.model)
        self._tokenizer_stream = self.tokenizer.create_stream()

    # ── Tool schema preparation ─────────────────────────────────────────

    def prepare_tools(
        self,
        tools: Optional[Sequence[ToolDefinition]],
    ) -> Optional[list[ToolSchema]]:
        return to_openai_tool_schemas(tools)

    # ── Chat history ────────────────────────────────────────────────────

    def build_chat_history(
        self,
        messages: list[dict[str, str]],
        tools: Optional[list[ToolSchema]] = None,
    ) -> list[dict[str, str]]:
        """Return messages as-is; the tokenizer's built-in chat template
        handles the formatting during ``tokenizer.encode_chat()``."""
        _ = tools  # onnxruntime-genai does not inject tools into chat history
        return messages

    # ── Generation config ───────────────────────────────────────────────

    def generation_config(
        self,
        *,
        temperature: float,
        max_tokens: int,
    ) -> JSONObject:
        base = dict(self.backend.extra.get("generation_config") or {})
        base.update(
            _resolve_search_options(
                temperature=temperature,
                max_tokens=max_tokens,
                extra=base,
            )
        )
        return base

    # ── Completion (entry point) ────────────────────────────────────────

    def create_completion(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        stream: bool,
        tools: Optional[list[ToolSchema]] = None,
    ):
        history = self.build_chat_history(messages, tools=tools)
        config = self.generation_config(temperature=temperature, max_tokens=max_tokens)

        # Encode the chat into input token IDs using the model's chat template.
        # onnxruntime-genai 0.14.x split encode_chat into apply_chat_template + encode
        prompt = self.tokenizer.apply_chat_template(json.dumps(history))
        input_ids = self.tokenizer.encode(prompt)

        # Build generator parameters.
        params = self.ort_genai.GeneratorParams(self.model)
        params.set_search_options(**config)

        if stream:
            return self._create_stream(input_ids, params)

        return self._create_completion_blocking(input_ids, params)

    def _create_completion_blocking(self, input_ids, params) -> _ONNXCompletionResponse:
        """Generate the full output sequence without streaming."""
        generator = self.ort_genai.Generator(self.model, params)
        generator.append_tokens(input_ids)
        while not generator.is_done():
            generator.generate_next_token()
        output_ids = generator.get_sequence(0)
        content = self.tokenizer.decode(output_ids)

        return _ONNXCompletionResponse(content=content)

    # ── Streaming ───────────────────────────────────────────────────────

    def _create_stream(self, input_ids, params) -> Iterable[str]:
        """Yield text chunks as they are generated, via a background thread."""
        items: queue.Queue[StreamQueueItem | _StreamSentinel] = queue.Queue(maxsize=10)
        sentinel = _StreamSentinel()

        def _worker() -> None:
            try:
                generator = self.ort_genai.Generator(self.model, params)
                generator.append_tokens(input_ids)
                while not generator.is_done():
                    generator.generate_next_token()
                    token_ids = generator.get_next_tokens()
                    chunk = ""
                    for tid in token_ids:
                        chunk += self._tokenizer_stream.decode(tid.item())
                    if chunk:
                        items.put(chunk, block=True)
            except BaseException as exc:
                items.put(exc, block=True)
            finally:
                items.put(sentinel, block=True)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        while True:
            item = items.get()
            if item is sentinel:
                break
            if isinstance(item, BaseException):
                raise item
            yield str(item)

    # ── Response normalisation ──────────────────────────────────────────

    def normalize_completion_response(self, response) -> LLMOutput:
        return LLMOutput(
            content=self._coerce_content_to_text(
                self._read_field(response, "content", response)
            ),
            provider=self.backend.provider,
            backend_name=self.backend.name,
            model=self.backend.model,
            role="assistant",
            stop_reason=self._read_field(response, "stop_reason", None),
            usage=self.normalize_usage(self._read_field(response, "usage", None)),
        )

    def iter_stream_text(self, response, *, output_reasoning: bool) -> Iterable[str]:
        for chunk in response:
            if isinstance(chunk, str):
                if chunk:
                    yield chunk
            else:
                text = str(chunk)
                if text:
                    yield text
