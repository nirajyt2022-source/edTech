"""
Embedding service — Gemini text-embedding-004 wrapper.

Uses the google-genai SDK (already a dependency) with TTL caching to avoid
redundant embedding calls for repeated queries.

Usage:
    from app.services.embedding import get_embedding_service

    svc = get_embedding_service()
    vec = await svc.embed_text("How do I add fractions?")  # 768-dim
"""

from __future__ import annotations

import asyncio

import structlog
from cachetools import TTLCache

from app.core.config import get_settings

logger = structlog.get_logger("skolar.embedding")

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_DIMS = 768
BATCH_SIZE = 20


class EmbeddingService:
    """Thin wrapper around Gemini text-embedding-004."""

    def __init__(self, api_key: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._cache: TTLCache[str, list[float]] = TTLCache(maxsize=500, ttl=3600)
        logger.info("embedding_service_init", model=EMBEDDING_MODEL)

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string. Returns 768-dim vector. Cached by text."""
        text = text.strip()
        if not text:
            return [0.0] * EMBEDDING_DIMS

        if text in self._cache:
            logger.debug("embedding_cache_hit", text_preview=text[:40])
            return self._cache[text]

        vec = await self._call_embed([text])
        result = vec[0]
        self._cache[text] = result
        return result

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Processes in chunks of BATCH_SIZE."""
        if not texts:
            return []

        results: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            chunk = texts[i : i + BATCH_SIZE]
            chunk_vecs = await self._call_embed(chunk)
            results.extend(chunk_vecs)
            # Cache each result
            for text, vec in zip(chunk, chunk_vecs):
                self._cache[text.strip()] = vec

        return results

    async def _call_embed(self, texts: list[str]) -> list[list[float]]:
        """Call the Gemini embedding API (blocking SDK, run in thread)."""
        try:
            response = await asyncio.to_thread(
                self._client.models.embed_content,
                model=EMBEDDING_MODEL,
                contents=texts,
            )
            return [e.values for e in response.embeddings]
        except Exception as e:
            logger.error("embedding_api_error", error=str(e), count=len(texts))
            raise


# -- Singleton ----------------------------------------------------------------

_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get the singleton EmbeddingService instance."""
    global _embedding_service
    if _embedding_service is None:
        settings = get_settings()
        _embedding_service = EmbeddingService(api_key=settings.gemini_api_key)
    return _embedding_service
