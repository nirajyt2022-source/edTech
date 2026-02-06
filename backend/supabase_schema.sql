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
