-- Phase 4 ("Personal data va privacy-first sharing", design doc section 9.7):
-- a user explicitly shares one piece of their own personal data (an email
-- summary, calendar event, etc.) into a Business workspace. Postgres-only,
-- inherently cross-user once shared. Safe to run multiple times.
--
-- See postgres_schema.sql's copy of this DDL for the full privacy-model
-- rationale (confirm-before-sharing only, sharer-only revoke, immutable
-- content, owner/admin see it once shared like any other workspace
-- content).

CREATE TABLE IF NOT EXISTS shared_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_by_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    content JSONB NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'workspace',
    revoked_at TIMESTAMPTZ,
    retention_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT shared_artifacts_source_type_check CHECK (
        source_type IN ('email_summary', 'calendar_event', 'note', 'document_reference')
    ),
    CONSTRAINT shared_artifacts_visibility_check CHECK (visibility IN ('workspace', 'private'))
);

CREATE INDEX IF NOT EXISTS idx_shared_artifacts_workspace
    ON shared_artifacts (workspace_id) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_shared_artifacts_owner
    ON shared_artifacts (source_owner_user_id) WHERE revoked_at IS NULL;

DROP TRIGGER IF EXISTS trg_shared_artifacts_updated_at ON shared_artifacts;
CREATE TRIGGER trg_shared_artifacts_updated_at
BEFORE UPDATE ON shared_artifacts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
