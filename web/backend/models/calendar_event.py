from datetime import datetime

from models import postgres_db as pg
from models.schedule import LOCAL_TZ


def _coerce_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=LOCAL_TZ)
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=LOCAL_TZ)
    except (TypeError, ValueError):
        return None


class CalendarEvent:
    @staticmethod
    def get_google_event(user_id, external_event_id, calendar_id='primary', db_path=None):
        if not pg.enabled() or not external_event_id:
            return None
        user_id = user_id or pg.user_id_from_db_path(db_path)
        with pg.connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM calendar_events
                WHERE user_id = %s
                  AND provider = 'google'
                  AND calendar_id = %s
                  AND external_event_id = %s
                LIMIT 1
                """,
                (user_id, calendar_id, external_event_id),
            ).fetchone()
            return pg.normalize_row(row)

    @staticmethod
    def google_event_unchanged(user_id, event, calendar_id='primary', db_path=None):
        if not pg.enabled() or not event or not event.get('id') or not event.get('etag'):
            return False
        cached = CalendarEvent.get_google_event(user_id, event.get('id'), calendar_id=calendar_id, db_path=db_path)
        return bool(cached and cached.get('etag') == event.get('etag'))

    @staticmethod
    def upsert_google_event(user_id, event, schedule_id=None, calendar_id='primary', db_path=None):
        if not pg.enabled() or not event or not event.get('id'):
            return False
        user_id = user_id or pg.user_id_from_db_path(db_path)
        pg.ensure_user(user_id)
        existing = CalendarEvent.get_google_event(user_id, event.get('id'), calendar_id=calendar_id, db_path=db_path)
        existing_etag = (existing or {}).get('etag')
        next_etag = event.get('etag') or ''
        schedule_changed = schedule_id is not None and str((existing or {}).get('schedule_id') or '') != str(schedule_id)
        if existing and existing_etag and next_etag and existing_etag == next_etag and not schedule_changed:
            return False

        with pg.connection() as conn:
            conn.execute(
                """
                INSERT INTO calendar_events (
                    user_id, provider, calendar_id, external_event_id, schedule_id,
                    title, description, start_time, end_time, timezone, location,
                    attendees, status, html_link, etag, google_updated_at, raw_event, fetched_at
                )
                VALUES (
                    %s, 'google', %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, NOW()
                )
                ON CONFLICT (user_id, provider, calendar_id, external_event_id) DO UPDATE
                SET schedule_id = COALESCE(EXCLUDED.schedule_id, calendar_events.schedule_id),
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    start_time = EXCLUDED.start_time,
                    end_time = EXCLUDED.end_time,
                    timezone = EXCLUDED.timezone,
                    location = EXCLUDED.location,
                    attendees = EXCLUDED.attendees,
                    status = EXCLUDED.status,
                    html_link = EXCLUDED.html_link,
                    etag = EXCLUDED.etag,
                    google_updated_at = EXCLUDED.google_updated_at,
                    raw_event = EXCLUDED.raw_event,
                    fetched_at = NOW()
                """,
                (
                    user_id,
                    calendar_id,
                    event.get('id'),
                    schedule_id,
                    event.get('title') or 'Untitled',
                    event.get('description') or '',
                    _coerce_datetime(event.get('start')),
                    _coerce_datetime(event.get('end')),
                    'Asia/Ho_Chi_Minh',
                    event.get('location') or '',
                    pg.json_value(event.get('attendees') or []),
                    event.get('status') or 'confirmed',
                    event.get('html_link') or '',
                    next_etag,
                    _coerce_datetime(event.get('updated')),
                    pg.json_value(event),
                ),
            )
        return True

    @staticmethod
    def delete_google_event(user_id, external_event_id, calendar_id='primary', db_path=None):
        if not pg.enabled() or not external_event_id:
            return False
        user_id = user_id or pg.user_id_from_db_path(db_path)
        with pg.connection() as conn:
            cur = conn.execute(
                """
                DELETE FROM calendar_events
                WHERE user_id = %s
                  AND provider = 'google'
                  AND calendar_id = %s
                  AND external_event_id = %s
                """,
                (user_id, calendar_id, external_event_id),
            )
            return cur.rowcount > 0
