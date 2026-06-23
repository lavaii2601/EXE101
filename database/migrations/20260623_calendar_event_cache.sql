BEGIN;

ALTER TABLE calendar_events
    ADD COLUMN IF NOT EXISTS etag TEXT,
    ADD COLUMN IF NOT EXISTS google_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_calendar_events_user_etag
    ON calendar_events (user_id, provider, external_event_id, etag);

CREATE INDEX IF NOT EXISTS idx_calendar_events_google_updated
    ON calendar_events (user_id, google_updated_at DESC);

COMMIT;
