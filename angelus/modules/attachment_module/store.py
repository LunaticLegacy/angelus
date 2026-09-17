"""Bounded, content-addressed image storage; never owns provider objects."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import warnings

from PIL import Image, UnidentifiedImageError


class ImageAttachmentStore:
    """Own one Session's validated, immutable image files.

    Limits are intentionally conservative across supported vision providers.
    Animated files are rejected rather than silently discarding frames.
    """

    MAX_BYTES = 5 * 1024 * 1024
    MAX_PIXELS = 16_000_000
    MAX_ATTACHMENTS = 1000
    _ID = re.compile(r"[0-9a-f]{64}\Z")
    _MEDIA = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}

    def __init__(self, root: str | Path):
        self.root = Path(root).absolute()
        self._reject_symlinks(self.root)
        self._lock = threading.RLock()

    def _ensure_root(self) -> None:
        """Create the storage root only when this Session first stores an image.

        The Session root is shared durable state owned elsewhere; creating it
        eagerly during Session construction would materialize directories that
        a caller may still expect to be absent (for example, on delete).
        """
        with self._lock:
            self._reject_symlinks(self.root)
            self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _reject_symlinks(path: Path) -> None:
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError("Image paths must not contain symlinks")

    def _directory(self, attachment_id: str) -> Path:
        if not isinstance(attachment_id, str) or not self._ID.fullmatch(attachment_id):
            raise ValueError("Invalid image attachment ID")
        target = self.root / attachment_id
        self._reject_symlinks(target)
        if not target.is_dir():
            raise KeyError(attachment_id)
        return target

    @staticmethod
    def _read(path: Path, limit: int) -> bytes:
        ImageAttachmentStore._reject_symlinks(path)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        import stat
        with os.fdopen(os.open(path, flags), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Image input must be a regular file")
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError(f"Image exceeds {limit} byte limit")
        return data

    def put(self, data: bytes, filename: str = "image") -> dict:
        """Validate actual decoded format and publish an immutable attachment."""
        if not data or len(data) > self.MAX_BYTES:
            raise ValueError(f"Image must contain 1–{self.MAX_BYTES} bytes")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    media_type = self._MEDIA.get(image.format)
                    if media_type is None:
                        raise ValueError("Supported images: PNG, JPEG, WebP and GIF")
                    width, height = image.size
                    if width * height > self.MAX_PIXELS or width <= 0 or height <= 0 or max(width, height) > 8000:
                        raise ValueError(f"Image exceeds {self.MAX_PIXELS} pixels or 8000 pixels per side")
                    if getattr(image, "is_animated", False):
                        raise ValueError("Animated images are unsupported; upload one still frame")
                    image.verify()
                with Image.open(io.BytesIO(data)) as image:
                    image.load()
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError("Invalid or unsafe image data") from exc
        attachment_id = hashlib.sha256(data).hexdigest()
        filename = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
        filename = "".join(c for c in filename if c.isprintable())[:200] or "image"
        metadata = dict(attachment_id=attachment_id, media_type=media_type,
                        filename=filename, width=width, height=height, size_bytes=len(data))
        with self._lock:
            self._ensure_root()
            destination = self.root / attachment_id
            if destination.exists() or destination.is_symlink():
                return self.get(attachment_id)
            if sum(1 for p in self.root.iterdir() if self._ID.fullmatch(p.name)) >= self.MAX_ATTACHMENTS:
                raise ValueError("Session image attachment limit reached")
            temporary = Path(tempfile.mkdtemp(prefix=".upload-", dir=self.root))
            try:
                (temporary / "image").write_bytes(data)
                (temporary / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
                try:
                    temporary.rename(destination)
                except OSError:
                    if not destination.exists():
                        raise
                    return self.get(attachment_id)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        return metadata

    def get(self, attachment_id: str) -> dict:
        """Read durable metadata, failing if this Session does not own the ID."""
        directory = self._directory(attachment_id)
        metadata = json.loads(self._read(directory / "metadata.json", 4096))
        if metadata.get("attachment_id") != attachment_id or metadata.get("media_type") not in self._MEDIA.values():
            raise ValueError("Invalid attachment metadata")
        return metadata

    def path(self, attachment_id: str) -> Path:
        """Return a checked local path for the HTTP image response."""
        path = self._directory(attachment_id) / "image"
        self._reject_symlinks(path)
        if not path.is_file():
            raise KeyError(attachment_id)
        return path

    def resolve(self, reference: dict) -> dict:
        """Resolve a durable reference only when preparing a provider request."""
        attachment_id = reference["attachment_id"]
        metadata = self.get(attachment_id)
        if reference.get("media_type", metadata["media_type"]) != metadata["media_type"]:
            raise ValueError("Image reference media type does not match attachment")
        data = self._read(self.path(attachment_id), self.MAX_BYTES)
        if hashlib.sha256(data).hexdigest() != attachment_id:
            raise ValueError("Image attachment integrity check failed")
        return {"media_type": metadata["media_type"], "data": base64.b64encode(data).decode("ascii")}

    def import_file(self, path: str | Path, project_root: str | Path) -> dict:
        """Import a regular image file confined to the granted project root."""
        root = Path(project_root).absolute()
        self._reject_symlinks(root)
        target = Path(path)
        target = target if target.is_absolute() else root / target
        self._reject_symlinks(target)
        target = target.resolve(strict=True)
        if not target.is_relative_to(root.resolve(strict=True)):
            raise ValueError("Image file must be inside the project directory")
        return self.put(self._read(target, self.MAX_BYTES), target.name)
