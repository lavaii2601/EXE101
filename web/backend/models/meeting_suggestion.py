import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg


class MeetingSuggestion:
    _initialized_dbs = set()

    @staticmethod
    def init_db(db_path=None):
        if pg.enabled():
            return
        db_path = db_path or Config.DATABASE_PATH
        if db_path in MeetingSuggestion._initialized_dbs:
            return
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meeting_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT UNIQUE NOT NULL,
                sender TEXT,
                subject TEXT,
                email_date TEXT,
                snippet TEXT,
                title TEXT NOT NULL,
                description TEXT,
                start_time TEXT,
                end_time TEXT,
                location TEXT,
                attendees TEXT,
                status TEXT DEFAULT 'pending',
                schedule_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_meeting_suggestions_status_start ON meeting_suggestions(status, start_time, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_meeting_suggestions_email ON meeting_suggestions(email_id)")
        conn.commit()
        conn.close()
        MeetingSuggestion._initialized_dbs.add(db_path)

    @staticmethod
    def upsert(email_id, suggestion, db_path=None):
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            pg.ensure_user(user_id)
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    INSERT INTO meeting_suggestions (
                        user_id, email_id, sender, subject, email_date, snippet,
                        title, description, start_time, end_time, location, attendees
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, email_id) DO UPDATE
                    SET sender = EXCLUDED.sender,
                        subject = EXCLUDED.subject,
                        email_date = EXCLUDED.email_date,
                        snippet = EXCLUDED.snippet,
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        start_time = EXCLUDED.start_time,
                        end_time = EXCLUDED.end_time,
                        location = EXCLUDED.location,
                        attendees = EXCLUDED.attendees
                    RETURNING id
                    """,
                    (
                        user_id,
                        email_id,
                        suggestion.get("sender", ""),
                        suggestion.get("subject", ""),
                        None,
                        suggestion.get("snippet", ""),
                        suggestion.get("title", ""),
                        suggestion.get("description", ""),
                        suggestion.get("start_time"),
                        suggestion.get("end_time"),
                        suggestion.get("location", ""),
                        suggestion.get("attendees", ""),
                    ),
                ).fetchone()
                return row['id']

        db_path = db_path or Config.DATABASE_PATH
        MeetingSuggestion.init_db(db_path)
        conn = sqlite3.connect(db_path)
        existing = conn.execute(
            "SELECT id, status FROM meeting_suggestions WHERE email_id = ?",
            (email_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE meeting_suggestions
                SET sender = ?, subject = ?, email_date = ?, snippet = ?,
                    title = ?, description = ?, start_time = ?, end_time = ?,
                    location = ?, attendees = ?, updated_at = ?
                WHERE email_id = ?
                """,
                (
                    suggestion.get("sender", ""),
                    suggestion.get("subject", ""),
                    suggestion.get("email_date", ""),
                    suggestion.get("snippet", ""),
                    suggestion.get("title", ""),
                    suggestion.get("description", ""),
                    suggestion.get("start_time"),
                    suggestion.get("end_time"),
                    suggestion.get("location", ""),
                    suggestion.get("attendees", ""),
                    datetime.now().isoformat(),
                    email_id,
                ),
            )
            suggestion_id = existing[0]
        else:
            cursor = conn.execute(
                """
                INSERT INTO meeting_suggestions (
                    email_id, sender, subject, email_date, snippet, title,
                    description, start_time, end_time, location, attendees
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_id,
                    suggestion.get("sender", ""),
                    suggestion.get("subject", ""),
                    suggestion.get("email_date", ""),
                    suggestion.get("snippet", ""),
                    suggestion.get("title", ""),
                    suggestion.get("description", ""),
                    suggestion.get("start_time"),
                    suggestion.get("end_time"),
                    suggestion.get("location", ""),
                    suggestion.get("attendees", ""),
                ),
            )
            suggestion_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return suggestion_id

    @staticmethod
    def get_pending(db_path=None):
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM meeting_suggestions
                    WHERE user_id = %s AND status = 'pending'
                    ORDER BY COALESCE(start_time, created_at), created_at DESC
                    """,
                    (user_id,),
                ).fetchall()
                return pg.normalize_rows(rows)

        db_path = db_path or Config.DATABASE_PATH
        MeetingSuggestion.init_db(db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM meeting_suggestions
            WHERE status = 'pending'
            ORDER BY COALESCE(start_time, created_at), created_at DESC
            """
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def update_status(suggestion_id, status, schedule_id=None, db_path=None):
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                cur = conn.execute(
                    """
                    UPDATE meeting_suggestions
                    SET status = %s::meeting_suggestion_status, schedule_id = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (status, schedule_id, suggestion_id, user_id),
                )
                return cur.rowcount > 0

        db_path = db_path or Config.DATABASE_PATH
        MeetingSuggestion.init_db(db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            """
            UPDATE meeting_suggestions
            SET status = ?, schedule_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, schedule_id, datetime.now().isoformat(), suggestion_id),
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    @staticmethod
    def dismiss_email(email_id, db_path=None):
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                cur = conn.execute(
                    """
                    UPDATE meeting_suggestions
                    SET status = 'dismissed'
                    WHERE user_id = %s AND email_id = %s AND status = 'pending'
                    """,
                    (user_id, email_id),
                )
                return cur.rowcount > 0

        db_path = db_path or Config.DATABASE_PATH
        MeetingSuggestion.init_db(db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            """
            UPDATE meeting_suggestions
            SET status = 'dismissed', updated_at = ?
            WHERE email_id = ? AND status = 'pending'
            """,
            (datetime.now().isoformat(), email_id),
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0
