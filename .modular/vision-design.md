# Native vision input — 2026-09-17

## Problem and compatibility
Provide durable, local-first image inputs for OpenAI Chat Completions and
Anthropic Messages. Preserve existing text-only callers and saved contexts.
Images are not OCR summaries. No image generation or arbitrary remote URL fetch.
No Responses API migration, provider file upload, or automatic model selection.

## Boundaries and contracts
- `llmfetcher.multimodal`: provider-neutral `ImageReference` (JSON dict with
  attachment_id, media_type, optional detail auto/low/high) and `UserMessage`
  (text plus image references). `LLMContext.content` remains text and gains
  `images` with an empty default. Tool results may carry a typed
  `ImageToolResult(text, images)`; never stringify these before preservation.
- `llmfetcher` context owns durable references and archive preservation.
  Agent/Swarm accept UserMessage while existing strings remain valid. Image
  references survive checkpoint reload. Compaction includes reference markers,
  never base64; archives retain images and tools can reopen them by ID.
- Fetcher receives `image_resolver(reference) -> {media_type, data}` callback;
  data is base64, resolved only at provider request preparation. Provider
  handlers own wire conversion, including tool-result image semantics. OpenAI
  uses image_url data URLs, Anthropic image/source blocks. Unsupported
  providers reject image input rather than flattening it. Request previews and
  persisted request events must not contain image bytes.
- `attachment_module`: immutable Session-owned local image blobs and metadata;
  MIME/decode/size/dimension validation, bounded reads, opaque content IDs,
  confined project-file import. Owns image bytes, never provider SDK objects.
  `ImageAttachmentStore(root)` provides put(bytes, filename), get(id),
  resolve(reference), import_file(path, project_root). Metadata includes
  attachment_id, media_type, filename, width, height, size_bytes.
- HTTP: POST `/api/sessions/{id}/attachments/images`, raw bytes plus filename
  query, returns metadata with `url`; GET same prefix `/{attachment_id}` serves
  validated image. RunRequest gains `images: list[ImageReference]`, default [];
  text may be empty only when images exist. History messages gain images with
  Session URLs. Session owns store; application validates refs before running.
- Agent `view_image(attachment_id='', path='')` returns ImageToolResult.
  Attachment-ID reads are same-Session only; project path imports require an
  explicit vision tool grant and remain project-confined. Worker factories
  receive the same Session resolver; no cross-Session implicit access.
- Frontend owns draft images, upload/paste/drop/remove and previews, sending
  IDs only. Draft state is isolated across Session switches. Text-only steer
  remains supported; image steering is explicitly rejected in this iteration.

## Dependency graph and semantics
frontend -> HTTP -> application -> attachment_module -> filesystem/Pillow
application -> llmfetcher; attachment_tool_provider -> attachment_module
attachment_tool_provider -> llmfetcher multimodal contracts
llmfetcher context -> multimodal contracts
llmfetcher fetcher -> provider handlers -> multimodal contracts
llmfetcher -> injected image resolver (no Angelus imports)
No reverse edges; image bytes have a single owner; transport owns no store.
Deleting attachment module removes image I/O but leaves text runtime intact.
Replacing filesystem storage preserves resolver/API contracts.

## Validation
PASS: dependency direction is acyclic, ownership unique, provider formats
stay at handler boundary, text context stays compatible, image bytes are not
journaled. Required independent review before implementation completion.

## Implementation plan
1. runtime: llmfetcher multimodal/types/context/agent/swarm/fetcher/handlers and
   tests/index; forbid Angelus/frontend edits. Test both wire formats, streaming
   and normal calls, reload/archive, tool images, unsupported backend rejection.
2. attachments: angelus/modules/attachment_module, API attachments, tests,
   pyproject dependency; no frontend or llmfetcher implementation changes.
   Test real image decoding, bounds, traversal, MIME, restart and isolation.
3. integration: Session/factory/execution/API/core/tool registry/projections;
   depends on 1+2. Preserve context exchange/revisions safely with image refs.
4. frontend: app.js/css, templates, new image composer, chat renderer; depends
   on stable API contract. Test upload failure, session switch and image-only
   send; preserve text streaming. No backend edits.
5. verification/docs: run suites, inspect SDK request payloads with fake
   transports, update indexes and official-source implementation notes. Live
   paid requests are not required to validate transport contracts.

## Official sources
- https://developers.openai.com/api/docs/guides/images-vision
- https://platform.claude.com/docs/en/build-with-claude/vision
