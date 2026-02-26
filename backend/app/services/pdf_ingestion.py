"""
PDF / text ingestion service — chunk text, embed, and store in curriculum_embeddings.

Used by the textbook upload flow to persist extracted content for RAG search.

Usage:
    from app.services.pdf_ingestion import get_pdf_ingestion_service

    svc = get_pdf_ingestion_service()
    count = await svc.ingest_text(
        raw_text="The numerator tells ...",
        grade="Class 4", subject="Maths", topic="Fractions",
        source_type="textbook_upload",
    )
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.core.deps import get_supabase_client
from app.services.embedding import get_embedding_service

logger = structlog.get_logger("skolar.pdf_ingestion")

# Sentence-boundary regex: split on '. ', '! ', '? ' followed by uppercase or end
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u0900-\u097F])")


def chunk_text(text: str, target: int = 500, overlap: int = 50) -> list[str]:
    """Split *text* into chunks of roughly *target* characters at sentence boundaries.

    - If *text* is shorter than target * 1.6 (≈800), return it as a single chunk.
    - Otherwise split on sentence boundaries, accumulating until *target* is reached,
      then carry over the last *overlap* characters to the next chunk.
    - Returns [] for empty / whitespace-only input.
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= int(target * 1.6):
        return [text]

    sentences = _SENTENCE_RE.split(text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) > target and current:
            chunks.append(current.strip())
            # Carry overlap from the end of the previous chunk
            current = current[-overlap:] + " " + sentence if overlap else sentence
        else:
            current = (current + " " + sentence) if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks


class PDFIngestionService:
    """Chunk text, embed via Gemini, and store rows in curriculum_embeddings."""

    async def ingest_text(
        self,
        raw_text: str,
        grade: str,
        subject: str,
        topic: str = "",
        source_type: str = "pdf",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Chunk *raw_text*, embed each chunk, and store in DB. Returns row count."""
        chunks = chunk_text(raw_text)
        if not chunks:
            logger.warning("ingest_text_empty", grade=grade, subject=subject)
            return 0

        return await self.ingest_text_chunks(
            chunks=chunks,
            grade=grade,
            subject=subject,
            topic=topic,
            source_type=source_type,
            metadata=metadata,
        )

    async def ingest_text_chunks(
        self,
        chunks: list[str],
        grade: str,
        subject: str,
        topic: str = "",
        source_type: str = "pdf",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Embed pre-chunked text and store in curriculum_embeddings. Returns row count."""
        if not chunks:
            return 0

        svc = get_embedding_service()
        vectors = await svc.embed_batch(chunks)

        meta = metadata or {}
        rows = [
            {
                "source_type": source_type,
                "grade": grade,
                "subject": subject,
                "topic": topic,
                "chunk_text": chunk,
                "chunk_index": idx,
                "metadata": meta,
                "embedding": vec,
            }
            for idx, (chunk, vec) in enumerate(zip(chunks, vectors))
        ]

        sb = get_supabase_client()
        result = sb.table("curriculum_embeddings").insert(rows).execute()

        inserted = len(result.data) if result.data else 0
        logger.info(
            "ingest_text_complete",
            source_type=source_type,
            grade=grade,
            subject=subject,
            topic=topic,
            chunks=len(chunks),
            inserted=inserted,
        )
        return inserted

    async def ingest_pdf(
        self,
        file_path: str,
        grade: str,
        subject: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Ingest a PDF file via OCR + chunking. Not yet implemented."""
        raise NotImplementedError("Full PDF OCR ingestion pipeline not yet implemented")


# -- Singleton ----------------------------------------------------------------

_pdf_ingestion: PDFIngestionService | None = None


def get_pdf_ingestion_service() -> PDFIngestionService:
    """Get the singleton PDFIngestionService instance."""
    global _pdf_ingestion
    if _pdf_ingestion is None:
        _pdf_ingestion = PDFIngestionService()
    return _pdf_ingestion
