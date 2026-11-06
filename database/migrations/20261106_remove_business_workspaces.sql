-- Remove the multi-tenant Business workspace feature entirely: membership/
-- roles/invitations/seat-based billing, Work Hub (projects/tasks), manual
-- Status Reports, Business Knowledge docs, and privacy-first Sharing.
-- Confirmed before this migration: no real paying Business customers exist
-- (test/demo data only), so this is a pure schema cleanup, not a sunset
-- process needing a notice window.
--
-- Every personal user's own data (chat_sessions/history/session_memory/
-- knowledge_documents/subscriptions) already carries a real user_id --
-- workspace_id was always a redundant second dimension, resolved 1:1 from
-- user_id via the now-removed ensure_personal_workspace. Dropping it is a
-- column removal, not a rekey: no backfill needed, and no row becomes
-- orphaned (any leftover demo Business-subscription row is explicitly
-- deleted below, before the column that identifies it as such is gone).
--
-- These tables/columns are also removed from database/postgres_schema.sql
-- so a fresh deploy doesn't recreate them. Must not run before the backend
-- code that stops reading/writing these columns (web/backend's Phase 1/2
-- removal pass) is part of the same deploy -- chat_sessions/history/
-- session_memory currently have workspace_id NOT NULL, so running the new
-- code against the old schema would fail every insert.

BEGIN;

-- subscriptions: delete any leftover demo/test Business-workspace rows
-- before dropping the column that distinguishes them -- without this
-- they'd become orphaned rows (user_id NULL, no workspace_id left to
-- identify them by). The existing subscriptions_subject_check CHECK
-- guarantees every remaining row already has user_id set once this DELETE
-- is done, so tightening it to NOT NULL right after is safe.
DELETE FROM subscriptions WHERE workspace_id IS NOT NULL;
ALTER TABLE subscriptions DROP CONSTRAINT IF EXISTS subscriptions_subject_check;
ALTER TABLE subscriptions DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE subscriptions ALTER COLUMN user_id SET NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'subscriptions_user_required_check'
    ) THEN
        ALTER TABLE subscriptions
            ADD CONSTRAINT subscriptions_user_required_check CHECK (user_id IS NOT NULL);
    END IF;
END;
$$;

-- chat_sessions/history/session_memory: workspace_id was always resolved
-- 1:1 from user_id (see models/history.py's former _resolve_workspace_id),
-- so every row's user_id is already correct and sufficient on its own.
ALTER TABLE chat_sessions DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE history DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE session_memory DROP COLUMN IF EXISTS workspace_id;

-- knowledge_documents: drop the workspace-curated tier, keeping the
-- global (user_id IS NULL) and personal (user_id set) tiers.
ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS workspace_id;

-- notifications and ai_cost_log: workspace_id was dead weight on every
-- personal row already -- neither model's own query methods ever read it
-- back.
ALTER TABLE notifications DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE ai_cost_log DROP COLUMN IF EXISTS workspace_id;

-- Business-only feature tables, dependents dropped before the workspaces/
-- workspace_invitations rows they reference.
DROP TABLE IF EXISTS shared_artifacts;
DROP TABLE IF EXISTS status_reports;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS workspace_seat_requests;
DROP TABLE IF EXISTS workspace_invitations;
DROP TABLE IF EXISTS workspace_audit_events;
DROP TABLE IF EXISTS workspace_memberships;
DROP TABLE IF EXISTS workspaces;

COMMIT;
