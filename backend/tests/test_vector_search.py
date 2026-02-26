"""
Tests for VectorSearchService and RRF fusion.

All tests use unittest.mock — no real API calls or database access.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio

from app.services.vector_search import (
    EMBEDDING_WEIGHT,
    KEYWORD_WEIGHT,
    RRF_K,
    SEMANTIC_WEIGHT,
    VectorSearchService,
    _reciprocal_rank_fusion,
)

# ---------------------------------------------------------------------------
# RRF Unit Tests (3-way)
# ---------------------------------------------------------------------------

class TestReciprocalRankFusion:
    def test_semantic_ranked_higher_than_keyword(self):
        """Semantic-only result should outscore keyword-only result."""
        semantic = [{"id": "sem-1", "topic": "Fractions"}]
        embedding = []
        keyword = [{"id": "kw-1", "topic": "Decimals"}]

        fused = _reciprocal_rank_fusion(semantic, embedding, keyword, top_k=2)

        assert len(fused) == 2
        # Semantic result (weight 0.7) should be first
        assert fused[0]["id"] == "sem-1"
        assert fused[1]["id"] == "kw-1"

    def test_embedding_ranked_between_semantic_and_keyword(self):
        """Embedding-only result (weight 0.5) should rank between semantic (0.7) and keyword (0.3)."""
        semantic = [{"id": "sem-1", "topic": "Fractions"}]
        embedding = [{"id": "emb-1", "topic": "Textbook Fractions"}]
        keyword = [{"id": "kw-1", "topic": "Decimals"}]

        fused = _reciprocal_rank_fusion(semantic, embedding, keyword, top_k=3)

        assert len(fused) == 3
        assert fused[0]["id"] == "sem-1"
        assert fused[1]["id"] == "emb-1"
        assert fused[2]["id"] == "kw-1"

    def test_overlapping_results_get_boosted(self):
        """A document appearing in both lists gets a higher combined score."""
        shared_doc = {"id": "shared-1", "topic": "Fractions"}
        semantic = [shared_doc, {"id": "sem-only", "topic": "Decimals"}]
        embedding = []
        keyword = [shared_doc, {"id": "kw-only", "topic": "Geometry"}]

        fused = _reciprocal_rank_fusion(semantic, embedding, keyword, top_k=3)

        # Shared doc should be ranked first
        assert fused[0]["id"] == "shared-1"

    def test_triple_overlap_boost(self):
        """A doc in all three lists should rank above one in just two."""
        triple = {"id": "triple-1", "topic": "Fractions"}
        double = {"id": "double-1", "topic": "Decimals"}

        semantic = [triple, double]
        embedding = [triple]
        keyword = [double, triple]

        fused = _reciprocal_rank_fusion(semantic, embedding, keyword, top_k=2)
        assert fused[0]["id"] == "triple-1"

    def test_empty_lists(self):
        assert _reciprocal_rank_fusion([], [], [], top_k=3) == []

    def test_top_k_limits_output(self):
        semantic = [{"id": f"s{i}"} for i in range(5)]
        embedding = [{"id": f"e{i}"} for i in range(5)]
        keyword = [{"id": f"k{i}"} for i in range(5)]

        fused = _reciprocal_rank_fusion(semantic, embedding, keyword, top_k=2)
        assert len(fused) == 2

    def test_scores_use_correct_weights(self):
        """Verify the RRF formula: weight / (k + rank + 1)."""
        semantic = [{"id": "a"}]
        embedding = [{"id": "b"}]
        keyword = [{"id": "c"}]

        fused = _reciprocal_rank_fusion(semantic, embedding, keyword, top_k=3)

        # Score for "a": SEMANTIC_WEIGHT / (RRF_K + 0 + 1) = 0.7 / 61
        # Score for "b": EMBEDDING_WEIGHT / (RRF_K + 0 + 1) = 0.5 / 61
        # Score for "c": KEYWORD_WEIGHT / (RRF_K + 0 + 1) = 0.3 / 61
        expected_a = SEMANTIC_WEIGHT / (RRF_K + 1)
        expected_b = EMBEDDING_WEIGHT / (RRF_K + 1)
        expected_c = KEYWORD_WEIGHT / (RRF_K + 1)
        assert expected_a > expected_b > expected_c
        assert fused[0]["id"] == "a"
        assert fused[1]["id"] == "b"
        assert fused[2]["id"] == "c"

    def test_embedding_only_no_other_sources(self):
        """When only embeddings have results, those should still surface."""
        embedding = [{"id": "emb-1"}, {"id": "emb-2"}]
        fused = _reciprocal_rank_fusion([], embedding, [], top_k=3)
        assert len(fused) == 2
        assert fused[0]["id"] == "emb-1"


# ---------------------------------------------------------------------------
# VectorSearchService Tests (mocked)
# ---------------------------------------------------------------------------

def _make_search_service():
    """Create a VectorSearchService with mocked dependencies."""
    import app.services.vector_search as mod
    mod._vector_search = None
    return VectorSearchService()


class TestSemanticSearch:
    @patch("app.services.vector_search.get_supabase_client")
    @patch("app.services.vector_search.get_embedding_service")
    def test_returns_results(self, mock_embed_svc, mock_sb):
        svc = _make_search_service()

        # Mock embedding
        embed_instance = MagicMock()
        embed_instance.embed_text = AsyncMock(return_value=[0.1] * 768)
        mock_embed_svc.return_value = embed_instance

        # Mock Supabase RPC
        mock_rpc_result = MagicMock()
        mock_rpc_result.data = [
            {"id": "uuid-1", "topic": "Fractions", "similarity": 0.85},
        ]
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = mock_rpc_result
        sb_instance = MagicMock()
        sb_instance.rpc.return_value = mock_rpc
        mock_sb.return_value = sb_instance

        results = asyncio.run(svc.semantic_search("add fractions", grade="Class 4"))
        assert len(results) == 1
        assert results[0]["topic"] == "Fractions"

    @patch("app.services.vector_search.get_supabase_client")
    @patch("app.services.vector_search.get_embedding_service")
    def test_graceful_on_embed_failure(self, mock_embed_svc, mock_sb):
        """Returns [] when embedding fails instead of crashing."""
        svc = _make_search_service()

        embed_instance = MagicMock()
        embed_instance.embed_text = AsyncMock(side_effect=RuntimeError("API down"))
        mock_embed_svc.return_value = embed_instance

        results = asyncio.run(svc.semantic_search("broken query"))
        assert results == []


class TestSemanticSearchEmbeddings:
    @patch("app.services.vector_search.get_supabase_client")
    @patch("app.services.vector_search.get_embedding_service")
    def test_returns_normalized_results(self, mock_embed_svc, mock_sb):
        """Results should have ncert_summary mapped from chunk_text."""
        svc = _make_search_service()

        embed_instance = MagicMock()
        embed_instance.embed_text = AsyncMock(return_value=[0.1] * 768)
        mock_embed_svc.return_value = embed_instance

        mock_rpc_result = MagicMock()
        mock_rpc_result.data = [
            {
                "id": "uuid-emb-1",
                "chunk_text": "Fractions are parts of a whole.",
                "source_type": "textbook_upload",
                "topic": "Fractions",
                "similarity": 0.82,
            },
        ]
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = mock_rpc_result
        sb_instance = MagicMock()
        sb_instance.rpc.return_value = mock_rpc
        mock_sb.return_value = sb_instance

        results = asyncio.run(svc.semantic_search_embeddings("what are fractions"))
        assert len(results) == 1
        # Normalized field should exist
        assert results[0]["ncert_summary"] == "Fractions are parts of a whole."
        assert results[0]["source_type"] == "textbook_upload"

    @patch("app.services.vector_search.get_supabase_client")
    @patch("app.services.vector_search.get_embedding_service")
    def test_calls_correct_rpc(self, mock_embed_svc, mock_sb):
        """Should call match_curriculum_embeddings, not match_curriculum."""
        svc = _make_search_service()

        embed_instance = MagicMock()
        embed_instance.embed_text = AsyncMock(return_value=[0.1] * 768)
        mock_embed_svc.return_value = embed_instance

        mock_rpc_result = MagicMock()
        mock_rpc_result.data = []
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = mock_rpc_result
        sb_instance = MagicMock()
        sb_instance.rpc.return_value = mock_rpc
        mock_sb.return_value = sb_instance

        asyncio.run(svc.semantic_search_embeddings("test query"))
        sb_instance.rpc.assert_called_once()
        rpc_name = sb_instance.rpc.call_args[0][0]
        assert rpc_name == "match_curriculum_embeddings"

    @patch("app.services.vector_search.get_supabase_client")
    @patch("app.services.vector_search.get_embedding_service")
    def test_graceful_on_failure(self, mock_embed_svc, mock_sb):
        svc = _make_search_service()
        embed_instance = MagicMock()
        embed_instance.embed_text = AsyncMock(side_effect=RuntimeError("fail"))
        mock_embed_svc.return_value = embed_instance

        results = asyncio.run(svc.semantic_search_embeddings("broken"))
        assert results == []


class TestKeywordSearch:
    @patch("app.services.vector_search.get_supabase_client")
    def test_returns_results(self, mock_sb):
        svc = _make_search_service()

        mock_result = MagicMock()
        mock_result.data = [{"id": "uuid-2", "topic": "Addition"}]
        mock_query = MagicMock()
        mock_query.limit.return_value = mock_query
        mock_query.or_.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.execute.return_value = mock_result
        sb_instance = MagicMock()
        sb_instance.table.return_value.select.return_value = mock_query
        mock_sb.return_value = sb_instance

        results = asyncio.run(svc.keyword_search("how to add numbers", grade="Class 3"))
        assert len(results) == 1

    @patch("app.services.vector_search.get_supabase_client")
    def test_empty_on_db_error(self, mock_sb):
        svc = _make_search_service()
        mock_sb.side_effect = RuntimeError("DB connection failed")

        results = asyncio.run(svc.keyword_search("broken"))
        assert results == []


class TestHybridSearch:
    @patch("app.services.vector_search.get_supabase_client")
    @patch("app.services.vector_search.get_embedding_service")
    def test_fuses_three_sources(self, mock_embed_svc, mock_sb):
        svc = _make_search_service()

        # Mock embedding
        embed_instance = MagicMock()
        embed_instance.embed_text = AsyncMock(return_value=[0.1] * 768)
        mock_embed_svc.return_value = embed_instance

        # Mock Supabase — rpc is called twice (match_curriculum + match_curriculum_embeddings)
        mock_rpc_result_curriculum = MagicMock()
        mock_rpc_result_curriculum.data = [
            {"id": "uuid-1", "topic": "Fractions", "similarity": 0.85},
        ]
        mock_rpc_result_embeddings = MagicMock()
        mock_rpc_result_embeddings.data = [
            {"id": "uuid-emb-1", "chunk_text": "Textbook fractions", "similarity": 0.80},
        ]

        # rpc returns different results for different RPC names
        def rpc_side_effect(name, params):
            mock_rpc = MagicMock()
            if name == "match_curriculum":
                mock_rpc.execute.return_value = mock_rpc_result_curriculum
            else:
                mock_rpc.execute.return_value = mock_rpc_result_embeddings
            return mock_rpc

        mock_table_result = MagicMock()
        mock_table_result.data = [
            {"id": "uuid-2", "topic": "Decimals"},
        ]
        mock_query = MagicMock()
        mock_query.limit.return_value = mock_query
        mock_query.or_.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.execute.return_value = mock_table_result

        sb_instance = MagicMock()
        sb_instance.rpc.side_effect = rpc_side_effect
        sb_instance.table.return_value.select.return_value = mock_query
        mock_sb.return_value = sb_instance

        results = asyncio.run(svc.hybrid_search("add fractions"))
        assert len(results) >= 1
        # Semantic result (weight 0.7) should be ranked first
        assert results[0]["id"] == "uuid-1"

    @patch("app.services.vector_search.get_supabase_client")
    @patch("app.services.vector_search.get_embedding_service")
    def test_graceful_degradation(self, mock_embed_svc, mock_sb):
        """If all searches fail, returns [] instead of crashing."""
        svc = _make_search_service()

        embed_instance = MagicMock()
        embed_instance.embed_text = AsyncMock(side_effect=RuntimeError("fail"))
        mock_embed_svc.return_value = embed_instance
        mock_sb.side_effect = RuntimeError("fail")

        results = asyncio.run(svc.hybrid_search("broken"))
        assert results == []
