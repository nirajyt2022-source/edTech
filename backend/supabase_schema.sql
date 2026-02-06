-- Worksheets table to store generated worksheets
CREATE TABLE IF NOT EXISTS worksheets (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  board TEXT,
  grade TEXT,
  subject TEXT,
  topic TEXT,
  difficulty TEXT,
  language TEXT DEFAULT 'English',
  questions JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster user queries
CREATE INDEX IF NOT EXISTS idx_worksheets_user_id ON worksheets(user_id);
CREATE INDEX IF NOT EXISTS idx_worksheets_created_at ON worksheets(created_at DESC);

-- Enable Row Level Security
ALTER TABLE worksheets ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own worksheets
CREATE POLICY "Users can view own worksheets" ON worksheets
  FOR SELECT USING (auth.uid() = user_id);

-- Policy: Users can insert their own worksheets
CREATE POLICY "Users can insert own worksheets" ON worksheets
  FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Policy: Users can delete their own worksheets
CREATE POLICY "Users can delete own worksheets" ON worksheets
  FOR DELETE USING (auth.uid() = user_id);

-- Children table for multi-child profiles
CREATE TABLE IF NOT EXISTS children (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  grade TEXT NOT NULL,
  board TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_children_user_id ON children(user_id);

ALTER TABLE children ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own children" ON children
  FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own children" ON children
  FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own children" ON children
  FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own children" ON children
  FOR DELETE USING (auth.uid() = user_id);

-- Add child_id to worksheets table (run as ALTER if table already exists)
ALTER TABLE worksheets
ADD COLUMN IF NOT EXISTS child_id UUID REFERENCES children(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_worksheets_child_id ON worksheets(child_id);
