import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg

# Soft cap so a very long-running session can't grow this table without bound.
# Oldest rows beyond the cap are pruned right after an insert.
MAX_ENTRIES_PER_SESSION = 30


class SessionMemory:
    """Short factual notes Bob auto-extracts during a chat session (e.g. the
    user's name, a deadline, a preference, a decision) and re-injects into
    later turns of the *same* session. Scoped to chat_session_id on purpose --
    this is not the shared knowledge_documents table (cross-user product
    knowledge) or the raw history log (last N messages); it's a small,
    session-private working memory that survives even after the raw message
    history used for prompt context gets trimmed.
    """

    _initialized_dbs = set()

    @staticmethod
    def init_db(db_path=None):
        if pg.enabled():
            return
        db_path = db_path or Config.DATABASE_PATH
        if db_path in SessionMemory._initialized_dbs:
            return
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'auto',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_memory_session "
            "ON session_memory(chat_session_id, updated_at DESC)"
        )
        conn.commit()
        conn.close()
        SessionMemory._initialized_dbs.add(db_path)

    @staticmethod
    def remember(user_id, chat_session_id, content, source='auto', db_path=None):
        """Store one short fact for this session. Skips empty content and
        exact duplicates of a fact already remembered in this session."""
        content = (content or '').strip()
        if not content or not chat_session_id:
            return None
        content = content[:500]

        if pg.enabled():
            pg.ensure_user(user_id)
            with pg.connection() as conn:
                existing = conn.execute(
                    """
                    SELECT id FROM session_memory
                    WHERE chat_session_id = %s AND content = %s
                    """,
                    (chat_session_id, content),
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE session_memory SET updated_at = NOW() WHERE id = %s",
                        (existing['id'],),
                    )
                    return existing['id']
                row = conn.execute(
                    """
                    INSERT INTO session_memory (user_id, chat_session_id, content, source)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, chat_session_id, content, source),
                ).fetchone()
                conn.execute(
                    """
                    DELETE FROM session_memory
                    WHERE chat_session_id = %s
                      AND id NOT IN (
                          SELECT id FROM session_memory
                          WHERE chat_session_id = %s
                          ORDER BY updated_at DESC
                          LIMIT %s
                      )
                    """,
                    (chat_session_id, chat_session_id, MAX_ENTRIES_PER_SESSION),
                )
                return row['id']

        db_path = db_path or Config.DATABASE_PATH
        SessionMemory.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM session_memory WHERE chat_session_id = ? AND content = ?",
            (chat_session_id, content),
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                "UPDATE session_memory SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (existing[0],),
            )
            conn.commit()
            conn.close()
            return existing[0]

        cursor.execute(
            "INSERT INTO session_memory (chat_session_id, content, source) VALUES (?, ?, ?)",
            (chat_session_id, content, source),
        )
        new_id = cursor.lastrowid
        cursor.execute(
            """
            DELETE FROM session_memory
            WHERE chat_session_id = ?
              AND id NOT IN (
                  SELECT id FROM session_memory
                  WHERE chat_session_id = ?
                  ORDER BY updated_at DESC
                  LIMIT ?
              )
            """,
            (chat_session_id, chat_session_id, MAX_ENTRIES_PER_SESSION),
        )
        conn.commit()
        conn.close()
        return new_id

    @staticmethod
    def list_for_session(user_id, chat_session_id, limit=15, db_path=None):
        """Most recent facts for this session, oldest-first (reads like a
        chronological memory list when dropped into a prompt)."""
        if not chat_session_id:
            return []
        limit = max(1, min(int(limit or 15), MAX_ENTRIES_PER_SESSION))

        if pg.enabled():
            with pg.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT content FROM session_memory
                    WHERE chat_session_id = %s
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (chat_session_id, limit),
                ).fetchall()
                return [row['content'] for row in reversed(rows)]

        db_path = db_path or Config.DATABASE_PATH
        SessionMemory.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT content FROM session_memory WHERE chat_session_id = ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (chat_session_id, limit),
        )
        rows = [row[0] for row in cursor.fetchall()]
        conn.close()
        return list(reversed(rows))

    @staticmethod
    def delete_for_session(chat_session_id, db_path=None):
        if not chat_session_id:
            return 0

        if pg.enabled():
            with pg.connection() as conn:
                cur = conn.execute(
                    "DELETE FROM session_memory WHERE chat_session_id = %s",
                    (chat_session_id,),
                )
                return cur.rowcount

        db_path = db_path or Config.DATABASE_PATH
        SessionMemory.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM session_memory WHERE chat_session_id = ?", (chat_session_id,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
