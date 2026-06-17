-- Add chat retention support without deleting activity history.
-- Safe to run multiple times.

ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS retention_days SMALLINT NOT NULL DEFAULT 90,
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '90 days'),
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chat_sessions_retention_days_check'
    ) THEN
        ALTER TABLE chat_sessions
            ADD CONSTRAINT chat_sessions_retention_days_check
            CHECK (retention_days BETWEEN 30 AND 93);
    END IF;
END;
$$;

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '90 days');

ALTER TABLE history
    ADD COLUMN IF NOT EXISTS chat_session_id UUID REFERENCES chat_sessions(id) ON DELETE SET NULL;

UPDATE chat_sessions
SET retention_days = 90
WHERE retention_days IS NULL;

UPDATE chat_sessions
SET expires_at = created_at + (retention_days || ' days')::INTERVAL
WHERE expires_at IS NULL;

UPDATE chat_messages message
SET expires_at = session.expires_at
FROM chat_sessions session
WHERE message.session_id = session.id
  AND message.expires_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_expires
    ON chat_sessions (user_id, expires_at);

CREATE INDEX IF NOT EXISTS idx_chat_messages_expires
    ON chat_messages (expires_at);

CREATE INDEX IF NOT EXISTS idx_history_chat_session
    ON history (chat_session_id);

CREATE OR REPLACE FUNCTION cleanup_expired_chat_messages()
RETURNS BIGINT AS $$
DECLARE
    deleted_count BIGINT;
BEGIN
    DELETE FROM chat_messages
    WHERE expires_at <= NOW();

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    UPDATE chat_sessions
    SET archived_at = COALESCE(archived_at, NOW())
    WHERE expires_at <= NOW()
      AND archived_at IS NULL;

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
