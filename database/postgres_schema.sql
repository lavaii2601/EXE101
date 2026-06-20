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
    CREATE TYPE email_summary_type AS ENUM ('preview', 'ai_cached', 'ai_generated', 'manual');
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

-- Gmail message metadata and cached body. This replaces ad-hoc JSON cache entries
-- when you want searchable, queryable email state in Postgres.
CREATE TABLE IF NOT EXISTS gmail_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    gmail_message_id TEXT NOT NULL,
    thread_id TEXT,

    sender TEXT,
    sender_email TEXT,
    recipients TEXT,
    cc TEXT,
    bcc TEXT,
    subject TEXT,
    snippet TEXT,
    body_text TEXT,
    body_html TEXT,

    gmail_date TIMESTAMPTZ,
    is_unread BOOLEAN NOT NULL DEFAULT FALSE,
    labels TEXT[] NOT NULL DEFAULT '{}',
    tag TEXT,
    tag_confidence NUMERIC(4,3),

    has_attachments BOOLEAN NOT NULL DEFAULT FALSE,
    raw_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,

    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    body_fetched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT gmail_messages_user_message_unique UNIQUE (user_id, gmail_message_id)
);

CREATE TABLE IF NOT EXISTS gmail_attachments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    message_id BIGINT NOT NULL REFERENCES gmail_messages(id) ON DELETE CASCADE,
    gmail_attachment_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime_type TEXT,
    size_bytes BIGINT,
    content_disposition TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT gmail_attachments_unique UNIQUE (message_id, gmail_attachment_id)
);

CREATE TABLE IF NOT EXISTS email_summaries (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    message_id BIGINT REFERENCES gmail_messages(id) ON DELETE CASCADE,
    gmail_message_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    summary_type email_summary_type NOT NULL DEFAULT 'ai_generated',
    provider TEXT,
    model TEXT,
    source_hash TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT email_summaries_user_message_unique UNIQUE (user_id, gmail_message_id)
);

CREATE TABLE IF NOT EXISTS email_daily_reports (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    report_date DATE NOT NULL,
    total_emails INTEGER NOT NULL DEFAULT 0,
    provider TEXT,
    model TEXT,
    rows JSONB NOT NULL DEFAULT '[]'::JSONB,
    source_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT email_daily_reports_user_date_unique UNIQUE (user_id, report_date)
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
    message_id BIGINT REFERENCES gmail_messages(id) ON DELETE SET NULL,

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
    CONSTRAINT chat_sessions_retention_days_check CHECK (retention_days BETWEEN 30 AND 93)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    task TEXT,
    intent JSONB NOT NULL DEFAULT '{}'::JSONB,
    workspace_sources TEXT[] NOT NULL DEFAULT '{}',
    schedule_id BIGINT REFERENCES schedules(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '90 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chat_messages_role_check CHECK (role IN ('system', 'user', 'assistant', 'tool'))
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

CREATE TABLE IF NOT EXISTS ai_requests (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    provider TEXT,
    model TEXT,
    task TEXT,
    status TEXT NOT NULL DEFAULT 'success',
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    latency_ms INTEGER,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

-- Idempotent upgrades for databases that already had these tables before
-- chat retention columns were added. CREATE TABLE IF NOT EXISTS does not
-- add missing columns to existing tables.
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

CREATE INDEX IF NOT EXISTS idx_users_gmail_email ON users (gmail_email);
CREATE INDEX IF NOT EXISTS idx_users_mode ON users (user_mode);

CREATE INDEX IF NOT EXISTS idx_oauth_tokens_user_provider ON oauth_tokens (user_id, provider);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_expires_at ON oauth_tokens (expires_at);

CREATE INDEX IF NOT EXISTS idx_gmail_messages_user_date ON gmail_messages (user_id, gmail_date DESC);
CREATE INDEX IF NOT EXISTS idx_gmail_messages_user_unread ON gmail_messages (user_id, is_unread, gmail_date DESC);
CREATE INDEX IF NOT EXISTS idx_gmail_messages_user_tag ON gmail_messages (user_id, tag, gmail_date DESC);
CREATE INDEX IF NOT EXISTS idx_gmail_messages_subject_search ON gmail_messages USING GIN (to_tsvector('simple', COALESCE(subject, '') || ' ' || COALESCE(snippet, '')));

CREATE INDEX IF NOT EXISTS idx_gmail_attachments_message ON gmail_attachments (message_id);
CREATE INDEX IF NOT EXISTS idx_email_summaries_user_message ON email_summaries (user_id, gmail_message_id);
CREATE INDEX IF NOT EXISTS idx_email_daily_reports_user_date ON email_daily_reports (user_id, report_date DESC);

CREATE INDEX IF NOT EXISTS idx_schedules_user_start ON schedules (user_id, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_schedules_user_status ON schedules (user_id, status, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_schedules_calendar_event ON schedules (user_id, calendar_event_id) WHERE calendar_event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_calendar_events_user_start ON calendar_events (user_id, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_calendar_events_external ON calendar_events (user_id, provider, external_event_id);

CREATE INDEX IF NOT EXISTS idx_meeting_suggestions_user_status ON meeting_suggestions (user_id, status, COALESCE(start_time, created_at));
CREATE INDEX IF NOT EXISTS idx_meeting_suggestions_schedule ON meeting_suggestions (schedule_id);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated ON chat_sessions (user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_expires ON chat_sessions (user_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created ON chat_messages (session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_created ON chat_messages (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_expires ON chat_messages (expires_at);

CREATE INDEX IF NOT EXISTS idx_history_user_created ON history (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_user_action ON history (user_id, action_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_chat_session ON history (chat_session_id);

CREATE INDEX IF NOT EXISTS idx_cache_user_key ON cache (user_id, key);
CREATE INDEX IF NOT EXISTS idx_cache_namespace ON cache (namespace, expires_at);
CREATE INDEX IF NOT EXISTS idx_cache_expires_at ON cache (expires_at);
CREATE INDEX IF NOT EXISTS idx_cache_value_gin ON cache USING GIN (value);

CREATE INDEX IF NOT EXISTS idx_ai_requests_user_created ON ai_requests (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_requests_provider_task ON ai_requests (provider, task, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sync_jobs_user_type_status ON sync_jobs (user_id, job_type, status, created_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
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

DROP TRIGGER IF EXISTS trg_gmail_messages_updated_at ON gmail_messages;
CREATE TRIGGER trg_gmail_messages_updated_at
BEFORE UPDATE ON gmail_messages
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_email_summaries_updated_at ON email_summaries;
CREATE TRIGGER trg_email_summaries_updated_at
BEFORE UPDATE ON email_summaries
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_email_daily_reports_updated_at ON email_daily_reports;
CREATE TRIGGER trg_email_daily_reports_updated_at
BEFORE UPDATE ON email_daily_reports
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_schedules_updated_at ON schedules;
CREATE TRIGGER trg_schedules_updated_at
BEFORE UPDATE ON schedules
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

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

DROP TRIGGER IF EXISTS trg_cache_updated_at ON cache;
CREATE TRIGGER trg_cache_updated_at
BEFORE UPDATE ON cache
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_sync_jobs_updated_at ON sync_jobs;
CREATE TRIGGER trg_sync_jobs_updated_at
BEFORE UPDATE ON sync_jobs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
