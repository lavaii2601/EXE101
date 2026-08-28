-- EXE101 / FlowMate PostgreSQL schema
-- Purpose: production-ready relational schema for the current app features.
-- Run with: psql "$DATABASE_URL" -f database/postgres_schema.sql

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    CREATE TYPE user_mode AS ENUM (
        'student', 'worker', 'freelancer', 'mentor', 'teacher', 'business', 'creator'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TYPE user_mode ADD VALUE IF NOT EXISTS 'business';
ALTER TYPE user_mode ADD VALUE IF NOT EXISTS 'creator';

DO $$
BEGIN
    CREATE TYPE schedule_status AS ENUM ('pending', 'completed', 'cancelled', 'dismissed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE meeting_suggestion_status AS ENUM ('pending', 'created', 'dismissed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE activity_type AS ENUM (
        'chat',
        'email_summary',
        'email_daily_summary',
        'email_reply',
        'email_sent',
        'schedule_created',
        'schedule_updated',
        'schedule_deleted',
        'calendar_event_created',
        'calendar_event_updated',
        'calendar_event_deleted',
        'settings_updated',
        'system'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,

    name TEXT,
    email TEXT,
    avatar_url TEXT,
    password_hash TEXT,

    gmail_email TEXT,
    gmail_name TEXT,
    gmail_picture TEXT,
    gmail_connected BOOLEAN NOT NULL DEFAULT FALSE,
    gmail_connected_at TIMESTAMPTZ,
    gmail_disconnected_at TIMESTAMPTZ,

    user_mode user_mode,
    user_mode_selected_at TIMESTAMPTZ,

    locale TEXT NOT NULL DEFAULT 'vi',
    timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    preferences JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Immutable external identities prevent two distinct Google accounts whose
-- email punctuation normalizes to the same legacy file-safe id from sharing
-- a FlowMate workspace.
CREATE TABLE IF NOT EXISTS user_identities (
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    account_email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider, subject)
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'google',
    account_email TEXT,
    token_json JSONB NOT NULL,
    scopes TEXT[] NOT NULL DEFAULT '{}',
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT oauth_tokens_user_provider_unique UNIQUE (user_id, provider)
);

-- Transient state for an in-progress Google OAuth handshake (PKCE code
-- verifier, and whether the mobile app started it). Must be in the shared
-- DB, not a local file: the request that starts the flow (/auth_url) and
-- the request Google redirects back to (/oauth2callback) can land on
-- different backend instances behind the load balancer.
CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    code_verifier TEXT,
    mobile BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS schedules (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

    title TEXT NOT NULL,
    description TEXT,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    duration_minutes INTEGER,
    timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    location TEXT,
    attendees TEXT,
    attendee_emails TEXT[] NOT NULL DEFAULT '{}',

    source TEXT NOT NULL DEFAULT 'flowmate',
    source_email_id TEXT,
    email_body TEXT,

    calendar_provider TEXT DEFAULT 'google',
    calendar_event_id TEXT,
    calendar_event_link TEXT,
    calendar_synced_at TIMESTAMPTZ,
    calendar_sync_error TEXT,

    status schedule_status NOT NULL DEFAULT 'pending',
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT schedules_time_check CHECK (end_time IS NULL OR end_time >= start_time)
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'google',
    calendar_id TEXT NOT NULL DEFAULT 'primary',
    external_event_id TEXT NOT NULL,

    schedule_id BIGINT REFERENCES schedules(id) ON DELETE SET NULL,
    title TEXT,
    description TEXT,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    timezone TEXT,
    location TEXT,
    attendees JSONB NOT NULL DEFAULT '[]'::JSONB,
    status TEXT,
    html_link TEXT,
    etag TEXT,
    google_updated_at TIMESTAMPTZ,
    raw_event JSONB NOT NULL DEFAULT '{}'::JSONB,

    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT calendar_events_unique UNIQUE (user_id, provider, calendar_id, external_event_id)
);

CREATE TABLE IF NOT EXISTS meeting_suggestions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    email_id TEXT NOT NULL,

    sender TEXT,
    subject TEXT,
    email_date TIMESTAMPTZ,
    snippet TEXT,

    title TEXT NOT NULL,
    description TEXT,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    location TEXT,
    attendees TEXT,
    attendee_emails TEXT[] NOT NULL DEFAULT '{}',

    confidence NUMERIC(4,3),
    status meeting_suggestion_status NOT NULL DEFAULT 'pending',
    schedule_id BIGINT REFERENCES schedules(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT meeting_suggestions_user_email_unique UNIQUE (user_id, email_id)
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title TEXT,
    mode user_mode,
    retention_days SMALLINT NOT NULL DEFAULT 90,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '90 days'),
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chat_sessions_retention_days_check CHECK (retention_days BETWEEN 30 AND 365)
);

CREATE TABLE IF NOT EXISTS history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    user_message TEXT,
    assistant_response TEXT,
    action_type activity_type NOT NULL DEFAULT 'chat',
    related_type TEXT,
    related_id TEXT,
    chat_session_id UUID REFERENCES chat_sessions(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Short factual notes Bob auto-extracts during a chat session (name, deadline,
-- preference, decision, ...) and re-injects into later turns of that *same*
-- session. Scoped to chat_session_id on purpose -- distinct from the shared
-- knowledge_documents table (cross-user product knowledge) and from the raw
-- history log (last N messages); this is session-private working memory that
-- outlives the raw message window used for prompt context.
CREATE TABLE IF NOT EXISTS session_memory (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    chat_session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'auto',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT session_memory_source_check CHECK (source IN ('auto', 'user'))
);

-- Generic cache for current code paths that still cache composite payloads.
CREATE TABLE IF NOT EXISTS cache (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    namespace TEXT NOT NULL DEFAULT 'default',
    value JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT cache_user_key_unique UNIQUE (user_id, key)
);

CREATE TABLE IF NOT EXISTS sync_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT sync_jobs_status_check CHECK (status IN ('pending', 'running', 'success', 'failed', 'skipped'))
);

-- Lightweight cross-client invalidation cursor. Every successful workspace
-- mutation advances one global revision for the user and stamps each affected
-- domain with that same revision.
CREATE TABLE IF NOT EXISTS workspace_sync_state (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    revision BIGINT NOT NULL DEFAULT 0,
    domains JSONB NOT NULL DEFAULT '{}'::JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workspace_sync_state_revision_check CHECK (revision >= 0)
);

-- Provider-neutral billing ledger. Payment providers (Stripe, MoMo, VNPay,
-- manual bank transfer, etc.) can upsert their own external identifiers while
-- the admin dashboard reads one consistent source of truth. Monetary values
-- are stored in the currency's smallest unit (VND = đồng, USD = cents).
CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'manual',
    provider_subscription_id TEXT,
    plan_code TEXT NOT NULL,
    plan_name TEXT,
    status TEXT NOT NULL DEFAULT 'incomplete',
    billing_interval TEXT NOT NULL DEFAULT 'monthly',
    currency TEXT NOT NULL DEFAULT 'VND',
    unit_amount BIGINT NOT NULL DEFAULT 0,
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    canceled_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT subscriptions_status_check CHECK (
        status IN ('trialing', 'active', 'past_due', 'paused', 'canceled', 'incomplete', 'expired')
    ),
    CONSTRAINT subscriptions_interval_check CHECK (
        billing_interval IN ('monthly', 'yearly')
    ),
    CONSTRAINT subscriptions_currency_check CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT subscriptions_amount_check CHECK (unit_amount >= 0)
);

