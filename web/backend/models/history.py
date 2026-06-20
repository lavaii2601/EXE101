import os
import sqlite3
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config


class History:
    _initialized_dbs = set()

    @staticmethod
    def init_db(db_path=None):
        db_path = db_path or Config.DATABASE_PATH
        if db_path in History._initialized_dbs:
            return
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                user_message TEXT,
                assistant_response TEXT,
                action_type TEXT,
                related_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("PRAGMA table_info(history)")
        columns = {row[1] for row in cursor.fetchall()}
        if "title" not in columns:
            cursor.execute("ALTER TABLE history ADD COLUMN title TEXT")
        conn.commit()
        conn.close()
        History._initialized_dbs.add(db_path)

    @staticmethod
    def create(user_message, assistant_response, action_type="chat", related_id=None, title=None, db_path=None):
        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO history (title, user_message, assistant_response, action_type, related_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, user_message, assistant_response, action_type, related_id, datetime.now().isoformat()))
        conn.commit()
        rowid = cursor.lastrowid
        conn.close()
        return rowid

    @staticmethod
    def prune_older_than(days=90, db_path=None):
        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE created_at < ?", (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted

    @staticmethod
    def get_recent(limit=10, db_path=None):
        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        History.prune_older_than(90, db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM history ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def update_title(history_id, title, db_path=None):
        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE history SET title = ? WHERE id = ?", (title, history_id))
        updated = cursor.rowcount
        conn.commit()
        conn.close()
        return updated > 0

    @staticmethod
    def delete(history_id, db_path=None):
        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE id = ?", (history_id,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted > 0

    @staticmethod
    def clear_all(action_type=None, db_path=None):
        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        if action_type:
            cursor.execute("DELETE FROM history WHERE action_type = ?", (action_type,))
        else:
            cursor.execute("DELETE FROM history")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
