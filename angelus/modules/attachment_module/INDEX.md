# attachment_module/ — Session Image Attachment INDEX

This module owns one Session's immutable, validated image blobs and their
metadata under the Session execution root. It never holds provider SDK objects,
never reads outside a granted project directory, and never exposes image bytes
to Agent context; models receive durable attachment references only. Deleting
this module removes image I/O while leaving the text-only runtime intact.

| File | Responsibility |
|---|---|
| `store.py` | Content-addressed `ImageAttachmentStore`: bounded decode/format/dimension validation, symlink-safe bounded reads, confined project-file import and immutable metadata. |
| `tool_provider.py` | `ImageToolProvider` and `image_tool_registration`; materialize the authorized `view_image` Tool returning a typed `ImageToolResult`. |
| `__init__.py` | Public store and registration exports. |

## Runtime Boundary

`AngelusCore` registers `image_tool_registration` once as provider `vision`.
The provider materializes the `view_image` Tool for the Coordinator and Worker
roles only when the Session `ToolPolicy` grants both the `vision` category and
the `view_image` Tool, and only when the owning Session has attached its
durable `attachments` store and `execution` root. Attachment-ID reads resolve
solely inside the requesting Session; `path=` imports stay confined to the
Session's granted project directory. Bytes are resolved lazily through
`store.resolve(reference)` only while preparing a provider request, so
journals, checkpoints, previews and request events retain references, never
base64.

The HTTP transport lives in `angelus/api/attachments.py`, which serves the
Session-owned store and owns no storage itself.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [store.py](store.py#L38) | `ImageAttachmentStore._ensure_root` | `None` | `None` | Create the storage root only when this Session first stores an image. |
| [store.py](store.py#L50) | `ImageAttachmentStore._reject_symlinks` | `path: Path` | `None` | Implement `ImageAttachmentStore._reject_symlinks`. |
| [store.py](store.py#L54) | `ImageAttachmentStore._directory` | `attachment_id: str` | `Path` | Implement `ImageAttachmentStore._directory`. |
| [store.py](store.py#L64) | `ImageAttachmentStore._read` | `path: Path, limit: int` | `bytes` | Implement `ImageAttachmentStore._read`. |
| [store.py](store.py#L76) | `ImageAttachmentStore.put` | `data: bytes, filename: str` | `dict` | Validate actual decoded format and publish an immutable attachment. |
| [store.py](store.py#L124) | `ImageAttachmentStore.get` | `attachment_id: str` | `dict` | Read durable metadata, failing if this Session does not own the ID. |
| [store.py](store.py#L132) | `ImageAttachmentStore.path` | `attachment_id: str` | `Path` | Return a checked local path for the HTTP image response. |
| [store.py](store.py#L140) | `ImageAttachmentStore.resolve` | `reference: dict` | `dict` | Resolve a durable reference only when preparing a provider request. |
| [store.py](store.py#L151) | `ImageAttachmentStore.import_file` | `path: str \| Path, project_root: str \| Path` | `dict` | Import a regular image file confined to the granted project root. |
| [tool_provider.py](tool_provider.py#L24) | `ImageToolProvider.materialize` | `session: 'Session', policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Implement `ImageToolProvider.materialize`. |
| [tool_provider.py](tool_provider.py#L61) | `image_tool_registration` | `core: 'AngelusCore'` | `ToolProviderRegistration` | Implement `image_tool_registration`. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [store.py](store.py#L20) | `ImageAttachmentStore` | `root: str \| Path` | `object` | Own one Session's validated, immutable image files. |
| [tool_provider.py](tool_provider.py#L18) | `ImageToolProvider` | `core: 'AngelusCore'` | `object` | Expose native image results without filesystem or provider leakage. |

<!-- END GENERATED SYMBOL MAP -->
