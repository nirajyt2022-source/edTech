"""
Vector search service — hybrid semantic + keyword search with RRF fusion.

Combines pgvector cosine similarity on both curriculum_content and
curriculum_embeddings tables with ilike keyword search, fusing all three
result lists via Reciprocal Rank Fusion (RRF).

Usage:
    from app.services.vector_search import get_vector_search

    vs = get_vector_search()
    results = await vs.hybrid_search("How do I add fractions?", grade="Class 4", subject="Maths")
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.core.deps import get_supabase_client
from app.services.embedding import get_embedding_service

logger = structlog.get_logger("skolar.vector_search")

RRF_K = 60
SEMANTIC_WEIGHT = 0.7
EMBEDDING_WEIGHT = 0.5
KEYWORD_WEIGHT = 0.3


class VectorSearchService:
    """Hybrid search combining semantic embeddings and keyword matching."""

    async def semantic_search(
        self,
        query: str,
        grade: str | None = None,
        subject: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Embed query and search via match_curriculum RPC."""
        try:
            svc = get_embedding_service()
            vec = await svc.embed_text(query)

            sb = get_supabase_client()
            result = sb.rpc(
                "match_curriculum",
                {
                    "query_embedding": vec,
                    "match_count": top_k,
                    "filter_grade": grade,
                    "filter_subject": subject,
                    "similarity_threshold": 0.3,
                },
            ).execute()

            if result.data:
                logger.info(
                    "semantic_search_hit",
                    query_preview=query[:60],
                    count=len(result.data),
                )
                return result.data
            return []
        except Exception as e:
            logger.error("semantic_search_error", error=str(e), query_preview=query[:60])
            return []

    async def semantic_search_embeddings(
        self,
        query: str,
        grade: str | None = None,
        subject: str | None = None,
        top_k: int = 5,
        source_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search curriculum_embeddings table (textbook uploads, PDF chunks, etc.).

        Results are normalized to include an ``ncert_summary`` key so that
        ``_format_context()`` in ask_skolar.py can consume them identically.
        """
        try:
            svc = get_embedding_service()
            vec = await svc.embed_text(query)

            sb = get_supabase_client()
            result = sb.rpc(
                "match_curriculum_embeddings",
                {
                    "query_embedding": vec,
                    "match_count": top_k,
                    "filter_grade": grade,
                    "filter_subject": subject,
                    "filter_source_type": source_type,
                    "similarity_threshold": 0.3,
                },
            ).execute()

            if result.data:
                logger.info(
                    "semantic_search_embeddings_hit",
                    query_preview=query[:60],
                    count=len(result.data),
                )
                # Normalize: map chunk_text → ncert_summary so downstream formatters work
                for doc in result.data:
                    doc.setdefault("ncert_summary", doc.get("chunk_text", ""))
                return result.data
            return []
        except Exception as e:
            logger.error("semantic_search_embeddings_error", error=str(e), query_preview=query[:60])
            return []

    async def keyword_search(
        self,
        query: str,
        grade: str | None = None,
        subject: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Keyword search using ilike on topic and ncert_summary columns."""
        try:
            sb = get_supabase_client()
            # Extract meaningful words (skip very short ones)
            words = [w for w in query.split() if len(w) > 2]
            if not words:
                return []

            # Use the first few meaningful words for matching
            search_term = " ".join(words[:5])

            q = sb.table("curriculum_content").select("*")
            if grade:
                q = q.eq("grade", grade)
            if subject:
                q = q.eq("subject", subject)

            # Search in topic column
            q = q.or_(f"topic.ilike.%{search_term}%,ncert_summary.ilike.%{search_term}%")
            result = q.limit(top_k).execute()

            if result.data:
                logger.info(
                    "keyword_search_hit",
                    query_preview=query[:60],
                    count=len(result.data),
                )
                return result.data
            return []
        except Exception as e:
            logger.error("keyword_search_error", error=str(e), query_preview=query[:60])
            return []

    async def hybrid_search(
        self,
        query: str,
        grade: str | None = None,
        subject: str | None = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Run semantic (curriculum + embeddings) + keyword in parallel, fuse with RRF."""
        try:
            semantic_results, embedding_results, keyword_results = await asyncio.gather(
                self.semantic_search(query, grade, subject, top_k=top_k + 2),
                self.semantic_search_embeddings(query, grade, subject, top_k=top_k + 2),
                self.keyword_search(query, grade, subject, top_k=top_k + 2),
            )

            fused = _reciprocal_rank_fusion(semantic_results, embedding_results, keyword_results, top_k=top_k)

            logger.info(
                "hybrid_search_complete",
                query_preview=query[:60],
                semantic_count=len(semantic_results),
                embedding_count=len(embedding_results),
                keyword_count=len(keyword_results),
                fused_count=len(fused),
            )
            return fused
        except Exception as e:
            logger.error("hybrid_search_error", error=str(e), query_preview=query[:60])
            return []


def _reciprocal_rank_fusion(
    semantic_results: list[dict[str, Any]],
    embedding_results: list[dict[str, Any]],
    keyword_results: list[dict[str, Any]],
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Fuse three ranked lists using RRF with configurable weights."""
    scores: dict[str, float] = {}
    doc_map: dict[str, dict[str, Any]] = {}

    # Score semantic results (curriculum_content)
    for rank, doc in enumerate(semantic_results):
        doc_id = str(doc.get("id", f"sem_{rank}"))
        scores[doc_id] = scores.get(doc_id, 0.0) + SEMANTIC_WEIGHT / (RRF_K + rank + 1)
        doc_map[doc_id] = doc

    # Score embedding results (curriculum_embeddings)
    for rank, doc in enumerate(embedding_results):
        doc_id = str(doc.get("id", f"emb_{rank}"))
        scores[doc_id] = scores.get(doc_id, 0.0) + EMBEDDING_WEIGHT / (RRF_K + rank + 1)
        doc_map[doc_id] = doc

    # Score keyword results
    for rank, doc in enumerate(keyword_results):
        doc_id = str(doc.get("id", f"kw_{rank}"))
        scores[doc_id] = scores.get(doc_id, 0.0) + KEYWORD_WEIGHT / (RRF_K + rank + 1)
        doc_map[doc_id] = doc

    # Sort by fused score descending, return top_k
    ranked_ids = sorted(scores, key=lambda x: scores[x], reverse=True)[:top_k]
    return [doc_map[doc_id] for doc_id in ranked_ids]


# -- Singleton ----------------------------------------------------------------

_vector_search: VectorSearchService | None = None


def get_vector_search() -> VectorSearchService:
    """Get the singleton VectorSearchService instance."""
    global _vector_search
    if _vector_search is None:
        _vector_search = VectorSearchService()
    return _vector_search
