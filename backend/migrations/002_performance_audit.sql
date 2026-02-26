-- ============================================================
-- Migration 002: Performance Audit Fixes
-- Generated from /postgres-best-practices audit
--
-- Covers:
--   1. Composite indexes for common query patterns
--   2. RLS policy optimization (subselect auth.uid())
--   3. Partial index for revision scheduling
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. COMPOSITE INDEXES
-- ────────────────────────────────────────────────────────────

-- 1a. worksheets: list query filters by user_id + orders by created_at DESC
--     Current: separate idx_worksheets_user_id and idx_worksheets_created_at
--     Problem: Postgres can't merge two B-tree indexes efficiently for this pattern
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_worksheets_user_created
  ON worksheets (user_id, created_at DESC);

-- 1b. worksheets: class dashboard queries filter by class_id, then extract child_id
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_worksheets_class_child
  ON worksheets (class_id, child_id)
  WHERE class_id IS NOT NULL;

-- 1c. learning_sessions: history endpoint orders by created_at DESC per child
--     Current: idx_ls_child exists but doesn't cover the ORDER BY
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ls_child_created
  ON learning_sessions (child_id, created_at DESC);

-- 1d. topic_mastery: recommendation endpoint needs mastery_level for sorting
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tm_child_level
  ON topic_mastery (child_id, mastery_level);

-- 1e. topic_mastery: revision scheduler needs revision_due_at filtering
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tm_revision_due
  ON topic_mastery (revision_due_at)
  WHERE revision_due_at IS NOT NULL;


-- ────────────────────────────────────────────────────────────
-- 2. RLS POLICY OPTIMIZATION
--    Wrap auth.uid() in (select ...) to force single evaluation
--    per query instead of per-row function call.
-- ────────────────────────────────────────────────────────────

-- 2a. worksheets — direct user_id match
DROP POLICY IF EXISTS "Users can view own worksheets" ON worksheets;
CREATE POLICY "Users can view own worksheets" ON worksheets
  FOR SELECT USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can insert own worksheets" ON worksheets;
CREATE POLICY "Users can insert own worksheets" ON worksheets
  FOR INSERT WITH CHECK ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can delete own worksheets" ON worksheets;
CREATE POLICY "Users can delete own worksheets" ON worksheets
  FOR DELETE USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can update own worksheets" ON worksheets;
CREATE POLICY "Users can update own worksheets" ON worksheets
  FOR UPDATE USING ((select auth.uid()) = user_id);

-- 2b. children
DROP POLICY IF EXISTS "Users can view own children" ON children;
CREATE POLICY "Users can view own children" ON children
  FOR SELECT USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can insert own children" ON children;
CREATE POLICY "Users can insert own children" ON children
  FOR INSERT WITH CHECK ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can update own children" ON children;
CREATE POLICY "Users can update own children" ON children
  FOR UPDATE USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can delete own children" ON children;
CREATE POLICY "Users can delete own children" ON children
  FOR DELETE USING ((select auth.uid()) = user_id);

-- 2c. user_subscriptions
DROP POLICY IF EXISTS "Users can view own subscription" ON user_subscriptions;
CREATE POLICY "Users can view own subscription" ON user_subscriptions
  FOR SELECT USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can insert own subscription" ON user_subscriptions;
CREATE POLICY "Users can insert own subscription" ON user_subscriptions
  FOR INSERT WITH CHECK ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can update own subscription" ON user_subscriptions;
CREATE POLICY "Users can update own subscription" ON user_subscriptions
  FOR UPDATE USING ((select auth.uid()) = user_id);

-- 2d. topic_preferences
DROP POLICY IF EXISTS "Users can view own topic preferences" ON topic_preferences;
CREATE POLICY "Users can view own topic preferences" ON topic_preferences
  FOR SELECT USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can insert own topic preferences" ON topic_preferences;
CREATE POLICY "Users can insert own topic preferences" ON topic_preferences
  FOR INSERT WITH CHECK ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can update own topic preferences" ON topic_preferences;
CREATE POLICY "Users can update own topic preferences" ON topic_preferences
  FOR UPDATE USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can delete own topic preferences" ON topic_preferences;
CREATE POLICY "Users can delete own topic preferences" ON topic_preferences
  FOR DELETE USING ((select auth.uid()) = user_id);

-- 2e. child_engagement
DROP POLICY IF EXISTS "Users can view own child engagement" ON child_engagement;
CREATE POLICY "Users can view own child engagement" ON child_engagement
  FOR SELECT USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can insert own child engagement" ON child_engagement;
CREATE POLICY "Users can insert own child engagement" ON child_engagement
  FOR INSERT WITH CHECK ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can update own child engagement" ON child_engagement;
CREATE POLICY "Users can update own child engagement" ON child_engagement
  FOR UPDATE USING ((select auth.uid()) = user_id);

-- 2f. user_profiles
DROP POLICY IF EXISTS "Users can view own profile" ON user_profiles;
CREATE POLICY "Users can view own profile" ON user_profiles
  FOR SELECT USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can insert own profile" ON user_profiles;
CREATE POLICY "Users can insert own profile" ON user_profiles
  FOR INSERT WITH CHECK ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can update own profile" ON user_profiles;
CREATE POLICY "Users can update own profile" ON user_profiles
  FOR UPDATE USING ((select auth.uid()) = user_id);

-- 2g. teacher_classes
DROP POLICY IF EXISTS "Users can view own classes" ON teacher_classes;
CREATE POLICY "Users can view own classes" ON teacher_classes
  FOR SELECT USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can insert own classes" ON teacher_classes;
CREATE POLICY "Users can insert own classes" ON teacher_classes
  FOR INSERT WITH CHECK ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can update own classes" ON teacher_classes;
CREATE POLICY "Users can update own classes" ON teacher_classes
  FOR UPDATE USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can delete own classes" ON teacher_classes;
CREATE POLICY "Users can delete own classes" ON teacher_classes
  FOR DELETE USING ((select auth.uid()) = user_id);

-- 2h. Learning graph tables — child_id IN (children subquery)
--     Optimize: wrap auth.uid() in subselect + use EXISTS for clarity
DROP POLICY IF EXISTS "users_see_own_child_sessions" ON learning_sessions;
CREATE POLICY "users_see_own_child_sessions" ON learning_sessions
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM children
      WHERE children.id = learning_sessions.child_id
        AND children.user_id = (select auth.uid())
    )
  );

DROP POLICY IF EXISTS "users_see_own_topic_mastery" ON topic_mastery;
CREATE POLICY "users_see_own_topic_mastery" ON topic_mastery
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM children
      WHERE children.id = topic_mastery.child_id
        AND children.user_id = (select auth.uid())
    )
  );

DROP POLICY IF EXISTS "users_see_own_summary" ON child_learning_summary;
CREATE POLICY "users_see_own_summary" ON child_learning_summary
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM children
      WHERE children.id = child_learning_summary.child_id
        AND children.user_id = (select auth.uid())
    )
  );
