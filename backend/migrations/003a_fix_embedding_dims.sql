-- Migration 003a: Fix embedding dimensions from 768 → 3072
-- gemini-embedding-001 returns 3072 dimensions, not 768.
-- Run this in Supabase SQL Editor if you already ran 003_rag_pgvector.sql with 768 dims.

-- Drop old indexes (they reference the old vector size)
DROP INDEX IF EXISTS idx_curriculum_content_embedding;
DROP INDEX IF EXISTS idx_curriculum_embeddings_hnsw;

-- Alter columns from vector(768) to vector(3072)
ALTER TABLE curriculum_content
  ALTER COLUMN embedding TYPE vector(3072);

ALTER TABLE curriculum_embeddings
  ALTER COLUMN embedding TYPE vector(3072);

-- Recreate HNSW indexes with correct dimensions
CREATE INDEX IF NOT EXISTS idx_curriculum_content_embedding
  ON curriculum_content USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_curriculum_embeddings_hnsw
  ON curriculum_embeddings USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Recreate RPC with correct vector size
CREATE OR REPLACE FUNCTION match_curriculum(
  query_embedding vector(3072),
  match_count int DEFAULT 5,
  filter_grade text DEFAULT NULL,
  filter_subject text DEFAULT NULL,
  similarity_threshold float DEFAULT 0.3
) RETURNS TABLE (
  id uuid, grade text, subject text, topic text,
  chapter_name text, ncert_summary text,
  key_concepts jsonb, learning_outcomes jsonb, common_mistakes jsonb,
  difficulty_notes jsonb, grade_vocabulary jsonb,
  question_types jsonb, real_world_contexts jsonb,
  similarity float
) LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT cc.id, cc.grade, cc.subject, cc.topic,
    cc.chapter_name, cc.ncert_summary,
    cc.key_concepts, cc.learning_outcomes, cc.common_mistakes,
    cc.difficulty_notes, cc.grade_vocabulary,
    cc.question_types, cc.real_world_contexts,
    (1 - (cc.embedding <=> query_embedding))::float AS similarity
  FROM curriculum_content cc
  WHERE cc.embedding IS NOT NULL
    AND (filter_grade IS NULL OR cc.grade = filter_grade)
    AND (filter_subject IS NULL OR cc.subject = filter_subject)
    AND 1 - (cc.embedding <=> query_embedding) > similarity_threshold
  ORDER BY cc.embedding <=> query_embedding
  LIMIT match_count;
END; $$;
