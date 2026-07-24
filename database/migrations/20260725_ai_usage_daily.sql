-- Per-user daily counter for AI-costing actions (chat messages, email AI
-- summaries, draft replies, plan-day suggestions), used to gate the free
-- tier of the Freemium/Premium split. Increment is done via a single
-- INSERT ... ON CONFLICT ... DO UPDATE SET count = count + 1 RETURNING count
-- so it stays race-free and shared across gunicorn workers/restarts, unlike
-- the in-memory limiter in utils/security.py. Safe to run multiple times.

CREATE TABLE IF NOT EXISTS ai_usage_daily (
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    usage_date DATE NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, action, usage_date)
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_daily_user_date
    ON ai_usage_daily (user_id, usage_date);
