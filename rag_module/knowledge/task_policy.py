"""Task-specific retrieval policy for CTF-oriented knowledge lookup."""

from __future__ import annotations

from pathlib import Path

from .models import KnowledgeChunk, KnowledgeDocument, RetrievalQuery
from .keyword_retriever import KeywordRetriever


class TaskRetrievalPolicy:
    """Builds retrieval queries and task-specific boosts.

    This class contains CTF task semantics that should not live in the generic
    knowledge-base or vector-store layers.

    TODO: This class should become an interface, which enables user to implement their own policies.
    """

    def __init__(self, keyword: KeywordRetriever, root: Path) -> None:
        """Initialize the policy with term extraction and root path context.

        Args:
            keyword: Keyword retriever used to normalize task query terms.
            root: Knowledge-base root used to build fallback document paths.
        """
        # Store collaborators explicitly so task policy remains independent from
        # facade internals.
        self.keyword = keyword
        self.root = root

    def build_freeform_query(self, query: str, *, limit: int, max_limit: int) -> RetrievalQuery | None:
        """Build a normalized retrieval query for direct user search.

        Args:
            query: Freeform text query supplied by the caller.
            limit: Requested result count.
            max_limit: Maximum allowed result count for public search.

        Returns:
            A `RetrievalQuery` when usable terms exist, otherwise `None`.
        """
        # Clamp public search limits using the old `[1, 10]` behavior before the
        # query reaches any retrieval backend.
        normalized_limit = max(1, min(int(limit), max_limit))
        terms = self.keyword.extract_terms([query])
        if not terms:
            return None

        # Return a strategy-neutral retrieval query with the original semantic
        # multiplier used by `search()`.
        return RetrievalQuery(
            query_text=query,
            terms=terms,
            limit=normalized_limit,
            task_type='',
            semantic_multiplier=20.0,
        )

    def build_task_query(
        self,
        *,
        task_name: str,
        task_type: str,
        target: str,
        file_descriptions: str,
        limit: int,
    ) -> RetrievalQuery | None:
        """Build a normalized retrieval query from task metadata.

        Args:
            task_name: Human-readable task name.
            task_type: CTF task type such as `RE`.
                TODO: This is the general-using task type.
            target: Task target URL, binary name, or challenge-specific target.
            file_descriptions: User-facing descriptions of attached files.
            limit: Requested maximum context hit count.

        Returns:
            A task-aware `RetrievalQuery`, or `None` when no usable terms exist.
        """
        # Merge explicit task fields with policy defaults so sparse tasks still
        # retrieve useful strategy documents.
        default_terms = self.default_topic_keywords(task_type)
        task_keywords = self.keyword.extract_terms([task_name, task_type, target, file_descriptions, *default_terms])
        if not task_keywords:
            task_keywords = default_terms
        if not task_keywords:
            return None

        # Build the semantic query text in the same order as the old class so
        # semantic search receives equivalent context.
        query_parts = [task_name, task_type, target, file_descriptions, *default_terms]
        query_text = '\n'.join(part.strip() for part in query_parts if part and part.strip())

        # Clamp task-context results using the old `[1, 6]` behavior and keep the
        # previous vector-score multiplier for task retrieval.
        normalized_limit = max(1, min(int(limit), 6))
        return RetrievalQuery(
            query_text=query_text or ' '.join(task_keywords),
            terms=task_keywords,
            limit=normalized_limit,
            task_type=task_type,
            semantic_multiplier=18.0,
        )

    def default_topic_keywords(self, task_type: str) -> list[str]:
        """Return default query keywords for a task type.

        Args:
            task_type: CTF task type string.

        Returns:
            Default keywords used when task metadata is sparse.
        """
        # Preserve the old RE default topic keywords exactly so task context
        # retrieval remains behavior-compatible after refactoring.
        normalized = (task_type or '').strip().upper()
        if normalized == 'RE':
            return [
                'strategy',
                'shortest',
                'solver',
                'workflow',
                'windows',
                'pe',
                'packer',
                'unpacking',
                'anti-debug',
                'string',
                'obfuscation',
            ]
        return []

    def boost_for_task_type(self, document: KnowledgeDocument, task_type: str) -> int:
        """Return an additional deterministic boost for task-aware search.

        Args:
            document: Parsed knowledge document being ranked.
            task_type: CTF task type associated with the query.

        Returns:
            Integer boost added to keyword score.
        """
        return self._boost_for_path_and_text(
            task_type=task_type,
            relative_path=document.root_relative_path,
            combined_text=f'{document.absolute_path.name} {document.title}',
        )

    def boost_for_chunk(self, chunk: KnowledgeChunk, task_type: str) -> int:
        """Return an additional deterministic boost for a chunk hit.

        Args:
            chunk: Chunk produced from a parsed knowledge document.
            task_type: CTF task type associated with the query.

        Returns:
            Integer boost added to the chunk's keyword score.
        """
        return self._boost_for_path_and_text(
            task_type=task_type,
            relative_path=chunk.source_path,
            combined_text=f'{chunk.source_title} {chunk.chunk_title} {chunk.heading_path}',
        )

    def _boost_for_path_and_text(self, *, task_type: str, relative_path: str, combined_text: str) -> int:
        """Apply the old task-specific heuristic to path and text metadata."""
        # Normalize task type and textual features once before applying the old
        # RE-specific scoring rules.
        normalized = (task_type or '').strip().upper()
        combined = combined_text.lower()
        normalized_path = relative_path.replace('\\', '/').lower()
        score = 0

        # Strategy documents are globally preferred for task searches, matching
        # the previous behavior.
        if normalized_path.startswith('strategy/') or '/strategy/' in normalized_path:
            score += 24

        # Preserve the original RE-specific boost for triage, packers, unpacking,
        # obfuscation, and strategy documents.
        if normalized == 'RE':
            if 'triage' in combined or 'pack' in combined or 'unpack' in combined or 'obfusc' in combined:
                score += 10
            if normalized_path.startswith('strategy/') or '/strategy/' in normalized_path:
                score += 20
        return score

    def fallback_paths(self, task_type: str) -> list[Path]:
        """Return fallback documents for a task type.

        Args:
            task_type: CTF task type string.

        Returns:
            Ordered list of absolute fallback Markdown paths.
        """
        # Preserve the old RE fallback list and return no fallback documents for
        # task types that were previously unsupported.
        normalized = (task_type or '').strip().upper()
        if normalized != 'RE':
            return []
        return [
            self.root / 'strategy' / 're-shortest-verifiable-path.md',
            self.root / 'strategy' / 're-segmented-decode-short-circuit.md',
            self.root / 'strategy' / 're-local-decompile-before-full-flow.md',
            self.root / 'workflows' / 'windows-pe-triage.md',
            self.root / 'packers' / 'upx-identification.md',
            self.root / 'unpacking' / 'oep-recovery-playbook.md',
        ]
