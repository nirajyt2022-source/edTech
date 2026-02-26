-- Migration 003: pgvector semantic search for RAG
-- Pre-requisite: Enable pgvector extension via Supabase Dashboard → Database → Extensions → "vector" → Enable
-- Then run this SQL in the Supabase SQL Editor.

CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column to existing curriculum_content table
ALTER TABLE curriculum_content
  ADD COLUMN IF NOT EXISTS embedding vector(3072);

-- HNSW index for fast cosine similarity
CREATE INDEX IF NOT EXISTS idx_curriculum_content_embedding
  ON curriculum_content USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Standalone table for future PDF chunks / additional content
CREATE TABLE IF NOT EXISTS curriculum_embeddings (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  source_type text NOT NULL DEFAULT 'curriculum',
  grade text NOT NULL,
  subject text NOT NULL,
  topic text NOT NULL DEFAULT '',
  chunk_text text NOT NULL,
  chunk_index int NOT NULL DEFAULT 0,
  metadata jsonb DEFAULT '{}',
  embedding vector(3072) NOT NULL,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_curriculum_embeddings_hnsw
  ON curriculum_embeddings USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_curriculum_embeddings_grade_subject
  ON curriculum_embeddings (grade, subject);

-- RLS for curriculum_embeddings (same policy as curriculum_content)
ALTER TABLE curriculum_embeddings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'curriculum_embeddings' AND policyname = 'embeddings_readable_by_all'
  ) THEN
    CREATE POLICY "embeddings_readable_by_all" ON curriculum_embeddings
      FOR SELECT TO authenticated USING (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'curriculum_embeddings' AND policyname = 'embeddings_writable_by_service'
  ) THEN
    CREATE POLICY "embeddings_writable_by_service" ON curriculum_embeddings
      FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $$;

-- RPC: match_curriculum — cosine similarity search on curriculum_content
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
