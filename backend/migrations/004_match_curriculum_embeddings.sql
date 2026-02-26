-- Migration 004: RPC for semantic search on curriculum_embeddings table
-- Run this in the Supabase SQL Editor after migration 003.

-- match_curriculum_embeddings — cosine similarity search on curriculum_embeddings
-- Mirrors match_curriculum but queries the embeddings table (PDF chunks, textbook uploads, etc.)
CREATE OR REPLACE FUNCTION match_curriculum_embeddings(
  query_embedding vector(768),
  match_count int DEFAULT 5,
  filter_grade text DEFAULT NULL,
  filter_subject text DEFAULT NULL,
  filter_source_type text DEFAULT NULL,
  similarity_threshold float DEFAULT 0.3
) RETURNS TABLE (
  id uuid,
  source_type text,
  grade text,
  subject text,
  topic text,
  chunk_text text,
  chunk_index int,
  metadata jsonb,
  similarity float
) LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT ce.id, ce.source_type, ce.grade, ce.subject, ce.topic,
    ce.chunk_text, ce.chunk_index, ce.metadata,
    (1 - (ce.embedding <=> query_embedding))::float AS similarity
  FROM curriculum_embeddings ce
  WHERE (filter_grade IS NULL OR ce.grade = filter_grade)
    AND (filter_subject IS NULL OR ce.subject = filter_subject)
    AND (filter_source_type IS NULL OR ce.source_type = filter_source_type)
    AND 1 - (ce.embedding <=> query_embedding) > similarity_threshold
  ORDER BY ce.embedding <=> query_embedding
  LIMIT match_count;
END; $$;
