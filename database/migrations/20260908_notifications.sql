-- Phase 6 ("Billing automation and production hardening", design doc section
-- 15/9.9): in-app notifications for the subscription lifecycle scheduler
-- (renewal reminders, grace/read-only transitions). Email delivery is
-- explicitly deferred per section 16's already-approved decision -- v1 is
-- in-app only.
--
-- The UNIQUE(recipient_user_id, dedupe_key) constraint IS the idempotency
-- mechanism: the scheduler always INSERTs with ON CONFLICT DO NOTHING, so
-- two overlapping scheduler runs (or, if Railway ever runs multiple app
-- workers, two workers' threads firing at once) can never double-notify.
-- Safe to run multiple times.

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    body TEXT,
    action_url TEXT,
    dedupe_key TEXT NOT NULL,
    read_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT notifications_severity_check CHECK (severity IN ('info', 'warning', 'critical')),
    CONSTRAINT notifications_recipient_dedupe_unique UNIQUE (recipient_user_id, dedupe_key)
);

CREATE INDEX IF NOT EXISTS idx_notifications_recipient_unread
    ON notifications (recipient_user_id, created_at DESC) WHERE read_at IS NULL;
