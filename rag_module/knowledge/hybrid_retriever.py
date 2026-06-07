"""Hybrid keyword/vector retrieval orchestration."""

from __future__ import annotations

from .config import KnowledgeConfig
from .index_manager import VectorIndexManager
from .keyword_retriever import KeywordRetriever
from .markdown_loader import MarkdownKnowledgeLoader
from .models import KnowledgeHit, RetrievalQuery
from .task_policy import TaskRetrievalPolicy
from .text_utils import TextTools
from .vector_store import ChromaVectorStore


class HybridRetriever:
    """Merges keyword scores, vector scores, and task-policy boosts.

    This class owns final retrieval ranking. It does not build prompt context and
    does not manage vector-index persistence directly.
    """

    def __init__(
        self,
        *,
        config: KnowledgeConfig,
        loader: MarkdownKnowledgeLoader,
        keyword: KeywordRetriever,
        vector_store: ChromaVectorStore,
        index_manager: VectorIndexManager,
        policy: TaskRetrievalPolicy,
        text: TextTools,
    ) -> None:
        """Initialize the hybrid retriever.

        Args:
            config: Knowledge-base configuration values.
            loader: Markdown loader used to read current documents.
            keyword: Keyword scorer used for deterministic relevance.
            vector_store: Semantic vector backend adapter.
            index_manager: Index lifecycle manager used to ensure manifest state.
            policy: Task-specific retrieval policy for boosts and fallbacks.
            text: Text helper used to build final excerpts.
        """
        # Store collaborators by responsibility so this class only handles score
        # fusion and hit assembly.
        self.config = config
        self.loader = loader
        self.keyword = keyword
        self.vector_store = vector_store
        self.index_manager = index_manager
        self.policy = policy
        self.text = text

    def search(self, query: RetrievalQuery) -> list[KnowledgeHit]:
        """Search documents with hybrid lexical and semantic ranking.

        Args:
            query: Normalized retrieval query containing terms, semantic text,
                task type, limit, and vector-score multiplier.

        Returns:
            Ranked list of final knowledge hits capped by `query.limit`.
        """
        # Preserve the original behavior where retrieval ensures the manifest is
        # present and fresh before semantic candidates are requested.
        manifest_entries = self.index_manager.ensure_vector_index()
        semantic_limit = self.index_manager.semantic_candidate_limit(query.limit, len(manifest_entries))

        # Query the vector backend only when the manifest says the backend was
        # built successfully; otherwise rely on keyword-only fallback.
        semantic_hits = {}
        if self.index_manager.manifest.meta.backend_ready:
            semantic_hits = self.vector_store.query(query.query_text, limit=semantic_limit)

        # Score every current document so keyword matches outside semantic top-k
        # can still win when their lexical relevance is strong.
        hits: list[KnowledgeHit] = []
        for document in self.loader.load_documents():
            keyword_score = float(self.keyword.score_document(document, query.terms))
            if query.task_type:
                keyword_score += float(self.policy.boost_for_task_type(document, query.task_type))

            # Merge optional semantic score with deterministic score using the
            # same multiplicative weighting as the old implementation.
            semantic_hit = semantic_hits.get(document.repository_relative_path)
            vector_score = float(semantic_hit.score if semantic_hit is not None else 0.0)
            combined_score = keyword_score + (vector_score * query.semantic_multiplier)
            if combined_score <= 0:
                continue

            # Build the best available excerpt in the original priority order:
            # live keyword excerpt, semantic excerpt, then manifest excerpt.
            manifest_entry = manifest_entries.get(document.repository_relative_path)
            excerpt = self.text.build_excerpt(document.content, query.terms)
            if not excerpt and semantic_hit is not None:
                excerpt = semantic_hit.excerpt.strip()
            if not excerpt and manifest_entry is not None:
                excerpt = manifest_entry.excerpt

            # Append the final hit with rounded scores to match the old public
            # dataclass values.
            hits.append(
                KnowledgeHit(
                    path=document.repository_relative_path,
                    title=document.title,
                    score=round(combined_score, 4),
                    excerpt=excerpt,
                    keyword_score=round(keyword_score, 4),
                    vector_score=round(vector_score, 4),
                )
            )

        # Sort with the old tie-breakers: final score, vector score, shorter path,
        # then lexical path order for deterministic output.
        hits.sort(key=lambda item: (-item.score, -item.vector_score, len(item.path), item.path))
        return hits[: max(1, min(int(query.limit), 10))]

    def fallback_hits_for_task_type(self, task_type: str, *, limit: int) -> list[KnowledgeHit]:
        """Build fallback hits for sparse task-aware retrieval.

        Args:
            task_type: CTF task type used to select fallback documents.
            limit: Maximum number of fallback hits to return.

        Returns:
            Ranked fallback hits using deterministic seed scores.
        """
        # Retrieve policy-defined fallback paths and default terms once so each
        # fallback document uses consistent excerpt selection.
        fallback_paths = self.policy.fallback_paths(task_type)
        default_terms = self.policy.default_topic_keywords(task_type)
        hits: list[KnowledgeHit] = []

        # Preserve the old scoring order by enumerating the reversed fallback
        # list and then sorting descending by seed score.
        for score_seed, candidate in enumerate(fallback_paths[::-1], start=1):
            if not candidate.exists():
                continue
            document = self.loader.read_document(candidate)
            hits.append(
                KnowledgeHit(
                    path=document.repository_relative_path,
                    title=document.title,
                    score=float(score_seed),
                    excerpt=self.text.build_excerpt(document.content, default_terms),
                    keyword_score=float(score_seed),
                    vector_score=0.0,
                )
            )

        # Return at most six fallback hits, matching the old task-context limit
        # guard.
        hits.sort(key=lambda item: (-item.score, item.path))
        return hits[: max(1, min(int(limit), 6))]
