-- Remove indexes duplicated by UNIQUE constraints or unused by current queries,
-- then add composite indexes that match the application's actual filters.
-- This migration changes no table, column, constraint, or row data.

BEGIN;

-- The UNIQUE constraints already provide equivalent B-tree indexes.
DROP INDEX IF EXISTS idx_oauth_tokens_user_provider;
DROP INDEX IF EXISTS idx_gmail_attachments_message;
DROP INDEX IF EXISTS idx_email_summaries_user_message;
DROP INDEX IF EXISTS idx_email_daily_reports_user_date;
DROP INDEX IF EXISTS idx_cache_user_key;

-- No current query filters JSON cache values, cache namespaces, calendar ETags,
-- or Google update timestamps. ETags are read through calendar_events_unique.
DROP INDEX IF EXISTS idx_cache_namespace;
DROP INDEX IF EXISTS idx_cache_expires_at;
DROP INDEX IF EXISTS idx_cache_value_gin;
DROP INDEX IF EXISTS idx_calendar_events_user_etag;
DROP INDEX IF EXISTS idx_calendar_events_google_updated;

-- Match current per-user expiry cleanup and ordered lookup queries.
CREATE INDEX IF NOT EXISTS idx_cache_user_expires
    ON cache (user_id, expires_at);

DROP INDEX IF EXISTS idx_knowledge_documents_user;
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_user_created
    ON knowledge_documents (user_id, created_at DESC);

DROP INDEX IF EXISTS idx_intent_patterns_status;
CREATE INDEX IF NOT EXISTS idx_intent_patterns_status_created
    ON intent_patterns (status, created_at DESC);

COMMIT;
