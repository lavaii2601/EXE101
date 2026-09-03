import os
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg
from models import subscription as subscription_model
from models import entitlements


def _resolve_workspace_id(user_id, workspace_id):
    if workspace_id:
        return str(workspace_id)
    from models import workspace as workspace_model

    return str(workspace_model.ensure_personal_workspace(user_id)['id'])


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
        try:
            cursor.execute("ALTER TABLE history ADD COLUMN chat_session_id TEXT")
        except sqlite3.OperationalError:
            pass
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                mode TEXT,
                retention_days INTEGER NOT NULL DEFAULT 90,
                expires_at DATETIME NOT NULL,
                archived_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_action_created ON history(action_type, created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_chat_session ON history(chat_session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions(updated_at)")
        conn.commit()
        conn.close()
        History._initialized_dbs.add(db_path)

    @staticmethod
    def _normalize_session_id(value):
        try:
            return str(uuid.UUID(str(value or '').strip()))
        except (TypeError, ValueError):
            return str(uuid.uuid4())

    @staticmethod
    def _clamp_retention_days(value, is_premium=False):
        cap = entitlements.limits_for(is_premium)['chat_retention_days']
        try:
            days = int(value) if value is not None else cap
        except (TypeError, ValueError):
            days = cap
        return max(7, min(days, cap))

    @staticmethod
    def ensure_chat_session(user_id, session_id=None, title=None, mode='worker', retention_days=None, db_path=None, workspace_id=None):
        session_id = History._normalize_session_id(session_id)
        title = (title or 'Chat').strip()[:120] or 'Chat'
        is_premium = pg.enabled() and subscription_model.is_premium(user_id)
        retention_days = History._clamp_retention_days(retention_days, is_premium=is_premium)
        safe_mode = mode if mode in {
            'student', 'worker', 'freelancer', 'creator', 'business', 'mentor', 'teacher'
        } else 'worker'

        if pg.enabled():
            pg.ensure_user(user_id)
            workspace_id = _resolve_workspace_id(user_id, workspace_id)
            with pg.connection() as conn:
                existing = conn.execute(
                    """
                    SELECT
                        user_id,
                        workspace_id,
                        (archived_at IS NULL AND expires_at > NOW()) AS available
                    FROM chat_sessions
                    WHERE id = %s
                    """,
                    (session_id,),
                ).fetchone()
                if existing and (
                    existing['user_id'] != user_id
                    or str(existing.get('workspace_id')) != str(workspace_id)
                    or not existing['available']
                ):
                    # A client may supply an old or guessed session UUID, or
                    # the same user's own session from a *different* workspace
                    # (e.g. they switched from Personal to a Business
                    # workspace mid-session). Never return a UUID owned by
                    # another tenant or another workspace, and never revive an
                    # archived/expired session.
                    session_id = str(uuid.uuid4())

                row = conn.execute(
                    """
                    INSERT INTO chat_sessions (id, user_id, workspace_id, title, mode, retention_days, expires_at)
                    VALUES (%s, %s, %s, %s, %s::user_mode, %s, NOW() + (%s || ' days')::INTERVAL)
                    ON CONFLICT (id) DO UPDATE
                    SET updated_at = NOW(),
                        title = CASE
                            WHEN chat_sessions.title IS NULL OR chat_sessions.title = '' OR chat_sessions.title = 'Chat'
                            THEN EXCLUDED.title
                            ELSE chat_sessions.title
                        END,
                        mode = COALESCE(chat_sessions.mode, EXCLUDED.mode),
                        retention_days = COALESCE(chat_sessions.retention_days, EXCLUDED.retention_days),
                        expires_at = GREATEST(chat_sessions.expires_at, NOW() + (chat_sessions.retention_days || ' days')::INTERVAL)
                    WHERE chat_sessions.user_id = EXCLUDED.user_id
                      AND chat_sessions.workspace_id = EXCLUDED.workspace_id
                    RETURNING id::TEXT
                    """,
                    (session_id, user_id, workspace_id, title, safe_mode, retention_days, retention_days),
                ).fetchone()
                if not row:
                    # Covers the very small race where another tenant inserts
                    # the requested UUID after the ownership check.
                    session_id = str(uuid.uuid4())
                    row = conn.execute(
                        """
                        INSERT INTO chat_sessions (
                            id, user_id, workspace_id, title, mode, retention_days, expires_at
                        )
                        VALUES (
                            %s, %s, %s, %s, %s::user_mode, %s,
                            NOW() + (%s || ' days')::INTERVAL
                        )
                        RETURNING id::TEXT
                        """,
                        (
                            session_id,
                            user_id,
                            workspace_id,
                            title,
                            safe_mode,
                            retention_days,
                            retention_days,
                        ),
                    ).fetchone()
            return row['id'] if row else session_id

        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        expires_at = (datetime.now() + timedelta(days=retention_days)).isoformat()
        now = datetime.now().isoformat()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM chat_sessions
            WHERE id = ?
              AND archived_at IS NULL
              AND datetime(expires_at) > CURRENT_TIMESTAMP
            """,
            (session_id,),
        )
        existing = cursor.fetchone()
        cursor.execute("SELECT id FROM chat_sessions WHERE id = ?", (session_id,))
        owned_expired = cursor.fetchone()
        if owned_expired and not existing:
            session_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT OR IGNORE INTO chat_sessions (
                id, title, mode, retention_days, expires_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, title, safe_mode, retention_days, expires_at, now, now),
        )
        cursor.execute(
            """
            UPDATE chat_sessions
            SET updated_at = ?,
                title = CASE WHEN title IS NULL OR title = '' OR title = 'Chat' THEN ? ELSE title END
            WHERE id = ?
            """,
            (now, title, session_id),
        )
        conn.commit()
        conn.close()
        return session_id

    @staticmethod
    def list_chat_sessions(user_id, limit=30, db_path=None, workspace_id=None):
        limit = max(1, min(int(limit or 30), 100))
        if pg.enabled():
            workspace_id = _resolve_workspace_id(user_id, workspace_id)
            with pg.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        session.id::TEXT,
                        COALESCE(NULLIF(session.title, ''), 'Chat') AS title,
                        session.mode::TEXT AS mode,
                        session.retention_days,
                        session.expires_at,
                        session.created_at,
                        session.updated_at,
                        COUNT(history.id) AS message_count,
                        MAX(history.created_at) AS last_message_at,
                        (
                            ARRAY_AGG(history.user_message ORDER BY history.created_at DESC)
                            FILTER (WHERE history.user_message IS NOT NULL AND history.user_message <> '')
                        )[1] AS last_message
                    FROM chat_sessions session
                    LEFT JOIN history
                        ON history.chat_session_id = session.id
                       AND history.action_type = 'chat'
                    WHERE session.user_id = %s
                      AND session.workspace_id = %s
                      AND session.archived_at IS NULL
                      AND session.expires_at > NOW()
                    GROUP BY session.id
                    ORDER BY COALESCE(MAX(history.created_at), session.updated_at, session.created_at) DESC
                    LIMIT %s
                    """,
                    (user_id, workspace_id, limit),
                ).fetchall()
                return pg.normalize_rows(rows)

        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                session.id,
                COALESCE(NULLIF(session.title, ''), 'Chat') AS title,
                session.mode,
                session.retention_days,
                session.expires_at,
                session.created_at,
                session.updated_at,
                COUNT(history.id) AS message_count,
                MAX(history.created_at) AS last_message_at,
                (
                    SELECT h2.user_message
                    FROM history h2
                    WHERE h2.chat_session_id = session.id
                      AND h2.action_type = 'chat'
                    ORDER BY h2.created_at DESC
                    LIMIT 1
                ) AS last_message
            FROM chat_sessions session
            LEFT JOIN history
                ON history.chat_session_id = session.id
               AND history.action_type = 'chat'
            WHERE session.archived_at IS NULL
              AND datetime(session.expires_at) > CURRENT_TIMESTAMP
            GROUP BY session.id
            ORDER BY COALESCE(MAX(history.created_at), session.updated_at, session.created_at) DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    @staticmethod
    def chat_session_available(user_id, session_id, db_path=None, workspace_id=None):
        session_id = History._normalize_session_id(session_id)
        if pg.enabled():
            workspace_id = _resolve_workspace_id(user_id, workspace_id)
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    SELECT id
                    FROM chat_sessions
                    WHERE id = %s
                      AND user_id = %s
                      AND workspace_id = %s
                      AND archived_at IS NULL
                      AND expires_at > NOW()
                    """,
                    (session_id, user_id, workspace_id),
                ).fetchone()
                return bool(row)

        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM chat_sessions
            WHERE id = ?
              AND archived_at IS NULL
              AND datetime(expires_at) > CURRENT_TIMESTAMP
            """,
            (session_id,),
        )
        available = bool(cursor.fetchone())
        conn.close()
        return available

    @staticmethod
    def update_chat_session(user_id, session_id, title=None, retention_days=None, db_path=None, workspace_id=None):
        session_id = History._normalize_session_id(session_id)
        assignments = []
        values = []
        if title is not None:
            assignments.append("title = %s" if pg.enabled() else "title = ?")
            values.append((title or 'Chat').strip()[:120] or 'Chat')
        if retention_days is not None:
            is_premium = pg.enabled() and subscription_model.is_premium(user_id)
            days = History._clamp_retention_days(retention_days, is_premium=is_premium)
            if pg.enabled():
                assignments.extend(["retention_days = %s", "expires_at = NOW() + (%s || ' days')::INTERVAL"])
                values.extend([days, days])
            else:
                assignments.extend(["retention_days = ?", "expires_at = ?"])
                values.extend([days, (datetime.now() + timedelta(days=days)).isoformat()])
        if not assignments:
            return False

        if pg.enabled():
            workspace_id = _resolve_workspace_id(user_id, workspace_id)
            with pg.connection() as conn:
                cur = conn.execute(
                    f"""
                    UPDATE chat_sessions
                    SET {', '.join(assignments)}, updated_at = NOW()
                    WHERE id = %s AND user_id = %s AND workspace_id = %s
                    """,
                    (*values, session_id, user_id, workspace_id),
                )
                return cur.rowcount > 0

        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE chat_sessions SET {', '.join(assignments)}, updated_at = ? WHERE id = ?",
            (*values, datetime.now().isoformat(), session_id),
        )
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    @staticmethod
    def delete_chat_session(user_id, session_id, db_path=None, workspace_id=None):
        """Delete a chat session and the chat messages attached to it."""
        session_id = History._normalize_session_id(session_id)
        if not session_id:
            return False

        if pg.enabled():
            workspace_id = _resolve_workspace_id(user_id, workspace_id)
            with pg.connection() as conn:
                conn.execute(
                    """
                    DELETE FROM history
                    WHERE user_id = %s AND workspace_id = %s
                      AND action_type = %s::activity_type AND chat_session_id = %s
                    """,
                    (user_id, workspace_id, 'chat', session_id),
                )
                cur = conn.execute(
                    "DELETE FROM chat_sessions WHERE id = %s AND user_id = %s AND workspace_id = %s",
                    (session_id, user_id, workspace_id),
                )
                return cur.rowcount > 0

        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM history WHERE action_type = ? AND chat_session_id = ?",
            ('chat', session_id),
        )
        cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    @staticmethod
    def delete_all_chat_sessions(user_id, workspace_id=None, db_path=None):
        """Delete all saved chat-session metadata for one user in one workspace.

        PostgreSQL cascades this deletion to session_memory. SQLite stores one
        tenant per database file; its memory rows are cleared separately by
        the route so this method remains focused on chat session metadata.
        """
        if pg.enabled():
            workspace_id = _resolve_workspace_id(user_id, workspace_id)
            with pg.connection() as conn:
                cur = conn.execute(
                    "DELETE FROM chat_sessions WHERE user_id = %s AND workspace_id = %s",
                    (user_id, workspace_id),
                )
                return cur.rowcount

        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat_sessions")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted

    @staticmethod
    def clear_chat_state(
        user_id,
        workspace_id=None,
        db_path=None,
        chat_session_id=None,
        clear_all_history=False,
    ):
        """Atomically clear history, working memory, and session metadata.

        A session-specific clear retains that empty session for clients that
        continue chatting in it. A user-wide clear removes all session shells
        for the current workspace only -- clearing chat while in Personal
        must never touch a Business workspace's chat history, or vice versa.
        """
        user_id = user_id or 'default'
        if pg.enabled():
            workspace_id = _resolve_workspace_id(user_id, workspace_id)
            with pg.connection() as conn:
                if chat_session_id:
                    history_cur = conn.execute(
                        """
                        DELETE FROM history
                        WHERE user_id = %s
                          AND workspace_id = %s
                          AND action_type = 'chat'
                          AND chat_session_id = %s
                        """,
                        (user_id, workspace_id, chat_session_id),
                    )
                    memory_cur = conn.execute(
                        """
                        DELETE FROM session_memory
                        WHERE user_id = %s AND workspace_id = %s AND chat_session_id = %s
                        """,
                        (user_id, workspace_id, chat_session_id),
                    )
                    session_count = 0
                else:
                    history_sql = (
                        "DELETE FROM history WHERE user_id = %s AND workspace_id = %s"
                        if clear_all_history
                        else "DELETE FROM history "
                        "WHERE user_id = %s AND workspace_id = %s AND action_type = 'chat'"
                    )
                    history_cur = conn.execute(history_sql, (user_id, workspace_id))
                    memory_cur = conn.execute(
                        "DELETE FROM session_memory WHERE user_id = %s AND workspace_id = %s",
                        (user_id, workspace_id),
                    )
                    session_cur = conn.execute(
                        "DELETE FROM chat_sessions WHERE user_id = %s AND workspace_id = %s",
                        (user_id, workspace_id),
                    )
                    session_count = session_cur.rowcount
                return {
                    'history': history_cur.rowcount,
                    'memory': memory_cur.rowcount,
                    'sessions': session_count,
                }

        db_path = db_path or Config.DATABASE_PATH
        History.init_db(db_path=db_path)
        # Import lazily to avoid a model import cycle.
        from models.session_memory import SessionMemory
        SessionMemory.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            if chat_session_id:
                history_cur = conn.execute(
                    """
                    DELETE FROM history
                    WHERE action_type = 'chat' AND chat_session_id = ?
                    """,
                    (chat_session_id,),
                )
                memory_cur = conn.execute(
                    "DELETE FROM session_memory WHERE chat_session_id = ?",
                    (chat_session_id,),
                )
                session_count = 0
            else:
                history_sql = (
                    "DELETE FROM history"
                    if clear_all_history
                    else "DELETE FROM history WHERE action_type = 'chat'"
                )
                history_cur = conn.execute(history_sql)
                memory_cur = conn.execute("DELETE FROM session_memory")
                session_cur = conn.execute("DELETE FROM chat_sessions")
                session_count = session_cur.rowcount
            conn.commit()
            return {
                'history': history_cur.rowcount,
                'memory': memory_cur.rowcount,
                'sessions': session_count,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def create(user_message, assistant_response, action_type="chat", related_id=None, db_path=None, chat_session_id=None, workspace_id=None):
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            pg.ensure_user(user_id)
            workspace_id = _resolve_workspace_id(user_id, workspace_id)
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    INSERT INTO history (
                        user_id, workspace_id, user_message, assistant_response,
                        action_type, related_id, chat_session_id, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s::activity_type, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, workspace_id, user_message, assistant_response, action_type, related_id, chat_session_id, datetime.now()),
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
    def get_recent(limit=10, db_path=None, chat_session_id=None, workspace_id=None):
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            workspace_id = _resolve_workspace_id(user_id, workspace_id)
            with pg.connection() as conn:
                if chat_session_id:
                    rows = conn.execute(
                        """
                        SELECT * FROM history
                        WHERE user_id = %s
                          AND workspace_id = %s
                          AND chat_session_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (user_id, workspace_id, chat_session_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT * FROM history
                        WHERE user_id = %s
                          AND workspace_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (user_id, workspace_id, limit),
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
    def clear_all(action_type=None, db_path=None, chat_session_id=None, workspace_id=None):
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            workspace_id = _resolve_workspace_id(user_id, workspace_id)
            with pg.connection() as conn:
                if chat_session_id:
                    cur = conn.execute(
                        "DELETE FROM history WHERE user_id = %s AND workspace_id = %s AND action_type = %s AND chat_session_id = %s",
                        (user_id, workspace_id, action_type or 'chat', chat_session_id),
                    )
                elif action_type:
                    cur = conn.execute(
                        "DELETE FROM history WHERE user_id = %s AND workspace_id = %s AND action_type = %s",
                        (user_id, workspace_id, action_type),
                    )
                else:
                    cur = conn.execute(
                        "DELETE FROM history WHERE user_id = %s AND workspace_id = %s",
                        (user_id, workspace_id),
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
