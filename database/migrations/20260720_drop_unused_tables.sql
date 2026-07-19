-- Drop tables that were defined in the schema but never queried by the
-- running application (verified against every model/route/service under
-- web/backend and scripts/):
--   - Email caching (message lists, bodies, AI summaries) and the
--     daily-overview/report feature all actually persist through the
--     generic `cache` table (models/cache.py), never gmail_messages,
--     gmail_attachments, email_summaries, or email_daily_reports.
--   - Chat turn logging goes through `history` (models/history.py),
--     never chat_messages.
--   - ai_requests has no model, route, or service touching it at all.
-- These tables are also removed from database/postgres_schema.sql so a
-- fresh deploy doesn't recreate them.

BEGIN;

-- meeting_suggestions.message_id is the only column anywhere that
-- references gmail_messages(id), and it's itself unused (no model/route
-- ever reads or writes it -- meeting_suggestion.py keys off email_id
-- instead). Drop it first so gmail_messages has no remaining dependents.
ALTER TABLE meeting_suggestions DROP COLUMN IF EXISTS message_id;

DROP TABLE IF EXISTS gmail_attachments;
DROP TABLE IF EXISTS email_summaries;
DROP TABLE IF EXISTS gmail_messages;
DROP TABLE IF EXISTS email_daily_reports;
DROP TABLE IF EXISTS chat_messages;
DROP TABLE IF EXISTS ai_requests;

-- Only email_summaries.summary_type used this enum.
DROP TYPE IF EXISTS email_summary_type;

COMMIT;
