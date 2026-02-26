"""
PDF ingestion service — interface stub for future PDF chunking + embedding pipeline.

When implemented, this will:
1. Accept PDF uploads (textbook pages, worksheets)
2. Extract text via OCR / PDF parsing
3. Chunk text into semantic segments
4. Embed chunks via EmbeddingService
5. Store in curriculum_embeddings table

For now, this is a placeholder interface.
"""

from __future__ import annotations


class PDFIngestionService:
    """Stub for future PDF ingestion pipeline."""

    async def ingest_pdf(
        self,
        file_path: str,
        grade: str,
        subject: str,
        metadata: dict | None = None,
    ) -> dict:
        """Ingest a PDF file, chunk it, embed chunks, and store in DB."""
        raise NotImplementedError("PDF ingestion pipeline not yet implemented")

    async def ingest_text_chunks(
        self,
        chunks: list[str],
        grade: str,
        subject: str,
        topic: str = "",
        source_type: str = "pdf",
    ) -> int:
        """Embed and store pre-chunked text. Returns count of inserted rows."""
        raise NotImplementedError("PDF ingestion pipeline not yet implemented")