CREATE TABLE IF NOT EXISTS payment_transactions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    subscription_id BIGINT REFERENCES subscriptions(id) ON DELETE SET NULL,
    provider TEXT NOT NULL DEFAULT 'manual',
    provider_payment_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    currency TEXT NOT NULL DEFAULT 'VND',
    gross_amount BIGINT NOT NULL DEFAULT 0,
    fee_amount BIGINT NOT NULL DEFAULT 0,
    refund_amount BIGINT NOT NULL DEFAULT 0,
    description TEXT,
    paid_at TIMESTAMPTZ,
    refunded_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT payment_transactions_status_check CHECK (
        status IN ('pending', 'paid', 'failed', 'partially_refunded', 'refunded')
    ),
    CONSTRAINT payment_transactions_currency_check CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT payment_transactions_amounts_check CHECK (
        gross_amount >= 0 AND fee_amount >= 0 AND refund_amount >= 0
    )
);

-- Per-user daily counter for AI-costing actions (chat messages, email AI
-- summaries, draft replies, plan-day suggestions), gating the free tier of
-- the Freemium/Premium split. Incremented via a single atomic
-- INSERT ... ON CONFLICT ... DO UPDATE SET count = count + 1 RETURNING count.
CREATE TABLE IF NOT EXISTS ai_usage_daily (
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    usage_date DATE NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, action, usage_date)
);

