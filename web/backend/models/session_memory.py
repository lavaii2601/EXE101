import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg

# Soft cap so a very long-running session can't grow this table without bound.
# Oldest rows beyond the cap are pruned right after an insert.
MAX_ENTRIES_PER_SESSION = 30
EMAIL_RESULT_MAP_PREFIX = "__email_result_map_v1__:"
EMAIL_RESULT_MAP_SOURCE = "user"
MAX_EMAIL_RESULTS_PER_SESSION = 10


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
        user_id = user_id or 'default'

        if pg.enabled():
            pg.ensure_user(user_id)
            with pg.connection() as conn:
                existing = conn.execute(
                    """
                    SELECT memory.id
                    FROM session_memory memory
                    JOIN chat_sessions session
                      ON session.id = memory.chat_session_id
                     AND session.user_id = memory.user_id
                    WHERE memory.user_id = %s
                      AND memory.chat_session_id = %s
                      AND memory.content = %s
                    """,
                    (user_id, chat_session_id, content),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE session_memory
                        SET updated_at = NOW()
                        WHERE id = %s AND user_id = %s
                        """,
                        (existing['id'], user_id),
                    )
                    return existing['id']
                row = conn.execute(
                    """
                    INSERT INTO session_memory (user_id, chat_session_id, content, source)
                    SELECT %s, session.id, %s, %s
                    FROM chat_sessions session
                    WHERE session.id = %s
                      AND session.user_id = %s
                      AND session.archived_at IS NULL
                      AND session.expires_at > NOW()
                    RETURNING session_memory.id
                    """,
                    (user_id, content, source, chat_session_id, user_id),
                ).fetchone()
                # Never attach a user's memory to a session owned by another
                # tenant (or to an expired/archived session).
                if not row:
                    return None
                conn.execute(
                    """
                    DELETE FROM session_memory
                    WHERE user_id = %s
                      AND chat_session_id = %s
                      AND id NOT IN (
                          SELECT id FROM session_memory
                          WHERE user_id = %s
                            AND chat_session_id = %s
                          ORDER BY updated_at DESC
                          LIMIT %s
                      )
                    """,
                    (
                        user_id,
                        chat_session_id,
                        user_id,
                        chat_session_id,
                        MAX_ENTRIES_PER_SESSION,
                    ),
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
        user_id = user_id or 'default'
        limit = max(1, min(int(limit or 15), MAX_ENTRIES_PER_SESSION))

        if pg.enabled():
            with pg.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT memory.content
                    FROM session_memory memory
                    JOIN chat_sessions session
                      ON session.id = memory.chat_session_id
                     AND session.user_id = memory.user_id
                    WHERE memory.user_id = %s
                      AND memory.chat_session_id = %s
                      AND session.user_id = %s
                      AND NOT (
                          memory.source = %s
                          AND LEFT(memory.content, %s) = %s
                      )
                    ORDER BY memory.updated_at DESC
                    LIMIT %s
                    """,
                    (
                        user_id,
                        chat_session_id,
                        user_id,
                        EMAIL_RESULT_MAP_SOURCE,
                        len(EMAIL_RESULT_MAP_PREFIX),
                        EMAIL_RESULT_MAP_PREFIX,
                        limit,
                    ),
                ).fetchall()
                return [row['content'] for row in reversed(rows)]

        db_path = db_path or Config.DATABASE_PATH
        SessionMemory.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT content FROM session_memory "
            "WHERE chat_session_id = ? "
            "AND NOT (source = ? AND substr(content, 1, ?) = ?) "
            "ORDER BY updated_at DESC LIMIT ?",
            (
                chat_session_id,
                EMAIL_RESULT_MAP_SOURCE,
                len(EMAIL_RESULT_MAP_PREFIX),
                EMAIL_RESULT_MAP_PREFIX,
                limit,
            ),
        )
        rows = [row[0] for row in cursor.fetchall()]
        conn.close()
        return list(reversed(rows))

    @staticmethod
    def remember_email_results(user_id, chat_session_id, emails, db_path=None):
        """Replace the latest ordered Gmail result map for one active chat.

        The map is stored alongside session memory so the existing
        session-delete/clear paths remove it automatically. Its private
        prefix keeps the structured payload out of Bob's natural-language
        memory prompt.
        """
        if not chat_session_id:
            return None
        user_id = user_id or 'default'
        sanitized = []
        for email in list(emails or [])[:MAX_EMAIL_RESULTS_PER_SESSION]:
            if not isinstance(email, dict):
                continue
            email_id = str(email.get('id') or '').strip()
            if not email_id:
                continue
            sanitized.append({
                'id': email_id[:255],
                'title': str(
                    email.get('subject') or email.get('title') or '(không có tiêu đề)'
                ).strip()[:240],
            })
        if not sanitized:
            return None

        content = EMAIL_RESULT_MAP_PREFIX + json.dumps(
            {'emails': sanitized},
            ensure_ascii=False,
            separators=(',', ':'),
        )

        if pg.enabled():
            with pg.connection() as conn:
                conn.execute(
                    """
                    DELETE FROM session_memory
                    WHERE user_id = %s
                      AND chat_session_id = %s
                      AND source = %s
                      AND LEFT(content, %s) = %s
                    """,
                    (
                        user_id,
                        chat_session_id,
                        EMAIL_RESULT_MAP_SOURCE,
                        len(EMAIL_RESULT_MAP_PREFIX),
                        EMAIL_RESULT_MAP_PREFIX,
                    ),
                )
                row = conn.execute(
                    """
                    INSERT INTO session_memory (
                        user_id, chat_session_id, content, source
                    )
                    SELECT %s, session.id, %s, %s
                    FROM chat_sessions session
                    WHERE session.id = %s
                      AND session.user_id = %s
                      AND session.archived_at IS NULL
                      AND session.expires_at > NOW()
                    RETURNING session_memory.id
                    """,
                    (
                        user_id,
                        content,
                        EMAIL_RESULT_MAP_SOURCE,
                        chat_session_id,
                        user_id,
                    ),
                ).fetchone()
                return row['id'] if row else None

        db_path = db_path or Config.DATABASE_PATH
        SessionMemory.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id
            FROM chat_sessions
            WHERE id = ?
              AND archived_at IS NULL
              AND datetime(expires_at) > CURRENT_TIMESTAMP
            """,
            (chat_session_id,),
        )
        if not cursor.fetchone():
            conn.close()
            return None
        cursor.execute(
            """
            DELETE FROM session_memory
            WHERE chat_session_id = ?
              AND source = ?
              AND substr(content, 1, ?) = ?
            """,
            (
                chat_session_id,
                EMAIL_RESULT_MAP_SOURCE,
                len(EMAIL_RESULT_MAP_PREFIX),
                EMAIL_RESULT_MAP_PREFIX,
            ),
        )
        cursor.execute(
            """
            INSERT INTO session_memory (chat_session_id, content, source)
            VALUES (?, ?, ?)
            """,
            (chat_session_id, content, EMAIL_RESULT_MAP_SOURCE),
        )
        result_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return result_id

    @staticmethod
    def get_email_results(user_id, chat_session_id, db_path=None):
        """Return the latest ordered email results for this owned session."""
        if not chat_session_id:
            return []
        user_id = user_id or 'default'

        if pg.enabled():
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    SELECT memory.content
                    FROM session_memory memory
                    JOIN chat_sessions session
                      ON session.id = memory.chat_session_id
                     AND session.user_id = memory.user_id
                    WHERE memory.user_id = %s
                      AND memory.chat_session_id = %s
                      AND session.user_id = %s
                      AND session.archived_at IS NULL
                      AND session.expires_at > NOW()
                      AND memory.source = %s
                      AND LEFT(memory.content, %s) = %s
                    ORDER BY memory.updated_at DESC
                    LIMIT 1
                    """,
                    (
                        user_id,
                        chat_session_id,
                        user_id,
                        EMAIL_RESULT_MAP_SOURCE,
                        len(EMAIL_RESULT_MAP_PREFIX),
                        EMAIL_RESULT_MAP_PREFIX,
                    ),
                ).fetchone()
                content = row['content'] if row else None
        else:
            db_path = db_path or Config.DATABASE_PATH
            SessionMemory.init_db(db_path=db_path)
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT memory.content
                FROM session_memory memory
                JOIN chat_sessions session
                  ON session.id = memory.chat_session_id
                WHERE memory.chat_session_id = ?
                  AND session.archived_at IS NULL
                  AND datetime(session.expires_at) > CURRENT_TIMESTAMP
                  AND memory.source = ?
                  AND substr(memory.content, 1, ?) = ?
                ORDER BY memory.updated_at DESC
                LIMIT 1
                """,
                (
                    chat_session_id,
                    EMAIL_RESULT_MAP_SOURCE,
                    len(EMAIL_RESULT_MAP_PREFIX),
                    EMAIL_RESULT_MAP_PREFIX,
                ),
            )
            row = cursor.fetchone()
            conn.close()
            content = row[0] if row else None

        if not content or not str(content).startswith(EMAIL_RESULT_MAP_PREFIX):
            return []
        try:
            payload = json.loads(str(content)[len(EMAIL_RESULT_MAP_PREFIX):])
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        results = payload.get('emails') if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []
        return [
            {
                'id': str(item.get('id') or '').strip(),
                'title': str(item.get('title') or '(không có tiêu đề)').strip(),
            }
            for item in results[:MAX_EMAIL_RESULTS_PER_SESSION]
            if isinstance(item, dict) and str(item.get('id') or '').strip()
        ]

    @staticmethod
    def delete_for_session(user_id, chat_session_id, db_path=None):
        if not chat_session_id:
            return 0
        user_id = user_id or 'default'

        if pg.enabled():
            with pg.connection() as conn:
                cur = conn.execute(
                    """
                    DELETE FROM session_memory
                    WHERE user_id = %s AND chat_session_id = %s
                    """,
                    (user_id, chat_session_id),
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

    @staticmethod
    def delete_all_for_user(user_id, db_path=None):
        """Delete every remembered fact belonging to one user.

        SQLite uses one database file per user, while PostgreSQL stores all
        tenants together and therefore always filters explicitly by user_id.
        """
        user_id = user_id or 'default'

        if pg.enabled():
            with pg.connection() as conn:
                cur = conn.execute(
                    "DELETE FROM session_memory WHERE user_id = %s",
                    (user_id,),
                )
                return cur.rowcount

        db_path = db_path or Config.DATABASE_PATH
        SessionMemory.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM session_memory")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
