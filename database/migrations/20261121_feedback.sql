-- User feedback: free-text feedback a logged-in user submits from the app,
-- read-only in the admin dashboard (newest first). No ratings/categories/
-- attachments/replies -- see routes/feedback.py and routes/admin.py.
--
-- Only references users(user_id) -- never a table that could later be
-- dropped (see 20260906_shared_artifacts.sql / 20260904_work_hub.sql, both
-- gutted after referencing a dropped table caused a 3-day outage). Safe to
-- run on every deploy forever: CREATE TABLE/INDEX IF NOT EXISTS only.

CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback (created_at DESC);