-- Shared knowledge base for Bob's RAG lookups (not per-user -- product/feature
-- knowledge, FAQ, and any open-source reference material fed in later).
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    user_id TEXT DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Shared cache of message phrasings the AI has classified for a
-- confirmation-gated intent (see models/intent_pattern.py and
-- services/intent_pattern_cache.py). Not per-user on purpose -- "how people
-- phrase a request" is a language-pattern fact that benefits every user.
-- This table was previously missing from the deployed schema, so every
-- lookup/observe call failed silently (caught and logged, never raised) and
-- the AI was re-classifying every cacheable-intent message from scratch.
CREATE TABLE IF NOT EXISTS intent_patterns (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    phrase TEXT NOT NULL,
    intent TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.6,
    status TEXT NOT NULL DEFAULT 'candidate',
    confirm_count INTEGER NOT NULL DEFAULT 1,
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT intent_patterns_status_check CHECK (status IN ('candidate', 'trusted'))
);

-- Idempotent upgrades for databases that already had these tables before
-- chat retention columns were added. CREATE TABLE IF NOT EXISTS does not
-- add missing columns to existing tables.
ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS retention_days SMALLINT NOT NULL DEFAULT 90,
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '90 days'),
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT NULL;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS password_hash TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chat_sessions_retention_days_check'
    ) THEN
        ALTER TABLE chat_sessions
            ADD CONSTRAINT chat_sessions_retention_days_check
            CHECK (retention_days BETWEEN 30 AND 365);
    END IF;
END;
$$;

ALTER TABLE history
    ADD COLUMN IF NOT EXISTS chat_session_id UUID REFERENCES chat_sessions(id) ON DELETE SET NULL;

ALTER TABLE calendar_events
    ADD COLUMN IF NOT EXISTS etag TEXT,
    ADD COLUMN IF NOT EXISTS google_updated_at TIMESTAMPTZ;

UPDATE chat_sessions
SET retention_days = 90
WHERE retention_days IS NULL;

UPDATE chat_sessions
SET expires_at = created_at + (retention_days || ' days')::INTERVAL
WHERE expires_at IS NULL;

-- ============================================================
-- Multi-tenant workspaces (Worker Business Phase 1 foundation).
-- See WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md section 9 for the full
-- design. Distinct from workspace_sync_state above, which is an
-- unrelated per-user cross-device sync cursor that predates this
-- feature and keeps its existing name for backward compatibility.
-- ============================================================

CREATE TABLE IF NOT EXISTS workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    slug TEXT,
    avatar_url TEXT,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active',
    settings JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ,
    CONSTRAINT workspaces_type_check CHECK (type IN ('personal', 'business')),
    CONSTRAINT workspaces_status_check CHECK (
        status IN ('active', 'grace', 'read_only', 'suspended', 'archived')
    )
);

