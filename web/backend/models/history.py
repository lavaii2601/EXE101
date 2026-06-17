import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg


class History:
    _initialized_dbs = set()

    @staticmethod
    def init_db(db_path=None):
        if pg.enabled():
            return
        db_path = db_path or Config.DATABASE_PATH
        if db_path in History._initialized_dbs:
            return
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_message TEXT,
                assistant_response TEXT,
                action_type TEXT,
                related_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_action_created ON history(action_type, created_at)")
        conn.commit()
        conn.close()
        History._initialized_dbs.add(db_path)

    @staticmethod
    def create(user_message, assistant_response, action_type="chat", related_id=None, db_path=None, chat_session_id=None):
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            pg.ensure_user(user_id)
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    INSERT INTO history (
                        user_id, user_message, assistant_response,
                        action_type, related_id, chat_session_id, created_at
                    )
                    VALUES (%s, %s, %s, %s::activity_type, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, user_message, assistant_response, action_type, related_id, chat_session_id, datetime.now()),
                ).fetchone()
                return row['id']

        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE history ADD COLUMN chat_session_id TEXT")
        except sqlite3.OperationalError:
            pass
        cursor.execute("""
            INSERT INTO history (user_message, assistant_response, action_type, related_id, chat_session_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_message, assistant_response, action_type, related_id, chat_session_id, datetime.now().isoformat()))
        conn.commit()
        rowid = cursor.lastrowid
        conn.close()
        return rowid

    @staticmethod
    def get_recent(limit=10, db_path=None, chat_session_id=None):
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                if chat_session_id:
                    rows = conn.execute(
                        """
                        SELECT * FROM history
                        WHERE user_id = %s
                          AND chat_session_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (user_id, chat_session_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT * FROM history
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (user_id, limit),
                    ).fetchall()
                return pg.normalize_rows(rows)

        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE history ADD COLUMN chat_session_id TEXT")
        except sqlite3.OperationalError:
            pass
        if chat_session_id:
            cursor.execute(
                "SELECT * FROM history WHERE chat_session_id = ? ORDER BY created_at DESC LIMIT ?",
                (chat_session_id, limit),
            )
        else:
            cursor.execute("SELECT * FROM history ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def clear_all(action_type=None, db_path=None, chat_session_id=None):
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                if chat_session_id:
                    cur = conn.execute(
                        "DELETE FROM history WHERE user_id = %s AND action_type = %s AND chat_session_id = %s",
                        (user_id, action_type or 'chat', chat_session_id),
                    )
                elif action_type:
                    cur = conn.execute(
                        "DELETE FROM history WHERE user_id = %s AND action_type = %s",
                        (user_id, action_type),
                    )
                else:
                    cur = conn.execute(
                        "DELETE FROM history WHERE user_id = %s",
                        (user_id,),
                    )
                return cur.rowcount

        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE history ADD COLUMN chat_session_id TEXT")
        except sqlite3.OperationalError:
            pass
        if chat_session_id:
            cursor.execute(
                "DELETE FROM history WHERE action_type = ? AND chat_session_id = ?",
                (action_type or 'chat', chat_session_id),
            )
        elif action_type:
            cursor.execute("DELETE FROM history WHERE action_type = ?", (action_type,))
        else:
            cursor.execute("DELETE FROM history")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
