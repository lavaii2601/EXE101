from datetime import datetime, timedelta, timezone
import sqlite3
import os
import sys
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg

try:
    LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh") if ZoneInfo else timezone(timedelta(hours=7))
except Exception:
    # Windows Python has no built-in IANA tzdata; ZoneInfo raises at runtime
    # (not ImportError) when the optional `tzdata` package isn't installed.
    LOCAL_TZ = timezone(timedelta(hours=7))


def _coerce_local_datetime(value):
    if not value:
        return value
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return value
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=LOCAL_TZ)


class Schedule:
    _initialized_dbs = set()

    @staticmethod
    def init_db(db_path=None):
        """Initialize schedule table"""
        if pg.enabled():
            return
        db_path = db_path or Config.DATABASE_PATH
        if db_path in Schedule._initialized_dbs:
            return
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                attendees TEXT,
                email_body TEXT,
                calendar_event_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add calendar_event_id column if it doesn't exist (migration)
        try:
            cursor.execute('ALTER TABLE schedules ADD COLUMN calendar_event_id TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        # Add location column if missing
        try:
            cursor.execute('ALTER TABLE schedules ADD COLUMN location TEXT')
        except sqlite3.OperationalError:
            pass

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_schedules_start_time ON schedules(start_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_schedules_status_start ON schedules(status, start_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_schedules_calendar_event ON schedules(calendar_event_id)')
        
        conn.commit()
        conn.close()
        Schedule._initialized_dbs.add(db_path)

    @staticmethod
    def create(title, description, start_time, end_time, attendees, email_body='', location=None, calendar_event_id=None, db_path=None):
        """Create new schedule"""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            pg.ensure_user(user_id)
            attendees_value = ','.join(attendees) if isinstance(attendees, list) else attendees
            start_time_value = _coerce_local_datetime(start_time)
            end_time_value = _coerce_local_datetime(end_time)
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    INSERT INTO schedules (
                        user_id, title, description, start_time, end_time,
                        attendees, email_body, location, calendar_event_id, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                    RETURNING id
                    """,
                    (
                        user_id, title, description, start_time_value, end_time_value,
                        attendees_value, email_body, location, calendar_event_id
                    ),
                ).fetchone()
                return row['id']

        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO schedules (title, description, start_time, end_time, attendees, email_body, location, calendar_event_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ''', (title, description, start_time, end_time, attendees, email_body, location, calendar_event_id))
        conn.commit()
        schedule_id = cursor.lastrowid
        conn.close()
        return schedule_id

    @staticmethod
    def get_by_calendar_event_id(calendar_event_id, db_path=None):
        """Get schedule by Google Calendar event ID"""
        if not calendar_event_id:
            return None
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    SELECT * FROM schedules
                    WHERE user_id = %s AND calendar_event_id = %s
                    LIMIT 1
                    """,
                    (user_id, calendar_event_id),
                ).fetchone()
                return pg.normalize_row(row)

        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM schedules WHERE calendar_event_id = ?', (calendar_event_id,))
        schedule = cursor.fetchone()
        conn.close()
        return dict(schedule) if schedule else None
    
    @staticmethod
    def get_all(limit=50, db_path=None):
        """Get all schedules"""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM schedules
                    WHERE user_id = %s
                    ORDER BY start_time DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                ).fetchall()
                return pg.normalize_rows(rows)

        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM schedules ORDER BY start_time DESC LIMIT ?', (limit,))
        schedules = cursor.fetchall()
        conn.close()
        return [dict(s) for s in schedules]

    @staticmethod
    def get_between(start_time, end_time, limit=100, db_path=None):
        """Get schedules whose start time falls in [start_time, end_time)."""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM schedules
                    WHERE user_id = %s
                      AND start_time >= %s
                      AND start_time < %s
                    ORDER BY start_time ASC
                    LIMIT %s
                    """,
                    (user_id, start_time, end_time, limit),
                ).fetchall()
                return pg.normalize_rows(rows)

        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM schedules
            WHERE start_time >= ? AND start_time < ?
            ORDER BY start_time ASC
            LIMIT ?
            ''',
            (start_time, end_time, limit)
        )
        schedules = cursor.fetchall()
        conn.close()
        return [dict(s) for s in schedules]
    
    @staticmethod
    def get_by_id(schedule_id, db_path=None):
        """Get schedule by ID"""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                row = conn.execute(
                    "SELECT * FROM schedules WHERE id = %s AND user_id = %s",
                    (schedule_id, user_id),
                ).fetchone()
                return pg.normalize_row(row)

        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,))
        schedule = cursor.fetchone()
        conn.close()
        return dict(schedule) if schedule else None
    
    @staticmethod
    def update_status(schedule_id, status, db_path=None, expected_updated_at=None):
        """Update schedule status"""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            where_clause = "id = %s AND user_id = %s"
            values = [status, schedule_id, user_id]
            if expected_updated_at:
                where_clause += " AND updated_at = %s"
                values.append(expected_updated_at)
            with pg.connection() as conn:
                cur = conn.execute(
                    f"""
                    UPDATE schedules
                    SET status = %s::schedule_status, updated_at = NOW()
                    WHERE {where_clause}
                    """,
                    values,
                )
                return cur.rowcount > 0

        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        where_clause = 'id = ?'
        values = [status, datetime.now().isoformat(), schedule_id]
        if expected_updated_at:
            where_clause += ' AND updated_at = ?'
            values.append(expected_updated_at)
        cursor.execute(f'''
            UPDATE schedules
            SET status = ?, updated_at = ?
            WHERE {where_clause}
        ''', values)
        changed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    @staticmethod
    def update(schedule_id, **kwargs):
        """Update schedule information"""
        db_path = kwargs.pop('db_path', None) or Config.DATABASE_PATH
        expected_updated_at = kwargs.pop('expected_updated_at', None)
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            allowed_fields = ['title', 'description', 'start_time', 'end_time', 'attendees', 'email_body', 'status', 'location', 'calendar_event_id']
            updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
            if not updates:
                return False
            if isinstance(updates.get('attendees'), list):
                updates['attendees'] = ','.join(updates['attendees'])
            if 'start_time' in updates:
                updates['start_time'] = _coerce_local_datetime(updates.get('start_time'))
            if 'end_time' in updates:
                updates['end_time'] = _coerce_local_datetime(updates.get('end_time'))
            set_parts = [
                f'{key} = %s::schedule_status' if key == 'status' else f'{key} = %s'
                for key in updates.keys()
            ]
            set_parts.append('updated_at = NOW()')
            set_clause = ', '.join(set_parts)
            where_clause = 'id = %s AND user_id = %s'
            values = list(updates.values()) + [schedule_id, user_id]
            if expected_updated_at:
                where_clause += ' AND updated_at = %s'
                values.append(expected_updated_at)
            with pg.connection() as conn:
                cur = conn.execute(
                    f"UPDATE schedules SET {set_clause} WHERE {where_clause}",
                    values,
                )
                return cur.rowcount > 0

        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        allowed_fields = ['title', 'description', 'start_time', 'end_time', 'attendees', 'email_body', 'status', 'location', 'calendar_event_id']
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            conn.close()
            return False
        
        updates['updated_at'] = datetime.now().isoformat()
        
        set_clause = ', '.join([f'{k} = ?' for k in updates.keys()])
        values = list(updates.values())
        values.append(schedule_id)
        where_clause = 'id = ?'
        if expected_updated_at:
            where_clause += ' AND updated_at = ?'
            values.append(expected_updated_at)

        cursor.execute(f'''
            UPDATE schedules
            SET {set_clause}
            WHERE {where_clause}
        ''', values)
        
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    @staticmethod
    def attach_calendar_event_id(schedule_id, calendar_event_id, db_path=None):
        """Atomically attach a Google event to an as-yet unlinked schedule.

        This is integration metadata, not user-authored schedule content, so
        the statement intentionally leaves ``updated_at`` untouched. The
        PostgreSQL schedules trigger must likewise exclude this metadata-only
        update. Background callers still publish a workspace revision so
        clients can discover the newly attached Google ID.
        """
        if not calendar_event_id:
            return False

        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                cur = conn.execute(
                    """
                    UPDATE schedules
                    SET calendar_event_id = %s
                    WHERE id = %s
                      AND user_id = %s
                      AND (calendar_event_id IS NULL OR calendar_event_id = '')
                    """,
                    (calendar_event_id, schedule_id, user_id),
                )
                return cur.rowcount > 0

        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE schedules
            SET calendar_event_id = ?
            WHERE id = ?
              AND (calendar_event_id IS NULL OR calendar_event_id = '')
            """,
            (calendar_event_id, schedule_id),
        )
        attached = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return attached

    @staticmethod
    def delete(schedule_id, db_path=None):
        """Delete schedule"""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                cur = conn.execute(
                    "DELETE FROM schedules WHERE id = %s AND user_id = %s",
                    (schedule_id, user_id),
                )
                return cur.rowcount > 0

        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM schedules WHERE id = ?', (schedule_id,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted > 0

    @staticmethod
    def delete_expired_google_backed(cutoff_time, db_path=None):
        """Delete local copies of Google-backed schedules that already ended."""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                cur = conn.execute(
                    """
                    DELETE FROM schedules
                    WHERE user_id = %s
                      AND calendar_event_id IS NOT NULL
                      AND COALESCE(end_time, start_time) < %s
                    """,
                    (user_id, cutoff_time),
                )
                return cur.rowcount or 0

        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        cutoff_value = cutoff_time.isoformat() if isinstance(cutoff_time, datetime) else cutoff_time
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            DELETE FROM schedules
            WHERE calendar_event_id IS NOT NULL
              AND COALESCE(end_time, start_time) < ?
            ''',
            (cutoff_value,)
        )
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted
