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

-- Policy: Users can update their own worksheets
CREATE POLICY "Users can update own worksheets" ON worksheets
  FOR UPDATE USING (auth.uid() = user_id);

-- Add regeneration tracking column
ALTER TABLE worksheets
ADD COLUMN IF NOT EXISTS regeneration_count INT DEFAULT 0;

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

-- User subscriptions table for monetization
CREATE TABLE IF NOT EXISTS user_subscriptions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
  tier TEXT NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'paid')),
  worksheets_generated_this_month INT DEFAULT 0,
  month_reset_at TIMESTAMPTZ DEFAULT DATE_TRUNC('month', NOW()) + INTERVAL '1 month',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user_id ON user_subscriptions(user_id);

ALTER TABLE user_subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own subscription" ON user_subscriptions
  FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own subscription" ON user_subscriptions
  FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own subscription" ON user_subscriptions
  FOR UPDATE USING (auth.uid() = user_id);

-- Function to auto-create subscription for new users
CREATE OR REPLACE FUNCTION create_user_subscription()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO user_subscriptions (user_id, tier)
  VALUES (NEW.id, 'free')
  ON CONFLICT (user_id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to create subscription on user signup
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION create_user_subscription();

-- CBSE Syllabus reference table
CREATE TABLE IF NOT EXISTS cbse_syllabus (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  grade TEXT NOT NULL,
  subject TEXT NOT NULL,
  chapters JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(grade, subject)
);

CREATE INDEX IF NOT EXISTS idx_cbse_syllabus_grade_subject ON cbse_syllabus(grade, subject);

-- CBSE syllabus is read-only for all authenticated users
ALTER TABLE cbse_syllabus ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view CBSE syllabus" ON cbse_syllabus
  FOR SELECT USING (true);

-- Topic preferences table for storing child+subject selections
CREATE TABLE IF NOT EXISTS topic_preferences (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  child_id UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  subject TEXT NOT NULL,
  selected_topics JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(child_id, subject)
);

CREATE INDEX IF NOT EXISTS idx_topic_preferences_child_subject ON topic_preferences(child_id, subject);

ALTER TABLE topic_preferences ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own topic preferences" ON topic_preferences
  FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own topic preferences" ON topic_preferences
  FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own topic preferences" ON topic_preferences
  FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own topic preferences" ON topic_preferences
  FOR DELETE USING (auth.uid() = user_id);

-- Child engagement tracking table
CREATE TABLE IF NOT EXISTS child_engagement (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  child_id UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE UNIQUE,
  total_stars INT DEFAULT 0,
  current_streak INT DEFAULT 0,
  longest_streak INT DEFAULT 0,
  last_activity_date DATE,
  total_worksheets_completed INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_child_engagement_child_id ON child_engagement(child_id);

ALTER TABLE child_engagement ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own child engagement" ON child_engagement
  FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own child engagement" ON child_engagement
  FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own child engagement" ON child_engagement
  FOR UPDATE USING (auth.uid() = user_id);

-- User profiles table for role system (Phase 3)
CREATE TABLE IF NOT EXISTS user_profiles (
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
  role TEXT CHECK (role IN ('parent', 'teacher')),
  active_role TEXT CHECK (active_role IN ('parent', 'teacher')),
  subjects TEXT[],
  grades TEXT[],
  school_name TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile" ON user_profiles
  FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own profile" ON user_profiles
  FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own profile" ON user_profiles
  FOR UPDATE USING (auth.uid() = user_id);

-- Teacher classes table (Phase 3 - Step 2)
CREATE TABLE IF NOT EXISTS teacher_classes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  grade TEXT NOT NULL,
  subject TEXT NOT NULL,
  board TEXT NOT NULL DEFAULT 'CBSE',
  syllabus_source TEXT NOT NULL DEFAULT 'cbse' CHECK (syllabus_source IN ('cbse', 'custom')),
  custom_syllabus JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_teacher_classes_user_id ON teacher_classes(user_id);

ALTER TABLE teacher_classes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own classes" ON teacher_classes
  FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own classes" ON teacher_classes
  FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own classes" ON teacher_classes
  FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own classes" ON teacher_classes
  FOR DELETE USING (auth.uid() = user_id);
