-- FlowMate Admin Operations: account lifecycle, runtime AI controls,
-- request/security telemetry and immutable administrator audit history.
-- Idempotent: Railway applies every migration on each deploy.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS account_status TEXT NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS quota_reset_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_account_status_check'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_account_status_check
            CHECK (account_status IN ('active', 'suspended', 'disabled'));
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_users_account_status_active
    ON users (account_status, last_active_at DESC);

CREATE TABLE IF NOT EXISTS admin_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}'::JSONB,
    updated_by_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admin_audit_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admin_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    before_state JSONB,
    after_state JSONB,
    request_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_events_created
    ON admin_audit_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_events_target
    ON admin_audit_events (target_type, target_id, created_at DESC);

CREATE TABLE IF NOT EXISTS operational_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    feature TEXT,
    provider TEXT,
    model TEXT,
    status TEXT NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    request_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_operational_events_created
    ON operational_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_operational_events_type_created
    ON operational_events (event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS api_metrics_daily (
    metric_date DATE PRIMARY KEY,
    request_count BIGINT NOT NULL DEFAULT 0,
    error_count BIGINT NOT NULL DEFAULT 0,
    total_latency_ms BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
