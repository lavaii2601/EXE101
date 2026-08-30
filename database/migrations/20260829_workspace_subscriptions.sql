-- Phase 2 (Subscription/Seat/Entitlement foundation): extend the existing
-- `subscriptions` table so a row can belong to a Business workspace instead
-- of only a personal user_id, and add workspace_seat_requests for the
-- "seat capacity full" flow (design doc sections 6.4-6.9, 9.4-9.5).
-- Safe to run multiple times.

ALTER TABLE subscriptions
    ALTER COLUMN user_id DROP NOT NULL;

ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS workspace_id UUID,
    ADD COLUMN IF NOT EXISTS included_seats INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS extra_seats INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS grace_period_ends_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'subscriptions_workspace_fkey'
    ) THEN
        ALTER TABLE subscriptions
            ADD CONSTRAINT subscriptions_workspace_fkey
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'subscriptions_subject_check'
    ) THEN
        ALTER TABLE subscriptions
            ADD CONSTRAINT subscriptions_subject_check
            CHECK ((user_id IS NOT NULL) <> (workspace_id IS NOT NULL));
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'subscriptions_seats_check'
    ) THEN
        ALTER TABLE subscriptions
            ADD CONSTRAINT subscriptions_seats_check
            CHECK (included_seats >= 0 AND extra_seats >= 0);
    END IF;
END;
$$;

ALTER TABLE subscriptions
    DROP CONSTRAINT IF EXISTS subscriptions_status_check;

ALTER TABLE subscriptions
    ADD CONSTRAINT subscriptions_status_check
    CHECK (status IN ('trialing', 'active', 'past_due', 'paused', 'canceled', 'incomplete', 'expired', 'suspended'));

CREATE INDEX IF NOT EXISTS idx_subscriptions_workspace
    ON subscriptions (workspace_id) WHERE workspace_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS workspace_seat_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    invitation_id UUID REFERENCES workspace_invitations(id) ON DELETE SET NULL,
    requested_seats INTEGER NOT NULL,
    quoted_unit_amount BIGINT NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'VND',
    status TEXT NOT NULL DEFAULT 'pending_owner',
    requested_by_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    approved_by_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workspace_seat_requests_status_check CHECK (
        status IN ('pending_owner', 'payment_pending', 'approved', 'rejected', 'expired')
    ),
    CONSTRAINT workspace_seat_requests_seats_check CHECK (requested_seats > 0),
    CONSTRAINT workspace_seat_requests_amount_check CHECK (quoted_unit_amount >= 0),
    CONSTRAINT workspace_seat_requests_currency_check CHECK (currency ~ '^[A-Z]{3}$')
);

CREATE INDEX IF NOT EXISTS idx_workspace_seat_requests_workspace
    ON workspace_seat_requests (workspace_id, status);

DROP TRIGGER IF EXISTS trg_workspace_seat_requests_updated_at ON workspace_seat_requests;
CREATE TRIGGER trg_workspace_seat_requests_updated_at
BEFORE UPDATE ON workspace_seat_requests
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
