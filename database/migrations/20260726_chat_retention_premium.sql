-- Keep the PostgreSQL constraint aligned with the Premium entitlement.
-- Premium chat sessions retain history for up to 365 days. The previous
-- 93-day database constraint rejected new Premium sessions before Bob could
-- process the message, causing POST /api/chat/message to return HTTP 500.
-- Safe to run multiple times.

ALTER TABLE chat_sessions
    DROP CONSTRAINT IF EXISTS chat_sessions_retention_days_check;

ALTER TABLE chat_sessions
    ADD CONSTRAINT chat_sessions_retention_days_check
    CHECK (retention_days BETWEEN 30 AND 365);
