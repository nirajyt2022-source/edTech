"""
Tests for pdf_ingestion service — chunk_text() and ingest_text_chunks().

All tests use unittest.mock — no real API calls or database access.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio

from app.services.pdf_ingestion import PDFIngestionService, chunk_text


# ---------------------------------------------------------------------------
# chunk_text() Unit Tests
# ---------------------------------------------------------------------------


class TestChunkText:
    def test_empty_string(self):
        assert chunk_text("") == []

    def test_whitespace_only(self):
        assert chunk_text("   \n\t  ") == []

    def test_short_text_single_chunk(self):
        """Text under ~800 chars should be returned as a single chunk."""
        text = "Fractions are parts of a whole. The numerator is on top."
        chunks = chunk_text(text, target=500)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_splits(self):
        """Text over target * 1.6 should split into multiple chunks."""
        # Build a text with many sentences (~1500 chars)
        sentences = [f"Sentence number {i} is about fractions and mathematics." for i in range(30)]
        text = " ".join(sentences)
        assert len(text) > 800  # Confirm it's long enough

        chunks = chunk_text(text, target=500, overlap=50)
        assert len(chunks) > 1
        # All chunks should be non-empty
        for c in chunks:
            assert len(c.strip()) > 0

    def test_overlap_carries_context(self):
        """Overlap should carry tail of previous chunk into next."""
        sentences = [f"Sentence {i} discusses topic {i} in detail here." for i in range(30)]
        text = " ".join(sentences)
        chunks = chunk_text(text, target=300, overlap=50)

        if len(chunks) >= 2:
            # Last 50 chars of chunk 0 should appear in chunk 1's beginning
            tail = chunks[0][-50:]
            assert tail in chunks[1]

    def test_custom_target(self):
        """Smaller target should produce more chunks."""
        sentences = [f"This is sentence number {i} about learning." for i in range(40)]
        text = " ".join(sentences)
        big_chunks = chunk_text(text, target=1000)
        small_chunks = chunk_text(text, target=200)
        assert len(small_chunks) >= len(big_chunks)

    def test_boundary_just_under_threshold(self):
        """Text at exactly target*1.6 chars should stay as one chunk."""
        target = 500
        # 800 chars = 500 * 1.6 — should stay as single chunk
        text = "A" * 800
        chunks = chunk_text(text, target=target)
        assert len(chunks) == 1


# ---------------------------------------------------------------------------
# PDFIngestionService Tests (mocked)
# ---------------------------------------------------------------------------


class TestIngestTextChunks:
    @patch("app.services.pdf_ingestion.get_supabase_client")
    @patch("app.services.pdf_ingestion.get_embedding_service")
    def test_inserts_chunks(self, mock_embed_svc, mock_sb):
        svc = PDFIngestionService()

        # Mock embedding
        embed_instance = MagicMock()
        embed_instance.embed_batch = AsyncMock(return_value=[[0.1] * 768, [0.2] * 768])
        mock_embed_svc.return_value = embed_instance

        # Mock Supabase insert
        mock_insert_result = MagicMock()
        mock_insert_result.data = [{"id": "uuid-1"}, {"id": "uuid-2"}]
        mock_insert = MagicMock()
        mock_insert.execute.return_value = mock_insert_result
        sb_instance = MagicMock()
        sb_instance.table.return_value.insert.return_value = mock_insert
        mock_sb.return_value = sb_instance

        count = asyncio.run(
            svc.ingest_text_chunks(
                chunks=["Chunk 1 about fractions.", "Chunk 2 about decimals."],
                grade="Class 4",
                subject="Maths",
                topic="Fractions",
                source_type="textbook_upload",
            )
        )

        assert count == 2
        # Verify embed_batch was called with the chunks
        embed_instance.embed_batch.assert_awaited_once_with(
            ["Chunk 1 about fractions.", "Chunk 2 about decimals."]
        )
        # Verify insert was called
        sb_instance.table.assert_called_with("curriculum_embeddings")

    @patch("app.services.pdf_ingestion.get_supabase_client")
    @patch("app.services.pdf_ingestion.get_embedding_service")
    def test_empty_chunks_returns_zero(self, mock_embed_svc, mock_sb):
        svc = PDFIngestionService()
        count = asyncio.run(
            svc.ingest_text_chunks(chunks=[], grade="Class 4", subject="Maths")
        )
        assert count == 0

    @patch("app.services.pdf_ingestion.get_supabase_client")
    @patch("app.services.pdf_ingestion.get_embedding_service")
    def test_metadata_passed_through(self, mock_embed_svc, mock_sb):
        svc = PDFIngestionService()

        embed_instance = MagicMock()
        embed_instance.embed_batch = AsyncMock(return_value=[[0.1] * 768])
        mock_embed_svc.return_value = embed_instance

        mock_insert_result = MagicMock()
        mock_insert_result.data = [{"id": "uuid-1"}]
        mock_insert = MagicMock()
        mock_insert.execute.return_value = mock_insert_result
        sb_instance = MagicMock()
        sb_instance.table.return_value.insert.return_value = mock_insert
        mock_sb.return_value = sb_instance

        meta = {"chapter": "Chapter 8", "key_concepts": ["numerator", "denominator"]}
        asyncio.run(
            svc.ingest_text_chunks(
                chunks=["Some text"],
                grade="Class 4",
                subject="Maths",
                metadata=meta,
            )
        )

        # Verify the inserted row includes metadata
        insert_call_args = sb_instance.table.return_value.insert.call_args[0][0]
        assert insert_call_args[0]["metadata"] == meta


class TestIngestText:
    @patch("app.services.pdf_ingestion.get_supabase_client")
    @patch("app.services.pdf_ingestion.get_embedding_service")
    def test_empty_text_returns_zero(self, mock_embed_svc, mock_sb):
        svc = PDFIngestionService()
        count = asyncio.run(
            svc.ingest_text(raw_text="", grade="Class 4", subject="Maths")
        )
        assert count == 0

    @patch("app.services.pdf_ingestion.get_supabase_client")
    @patch("app.services.pdf_ingestion.get_embedding_service")
    def test_short_text_single_chunk(self, mock_embed_svc, mock_sb):
        svc = PDFIngestionService()

        embed_instance = MagicMock()
        embed_instance.embed_batch = AsyncMock(return_value=[[0.1] * 768])
        mock_embed_svc.return_value = embed_instance

        mock_insert_result = MagicMock()
        mock_insert_result.data = [{"id": "uuid-1"}]
        mock_insert = MagicMock()
        mock_insert.execute.return_value = mock_insert_result
        sb_instance = MagicMock()
        sb_instance.table.return_value.insert.return_value = mock_insert
        mock_sb.return_value = sb_instance

        count = asyncio.run(
            svc.ingest_text(
                raw_text="Short text about fractions.",
                grade="Class 4",
                subject="Maths",
                topic="Fractions",
            )
        )
        assert count == 1
