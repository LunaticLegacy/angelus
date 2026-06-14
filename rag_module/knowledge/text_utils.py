"""Text normalization helpers shared by knowledge-base components."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Sequence

from markdown_it import MarkdownIt
from markdown_it.token import Token

from .models import KnowledgeChunk, KnowledgeDocument, MarkdownBlock


class TextTools:
    """Provides reusable text extraction and excerpt helpers.

    This class contains pure text-processing behavior so loaders, retrievers,
    and vector stores do not duplicate regular expressions or excerpt rules.
    """

    def __init__(self, *, excerpt_chars: int, embedding_max_chars: int, chunk_max_chars: int) -> None:
        """Initialize text helper limits.

        Args:
            excerpt_chars: Maximum number of characters returned by excerpts.
            embedding_max_chars: Maximum number of normalized content characters
                included in semantic documents.
            chunk_max_chars: Maximum size of a single markdown chunk in
                characters before a new chunk is started.
        """
        # Store limits from configuration so all text helpers share the same
        # truncation behavior as the original monolithic implementation.
        self.excerpt_chars = excerpt_chars
        self.embedding_max_chars = embedding_max_chars
        self.chunk_max_chars = max(256, chunk_max_chars)
        self._markdown = MarkdownIt("commonmark", {"html": True, "linkify": True}).enable("table")

    def extract_terms(self, values: Sequence[str]) -> list[str]:
        """Extract normalized keyword terms from arbitrary text values.

        The method preserves the old tokenization rule: ASCII technical tokens
        and contiguous Chinese phrases of length at least two are retained.

        Args:
            values: Text values whose terms should be merged and deduplicated in
                first-seen order.

        Returns:
            A list of lowercase unique search terms.
        """

        # Maintain deterministic ordering by using a list for output and a set
        # only for membership checks.
        terms: list[str] = []
        seen: set[str] = set()

        # Walk each input independently so empty or None-like strings are simply
        # ignored without affecting the rest of the query.
        for value in values:
            for raw_term in re.findall(r'[A-Za-z0-9_./+-]+|[\u4e00-\u9fff]{2,}', value or ''):
                term = raw_term.strip().lower()
                if len(term) < 2 or term in seen:
                    continue
                seen.add(term)
                terms.append(term)

        # Return only unique meaningful terms, preserving compatibility with the
        # previous keyword scoring behavior.
        return terms

    def build_excerpt(self, content: str, terms: Sequence[str]) -> str:
        """Build a short excerpt from Markdown content.

        The method first prefers a non-heading block containing any query term,
        then falls back to the first usable non-heading block.

        Args:
            content: Raw Markdown document content.
            terms: Normalized query terms used to select the best excerpt block.

        Returns:
            A trimmed excerpt string, or an empty string when no usable block is
            available.
        """
        # Parse the document into logical blocks so YAML frontmatter, headings,
        # and fenced code are handled consistently instead of line-by-line.
        blocks = self._markdown_blocks(content)
        lowered_terms = [term.lower() for term in terms]

        # Prefer a block that mentions one of the query terms, because that keeps
        # the displayed result connected to the user's requested topic.
        for block in blocks:
            if self.should_skip_excerpt_block(block):
                continue
            lowered_text = block.text.lower()
            if any(term in lowered_text for term in lowered_terms):
                return self.trim_excerpt(block.text)

        # Fall back to the first usable block so semantic-only hits still show a
        # meaningful preview even when no keyword term appears in the excerpt.
        for block in blocks:
            if self.should_skip_excerpt_block(block):
                continue
            return self.trim_excerpt(block.text)

        # Return the same empty fallback as the old implementation when a file
        # contains only headings, tables, or ignored references.
        return ''

    def chunk_document(self, document: KnowledgeDocument) -> list[KnowledgeChunk]:
        """Split one Markdown document into retrieval chunks.

        The chunker keeps Markdown headings as section boundaries and packs the
        body text under each section into chunks up to the configured maximum
        size. Extremely large blocks are emitted as their own chunk so content
        is never dropped.

        Args:
            document: Parsed Markdown document to chunk.

        Returns:
            Ordered list of retrieval chunks derived from the source document.
        """
        # Parse the document into headings and paragraph-like blocks first so we
        # can preserve line spans and keep chunking deterministic.
        blocks = self._markdown_blocks(document.content)
        heading_stack: list[tuple[int, str]] = []
        chunks: list[KnowledgeChunk] = []
        current_parts: list[str] = []
        current_start_line = 0
        current_end_line = 0

        def current_heading_path() -> str:
            if heading_stack:
                return ' / '.join(title for _, title in heading_stack)
            return document.title

        def current_chunk_title() -> str:
            if heading_stack:
                return heading_stack[-1][1]
            return document.title

        def flush_chunk() -> None:
            nonlocal current_parts, current_start_line, current_end_line
            if not current_parts:
                return

            body = '\n'.join(current_parts).strip()
            if not body:
                current_parts = []
                current_start_line = 0
                current_end_line = 0
                return

            chunk_index = len(chunks)
            heading_path = current_heading_path()
            chunk_title = current_chunk_title()
            chunk_key = self._chunk_key(
                source_path=document.repository_relative_path,
                chunk_index=chunk_index,
                start_line=current_start_line or 1,
                end_line=current_end_line or current_start_line or 1,
                heading_path=heading_path,
                chunk_title=chunk_title,
                content=body,
            )
            chunks.append(
                KnowledgeChunk(
                    source_path=document.repository_relative_path,
                    source_title=document.title,
                    chunk_key=chunk_key,
                    chunk_index=chunk_index,
                    chunk_title=chunk_title,
                    heading_path=heading_path,
                    start_line=current_start_line or 1,
                    end_line=current_end_line or current_start_line or 1,
                    content=body,
                )
            )
            current_parts = []
            current_start_line = 0
            current_end_line = 0

        # Section headings become chunk boundaries; content blocks are packed
        # until the configured size limit is reached.
        for block in blocks:
            if block.kind == 'heading':
                flush_chunk()
                level = int(block.level or 1)
                title = block.text.strip() or document.title
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))
                continue

            text = block.text.strip()
            if not text:
                continue

            # Start a new chunk before appending a block that would overflow
            # the configured budget; individual oversized blocks are still kept.
            prospective_size = len('\n'.join(current_parts)) + len(text) + (1 if current_parts else 0)
            if current_parts and prospective_size > self.chunk_max_chars:
                flush_chunk()

            if not current_parts:
                current_start_line = block.start_line
            current_end_line = block.end_line
            current_parts.append(text)

        flush_chunk()
        return chunks

    def should_skip_excerpt_line(self, line: str) -> bool:
        """Return whether a line is unsuitable for excerpt display.

        Args:
            line: Candidate Markdown line after whitespace trimming.

        Returns:
            `True` when the line should be skipped, otherwise `False`.
        """
        return self.should_skip_excerpt_block(
            MarkdownBlock(kind='text', text=line, start_line=1, end_line=1)
        )

    def should_skip_excerpt_block(self, block: MarkdownBlock) -> bool:
        """Return whether a parsed Markdown block is unsuitable for excerpts.

        Args:
            block: Parsed Markdown block candidate.

        Returns:
            `True` when the block should be skipped, otherwise `False`.
        """
        # Normalize once so the skip rules are case-insensitive and unaffected
        # by accidental leading or trailing whitespace.
        normalized = block.text.strip().lower()
        if not normalized:
            return True

        # Headings are only used to establish chunk boundaries, not display
        # excerpts.
        if block.kind == 'heading':
            return True

        # Preserve the original behavior that hides internal prompt/kb reference
        # lists from user-facing excerpts.
        if normalized.startswith('- `prompts/') or normalized.startswith('- `kb/'):
            return True

        # Preserve the old table-skip behavior because table rows are usually
        # poor standalone excerpts.
        if block.kind == 'table' or normalized.startswith('| ') or normalized.startswith('|'):
            return True
        return False

    def trim_excerpt(self, text: str) -> str:
        """Normalize and trim an excerpt string.

        Args:
            text: Raw excerpt text selected from a Markdown line.

        Returns:
            Whitespace-normalized excerpt capped at `excerpt_chars`.
        """
        # Collapse internal whitespace to keep prompt context compact and stable
        # across Markdown formatting differences.
        normalized = re.sub(r'\s+', ' ', text).strip()
        if len(normalized) <= self.excerpt_chars:
            return normalized

        # Match the old truncation style by reserving three characters for the
        # ellipsis and avoiding trailing whitespace before it.
        return normalized[: self.excerpt_chars - 3].rstrip() + '...'

    def build_chunk_semantic_document(self, chunk: KnowledgeChunk) -> str:
        """Build the text payload stored for one semantic chunk.

        Args:
            chunk: Chunk derived from a source markdown document.

        Returns:
            Semantic document string containing the source title, section path,
            repository-relative path, and chunk body.
        """
        # Include both the source title and the chunk heading path so the
        # embedding model sees enough local context to differentiate sibling
        # chunks from the same document.
        semantic_title = chunk.source_title
        if chunk.heading_path and chunk.heading_path != chunk.source_title:
            semantic_title = f'{chunk.source_title} :: {chunk.heading_path}'
        relative_path = f'{chunk.source_path}#{chunk.chunk_index + 1:04d}'
        return self.build_semantic_document(
            title=semantic_title,
            relative_path=relative_path,
            content=chunk.content,
        )

    def build_semantic_document(self, *, title: str, relative_path: str, content: str) -> str:
        """Build the text payload stored in the semantic vector index.

        Args:
            title: Parsed document title.
            relative_path: Repository-relative Markdown path.
            content: Raw Markdown document content.

        Returns:
            Semantic document string containing title, path, and truncated body.
        """
        # Normalize whitespace before truncation so semantically equivalent
        # Markdown formatting produces stable vector input length.
        cleaned_content = re.sub(r'\s+', ' ', content).strip()
        if len(cleaned_content) > self.embedding_max_chars:
            cleaned_content = cleaned_content[: self.embedding_max_chars].rstrip()

        # Preserve the old semantic document shape so existing embeddings are
        # conceptually equivalent after a rebuild.
        return f'{title}\n\n{relative_path}\n\n{cleaned_content}'

    def excerpt_from_semantic_document(self, document: str) -> str:
        """Extract a display excerpt from a stored semantic document payload.

        Args:
            document: Semantic document text previously built for vector storage.

        Returns:
            Best-effort excerpt extracted from the semantic document body.
        """
        # Split title/path/body using the original double-newline structure and
        # keep the final segment as the body for excerpt construction.
        parts = document.split('\n\n', 2)
        body = parts[-1] if parts else document

        # Use the generic excerpt builder without query terms, matching the old
        # vector-hit fallback behavior.
        return self.build_excerpt(body, [])

    def _markdown_blocks(self, content: str) -> list[MarkdownBlock]:
        """Split raw markdown into heading and body blocks.

        Args:
            content: Raw Markdown text.

        Returns:
            Ordered Markdown blocks with source line spans.
        """
        body, line_offset = self._strip_yaml_frontmatter(content)
        lines = body.splitlines()

        try:
            tokens = self._markdown.parse(body)
            blocks = self._markdown_blocks_from_tokens(tokens, lines, line_offset)
            if blocks:
                return blocks
        except Exception:  # pragma: no cover - markdown-it parsing should be stable
            pass

        return self._fallback_markdown_blocks(body, line_offset)

    def _markdown_blocks_from_tokens(
        self,
        tokens: list[Token],
        lines: list[str],
        line_offset: int,
    ) -> list[MarkdownBlock]:
        """Convert markdown-it tokens into logical Markdown blocks."""
        blocks: list[MarkdownBlock] = []
        index = 0
        token_count = len(tokens)

        # Walk the token stream once so heading, paragraph, code, and table
        # blocks stay aligned to their original source line ranges.
        while index < token_count:
            token = tokens[index]

            if token.type == 'table_open':
                block = self._block_from_token(token, lines, line_offset, kind='table')
                if block is not None:
                    blocks.append(block)
                index = self._skip_until(tokens, index + 1, 'table_close')
                continue

            if token.type == 'heading_open':
                inline = self._next_inline_token(tokens, index + 1)
                text = self._inline_text(inline) if inline is not None else ''
                block = self._block_from_token(token, lines, line_offset, kind='heading', text=text, level=self._heading_level(token))
                if block is not None:
                    blocks.append(block)
                index += 1
                continue

            if token.type == 'paragraph_open':
                inline = self._next_inline_token(tokens, index + 1)
                block = self._block_from_token(token, lines, line_offset, kind='text', text=self._raw_block_text(token, lines, default=self._inline_text(inline)))
                if block is not None:
                    blocks.append(block)
                index += 1
                continue

            if token.type == 'fence':
                block = self._block_from_token(
                    token,
                    lines,
                    line_offset,
                    kind='code',
                    text=self._raw_block_text(token, lines, default=token.content.rstrip('\n')),
                    info=token.info.strip() or None,
                )
                if block is not None:
                    blocks.append(block)
                index += 1
                continue

            if token.type == 'code_block':
                block = self._block_from_token(
                    token,
                    lines,
                    line_offset,
                    kind='code',
                    text=self._raw_block_text(token, lines, default=token.content),
                )
                if block is not None:
                    blocks.append(block)
                index += 1
                continue

            if token.type == 'html_block':
                block = self._block_from_token(token, lines, line_offset, kind='html', text=self._raw_block_text(token, lines, default=token.content))
                if block is not None:
                    blocks.append(block)
                index += 1
                continue

            index += 1

        return blocks

    def _fallback_markdown_blocks(self, content: str, line_offset: int) -> list[MarkdownBlock]:
        """Split markdown with a conservative line-based fallback parser."""
        blocks: list[MarkdownBlock] = []
        buffer: list[str] = []
        buffer_start_line = 0
        lines = content.splitlines()

        def flush_buffer(end_line: int) -> None:
            nonlocal buffer, buffer_start_line
            if not buffer:
                return
            blocks.append(
                MarkdownBlock(
                    kind='text',
                    text='\n'.join(buffer).strip(),
                    start_line=buffer_start_line or end_line,
                    end_line=end_line,
                )
            )
            buffer = []
            buffer_start_line = 0

        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            heading_match = re.match(r'^(#{1,6})\s+(.*)$', stripped)
            if heading_match:
                flush_buffer(line_offset + line_number - 1)
                blocks.append(
                    MarkdownBlock(
                        kind='heading',
                        text=heading_match.group(2).strip(),
                        start_line=line_offset + line_number,
                        end_line=line_offset + line_number,
                        level=len(heading_match.group(1)),
                    )
                )
                continue

            if not stripped:
                flush_buffer(line_offset + line_number - 1)
                continue

            if not buffer:
                buffer_start_line = line_offset + line_number
            buffer.append(line.rstrip())

        flush_buffer(line_offset + len(lines) or line_offset or 1)
        return blocks

    def _block_from_token(
        self,
        token: Token,
        lines: list[str],
        line_offset: int,
        *,
        kind: str,
        text: str | None = None,
        level: int | None = None,
        info: str | None = None,
    ) -> MarkdownBlock | None:
        """Build a `MarkdownBlock` from a markdown-it token."""
        start_line, end_line = self._token_lines(token, line_offset, len(lines))
        if start_line <= 0 or end_line <= 0:
            return None

        block_text = text if text is not None else self._raw_block_text(token, lines)
        block_text = block_text.strip()
        if not block_text and kind != 'heading':
            return None
        return MarkdownBlock(kind=kind, text=block_text, start_line=start_line, end_line=end_line, level=level, info=info)

    def _token_lines(self, token: Token, line_offset: int, line_count: int) -> tuple[int, int]:
        """Return 1-based original line numbers for a token."""
        if token.map is None:
            return 0, 0

        start = line_offset + token.map[0] + 1
        end = line_offset + max(token.map[1], token.map[0] + 1)
        if line_count > 0:
            end = min(end, line_offset + line_count)
        return start, end

    def _raw_block_text(self, token: Token, lines: list[str], default: str = '') -> str:
        """Extract the source slice for a token when line information exists."""
        if token.map is None:
            return default

        start, end = token.map
        if start < 0 or end <= start:
            return default
        if end > len(lines):
            end = len(lines)
        return '\n'.join(lines[start:end]).strip() or default

    def _next_inline_token(self, tokens: list[Token], index: int) -> Token | None:
        """Return the next inline token after a block opener, if present."""
        if index < len(tokens) and tokens[index].type == 'inline':
            return tokens[index]
        return None

    def _skip_until(self, tokens: list[Token], index: int, token_type: str) -> int:
        """Advance the token index until the matching close token is seen."""
        while index < len(tokens):
            if tokens[index].type == token_type:
                return index + 1
            index += 1
        return index

    def _inline_text(self, token: Token | None) -> str:
        """Render inline markdown tokens as readable text."""
        if token is None:
            return ''
        if token.children:
            parts: list[str] = []
            for child in token.children:
                if child.type in {'text', 'code_inline', 'html_inline'}:
                    parts.append(child.content)
                elif child.type in {'softbreak', 'hardbreak'}:
                    parts.append(' ')
            return ''.join(parts).strip() or token.content.strip()
        return token.content.strip()

    def _heading_level(self, token: Token) -> int | None:
        """Convert a markdown-it heading token tag into a numeric level."""
        if token.tag.startswith('h') and token.tag[1:].isdigit():
            return int(token.tag[1:])
        return None

    def _strip_yaml_frontmatter(self, content: str) -> tuple[str, int]:
        """
        Remove a leading YAML frontmatter block before Markdown parsing.
        
        Args:
        
        Returns:
            [0]: return shtis.
            [1]: offset of yaml formatter on heading.
        """
        lines = content.splitlines()
        if not lines or lines[0].strip() != '---':
            return content, 0

        # Treat the first closing `---` or `...` line as frontmatter terminator.
        for index in range(1, len(lines)):
            marker = lines[index].strip()
            if marker in {'---', '...'}:
                body = '\n'.join(lines[index + 1 :])
                return body, index + 1

        # Leave malformed frontmatter untouched so we never drop document text
        # when a file only happens to start with `---`.
        return content, 0

    def _chunk_key(
        self,
        *,
        source_path: str,
        chunk_index: int,
        start_line: int,
        end_line: int,
        heading_path: str,
        chunk_title: str,
        content: str,
    ) -> str:
        """Build a stable chunk identifier for vector storage.

        Args:
            source_path: Repository-relative path of the source document.
            chunk_index: Zero-based chunk ordinal within the document.
            start_line: First source line covered by the chunk.
            end_line: Last source line covered by the chunk.
            heading_path: Hierarchical Markdown heading path.
            chunk_title: Short title or heading label for the chunk.
            content: Raw chunk body text.

        Returns:
            Stable hexadecimal chunk identifier suitable for vector IDs.
        """
        payload = '\n'.join(
            [
                source_path,
                str(chunk_index),
                str(start_line),
                str(end_line),
                heading_path,
                chunk_title,
                content,
            ]
        )
        return hashlib.md5(payload.encode('utf-8')).hexdigest()