-- Each user has at most one personal workspace. A CHECK constraint can't
-- express "at most one row per owner where type = 'personal'", so this is
-- enforced with a partial unique index instead.
CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_one_personal_per_owner
    ON workspaces (owner_user_id)
    WHERE type = 'personal';

CREATE TABLE IF NOT EXISTS workspace_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    disabled_at TIMESTAMPTZ,
    removed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workspace_memberships_role_check CHECK (role IN ('owner', 'admin', 'worker')),
    CONSTRAINT workspace_memberships_status_check CHECK (status IN ('active', 'disabled', 'removed')),
    CONSTRAINT workspace_memberships_unique UNIQUE (workspace_id, user_id)
);

CREATE TABLE IF NOT EXISTS workspace_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    email_normalized TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    token_hash TEXT NOT NULL,
    invited_by_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Only 'admin'/'worker' are invitable -- a workspace's one 'owner' is set
    -- at creation time, never granted through an invitation.
    CONSTRAINT workspace_invitations_role_check CHECK (role IN ('admin', 'worker')),
    CONSTRAINT workspace_invitations_status_check CHECK (
        status IN ('pending', 'accepted', 'declined', 'revoked', 'expired', 'capacity_blocked')
    )
);

CREATE TABLE IF NOT EXISTS workspace_audit_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    actor_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_gmail_email ON users (gmail_email);
CREATE INDEX IF NOT EXISTS idx_users_mode ON users (user_mode);
CREATE INDEX IF NOT EXISTS idx_user_identities_user ON user_identities (user_id);

CREATE INDEX IF NOT EXISTS idx_oauth_tokens_expires_at ON oauth_tokens (expires_at);

