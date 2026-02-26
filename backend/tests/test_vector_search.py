"""
Tests for VectorSearchService and RRF fusion.

All tests use unittest.mock — no real API calls or database access.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from types import SimpleNamespace

from app.services.vector_search import (
    VectorSearchService,
    _reciprocal_rank_fusion,
    SEMANTIC_WEIGHT,
    KEYWORD_WEIGHT,
    RRF_K,
)


# ---------------------------------------------------------------------------
# RRF Unit Tests
# ---------------------------------------------------------------------------

class TestReciprocalRankFusion:
    def test_semantic_ranked_higher_than_keyword(self):
        """Semantic-only result should outscore keyword-only result."""
        semantic = [{"id": "sem-1", "topic": "Fractions"}]
        keyword = [{"id": "kw-1", "topic": "Decimals"}]

        fused = _reciprocal_rank_fusion(semantic, keyword, top_k=2)

        assert len(fused) == 2
        # Semantic result (weight 0.7) should be first
        assert fused[0]["id"] == "sem-1"
        assert fused[1]["id"] == "kw-1"

    def test_overlapping_results_get_boosted(self):
        """A document appearing in both lists gets a higher combined score."""
        shared_doc = {"id": "shared-1", "topic": "Fractions"}
        semantic = [shared_doc, {"id": "sem-only", "topic": "Decimals"}]
        keyword = [shared_doc, {"id": "kw-only", "topic": "Geometry"}]

        fused = _reciprocal_rank_fusion(semantic, keyword, top_k=3)

        # Shared doc should be ranked first
        assert fused[0]["id"] == "shared-1"

    def test_empty_lists(self):
        assert _reciprocal_rank_fusion([], [], top_k=3) == []

    def test_top_k_limits_output(self):
        semantic = [{"id": f"s{i}"} for i in range(5)]
        keyword = [{"id": f"k{i}"} for i in range(5)]

        fused = _reciprocal_rank_fusion(semantic, keyword, top_k=2)
        assert len(fused) == 2

    def test_scores_use_correct_weights(self):
        """Verify the RRF formula: weight / (k + rank + 1)."""
        semantic = [{"id": "a"}]
        keyword = [{"id": "b"}]

        fused = _reciprocal_rank_fusion(semantic, keyword, top_k=2)

        # Score for "a": SEMANTIC_WEIGHT / (RRF_K + 0 + 1) = 0.7 / 61
        # Score for "b": KEYWORD_WEIGHT / (RRF_K + 0 + 1) = 0.3 / 61
        expected_a = SEMANTIC_WEIGHT / (RRF_K + 1)
        expected_b = KEYWORD_WEIGHT / (RRF_K + 1)
        assert expected_a > expected_b
        assert fused[0]["id"] == "a"


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
    def test_fuses_results(self, mock_embed_svc, mock_sb):
        svc = _make_search_service()

        # Mock embedding
        embed_instance = MagicMock()
        embed_instance.embed_text = AsyncMock(return_value=[0.1] * 768)
        mock_embed_svc.return_value = embed_instance

        # Mock Supabase (both RPC and table calls)
        mock_rpc_result = MagicMock()
        mock_rpc_result.data = [
            {"id": "uuid-1", "topic": "Fractions", "similarity": 0.85},
        ]
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = mock_rpc_result

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
        sb_instance.rpc.return_value = mock_rpc
        sb_instance.table.return_value.select.return_value = mock_query
        mock_sb.return_value = sb_instance

        results = asyncio.run(svc.hybrid_search("add fractions"))
        assert len(results) >= 1
        # Semantic result should come first due to higher weight
        assert results[0]["id"] == "uuid-1"

    @patch("app.services.vector_search.get_supabase_client")
    @patch("app.services.vector_search.get_embedding_service")
    def test_graceful_degradation(self, mock_embed_svc, mock_sb):
        """If both searches fail, returns [] instead of crashing."""
        svc = _make_search_service()

        embed_instance = MagicMock()
        embed_instance.embed_text = AsyncMock(side_effect=RuntimeError("fail"))
        mock_embed_svc.return_value = embed_instance
        mock_sb.side_effect = RuntimeError("fail")

        results = asyncio.run(svc.hybrid_search("broken"))
        assert results == []
