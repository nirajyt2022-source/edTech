"""
Tests for EmbeddingService.

All tests use unittest.mock — no real Gemini API calls.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mock_embedding(dims=3072):
    """Create a mock embedding response."""
    return SimpleNamespace(values=[0.1] * dims)


def _make_mock_response(count=1, dims=3072):
    """Create a mock embed_content response."""
    return SimpleNamespace(
        embeddings=[_make_mock_embedding(dims) for _ in range(count)]
    )


def _get_service():
    """Create a fresh EmbeddingService with mocked google-genai client."""
    # Reset singleton
    import app.services.embedding as mod
    mod._embedding_service = None

    with patch("app.services.embedding.get_settings") as mock_settings:
        mock_settings.return_value = SimpleNamespace(gemini_api_key="fake-key")
        with patch("google.genai.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_client_cls.return_value = mock_instance
            from app.services.embedding import EmbeddingService
            svc = EmbeddingService(api_key="fake-key")
            svc._client = mock_instance
            return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmbedText:
    def test_returns_3072_dims(self):
        svc = _get_service()
        svc._client.models.embed_content.return_value = _make_mock_response(1, 3072)

        result = asyncio.run(svc.embed_text("How do I add fractions?"))
        assert len(result) == 3072
        assert all(isinstance(v, float) for v in result)

    def test_empty_text_returns_zeros(self):
        svc = _get_service()
        result = asyncio.run(svc.embed_text(""))
        assert len(result) == 3072
        assert all(v == 0.0 for v in result)

    def test_caching_avoids_second_call(self):
        svc = _get_service()
        svc._client.models.embed_content.return_value = _make_mock_response(1, 3072)

        # First call — hits API
        result1 = asyncio.run(svc.embed_text("test query"))
        assert svc._client.models.embed_content.call_count == 1

        # Second call — cache hit, no API call
        result2 = asyncio.run(svc.embed_text("test query"))
        assert svc._client.models.embed_content.call_count == 1
        assert result1 == result2

    def test_different_texts_not_cached(self):
        svc = _get_service()
        svc._client.models.embed_content.return_value = _make_mock_response(1, 3072)

        asyncio.run(svc.embed_text("query one"))
        asyncio.run(svc.embed_text("query two"))
        assert svc._client.models.embed_content.call_count == 2


class TestEmbedBatch:
    def test_returns_correct_count(self):
        svc = _get_service()
        texts = ["text 1", "text 2", "text 3"]
        svc._client.models.embed_content.return_value = _make_mock_response(3, 3072)

        results = asyncio.run(svc.embed_batch(texts))
        assert len(results) == 3
        assert all(len(v) == 3072 for v in results)

    def test_empty_batch_returns_empty(self):
        svc = _get_service()
        results = asyncio.run(svc.embed_batch([]))
        assert results == []

    def test_batch_caches_individual_texts(self):
        svc = _get_service()
        texts = ["alpha", "beta"]
        svc._client.models.embed_content.return_value = _make_mock_response(2, 3072)

        asyncio.run(svc.embed_batch(texts))

        # Now individual lookups should be cached
        svc._client.models.embed_content.return_value = _make_mock_response(1, 3072)
        result = asyncio.run(svc.embed_text("alpha"))
        # Should not have made an additional API call for "alpha" (cached from batch)
        assert svc._client.models.embed_content.call_count == 1
        assert len(result) == 3072


class TestEmbedError:
    def test_api_error_propagates(self):
        svc = _get_service()
        svc._client.models.embed_content.side_effect = RuntimeError("API quota exceeded")

        try:
            asyncio.run(svc.embed_text("will fail"))
            assert False, "Should have raised"
        except RuntimeError as e:
            assert "API quota exceeded" in str(e)