CREATE INDEX IF NOT EXISTS idx_schedules_user_start ON schedules (user_id, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_schedules_user_status ON schedules (user_id, status, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_schedules_calendar_event ON schedules (user_id, calendar_event_id) WHERE calendar_event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_calendar_events_user_start ON calendar_events (user_id, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_calendar_events_external ON calendar_events (user_id, provider, external_event_id);
CREATE INDEX IF NOT EXISTS idx_meeting_suggestions_user_status ON meeting_suggestions (user_id, status, COALESCE(start_time, created_at));
CREATE INDEX IF NOT EXISTS idx_meeting_suggestions_schedule ON meeting_suggestions (schedule_id);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated ON chat_sessions (user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_expires ON chat_sessions (user_id, expires_at);

CREATE INDEX IF NOT EXISTS idx_history_user_created ON history (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_user_action ON history (user_id, action_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_chat_session ON history (chat_session_id);

CREATE INDEX IF NOT EXISTS idx_session_memory_session ON session_memory (chat_session_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_cache_user_expires ON cache (user_id, expires_at);

CREATE INDEX IF NOT EXISTS idx_sync_jobs_user_type_status ON sync_jobs (user_id, job_type, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workspace_sync_state_updated ON workspace_sync_state (updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_provider_external
    ON subscriptions (provider, provider_subscription_id)
    WHERE provider_subscription_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_subscriptions_status_period
    ON subscriptions (status, current_period_end DESC);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_updated
    ON subscriptions (user_id, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_transactions_provider_external
    ON payment_transactions (provider, provider_payment_id)
    WHERE provider_payment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_transactions_paid_currency
    ON payment_transactions (paid_at DESC, currency)
    WHERE paid_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_transactions_refunded_currency
    ON payment_transactions (refunded_at DESC, currency)
    WHERE refunded_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_transactions_user_created
    ON payment_transactions (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_usage_daily_user_date
    ON ai_usage_daily (user_id, usage_date);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_created ON knowledge_documents (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_user_created ON knowledge_documents (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_intent_patterns_created ON intent_patterns (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_intent_patterns_status_created ON intent_patterns (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces (owner_user_id);
CREATE INDEX IF NOT EXISTS idx_workspace_memberships_user_status ON workspace_memberships (user_id, status);
CREATE INDEX IF NOT EXISTS idx_workspace_memberships_workspace_status ON workspace_memberships (workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_workspace_invitations_workspace_status ON workspace_invitations (workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_workspace_invitations_email_status ON workspace_invitations (email_normalized, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_invitations_token_hash ON workspace_invitations (token_hash);
CREATE INDEX IF NOT EXISTS idx_workspace_audit_events_workspace_created ON workspace_audit_events (workspace_id, created_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION set_schedule_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    IF ROW(
        NEW.title,
        NEW.description,
        NEW.start_time,
        NEW.end_time,
        NEW.duration_minutes,
        NEW.timezone,
        NEW.location,
        NEW.attendees,
        NEW.attendee_emails,
        NEW.source,
        NEW.source_email_id,
        NEW.email_body,
        NEW.status,
        NEW.metadata
    ) IS DISTINCT FROM ROW(
        OLD.title,
        OLD.description,
        OLD.start_time,
        OLD.end_time,
        OLD.duration_minutes,
        OLD.timezone,
        OLD.location,
        OLD.attendees,
        OLD.attendee_emails,
        OLD.source,
        OLD.source_email_id,
        OLD.email_body,
        OLD.status,
        OLD.metadata
    ) THEN
        NEW.updated_at = NOW();
    ELSE
        NEW.updated_at = OLD.updated_at;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_oauth_tokens_updated_at ON oauth_tokens;
CREATE TRIGGER trg_oauth_tokens_updated_at
BEFORE UPDATE ON oauth_tokens
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_user_identities_updated_at ON user_identities;
CREATE TRIGGER trg_user_identities_updated_at
BEFORE UPDATE ON user_identities
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_schedules_updated_at ON schedules;
CREATE TRIGGER trg_schedules_updated_at
BEFORE UPDATE ON schedules
FOR EACH ROW EXECUTE FUNCTION set_schedule_updated_at();

DROP TRIGGER IF EXISTS trg_calendar_events_updated_at ON calendar_events;
CREATE TRIGGER trg_calendar_events_updated_at
BEFORE UPDATE ON calendar_events
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_meeting_suggestions_updated_at ON meeting_suggestions;
CREATE TRIGGER trg_meeting_suggestions_updated_at
BEFORE UPDATE ON meeting_suggestions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_chat_sessions_updated_at ON chat_sessions;
CREATE TRIGGER trg_chat_sessions_updated_at
BEFORE UPDATE ON chat_sessions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_cache_updated_at ON cache;
CREATE TRIGGER trg_cache_updated_at
BEFORE UPDATE ON cache
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_sync_jobs_updated_at ON sync_jobs;
CREATE TRIGGER trg_sync_jobs_updated_at
BEFORE UPDATE ON sync_jobs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_workspace_sync_state_updated_at ON workspace_sync_state;
CREATE TRIGGER trg_workspace_sync_state_updated_at
BEFORE UPDATE ON workspace_sync_state
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_subscriptions_updated_at ON subscriptions;
CREATE TRIGGER trg_subscriptions_updated_at
BEFORE UPDATE ON subscriptions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_payment_transactions_updated_at ON payment_transactions;
CREATE TRIGGER trg_payment_transactions_updated_at
BEFORE UPDATE ON payment_transactions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_knowledge_documents_updated_at ON knowledge_documents;
CREATE TRIGGER trg_knowledge_documents_updated_at
BEFORE UPDATE ON knowledge_documents
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_intent_patterns_updated_at ON intent_patterns;
CREATE TRIGGER trg_intent_patterns_updated_at
BEFORE UPDATE ON intent_patterns
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_workspaces_updated_at ON workspaces;
CREATE TRIGGER trg_workspaces_updated_at
BEFORE UPDATE ON workspaces
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_workspace_memberships_updated_at ON workspace_memberships;
CREATE TRIGGER trg_workspace_memberships_updated_at
BEFORE UPDATE ON workspace_memberships
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_workspace_invitations_updated_at ON workspace_invitations;
CREATE TRIGGER trg_workspace_invitations_updated_at
BEFORE UPDATE ON workspace_invitations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
