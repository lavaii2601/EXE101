import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg


class KnowledgeDocument:
    """Knowledge base for Bob's RAG lookups.

    Three kinds of rows share this table, distinguished by `user_id` and
    `workspace_id`:
    - Global/product knowledge (user_id IS NULL AND workspace_id IS NULL) --
      FlowMate feature docs, anything added manually -- visible to every
      user, exactly like before workspace_id existed.
    - Per-user learned rows (user_id set, workspace_id NULL, source='auto',
      'web', or 'mentor') -- facts, corrections, preferences, sourced web
      research lessons, or AI mentor lessons Bob picks up for a specific
      user. These must NEVER be visible to a different user_id, and are
      never auto-promoted to a workspace (see Phase 4's confirm-before-
      sharing principle -- Bob does not decide on its own that a personal
      fact belongs to the company).
    - Workspace-curated rows (workspace_id set, source='manual') -- policy,
      template, FAQ docs an owner/admin explicitly authors for their
      Business workspace (design doc section 8.7). Visible to every active
      member of that workspace, never another workspace's members.
    """

    _initialized = False

    @staticmethod
    def init_db():
        if pg.enabled():
            return
        if KnowledgeDocument._initialized:
            return
        db_path = Config.DATABASE_PATH
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT DEFAULT '',
                source TEXT DEFAULT 'manual',
                user_id TEXT DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Add columns missing on pre-existing installs (created before
        # per-user auto-learned memories / workspace-curated docs existed).
        for column_sql in (
            'ALTER TABLE knowledge_documents ADD COLUMN user_id TEXT DEFAULT NULL',
            'ALTER TABLE knowledge_documents ADD COLUMN workspace_id TEXT DEFAULT NULL',
            'ALTER TABLE knowledge_documents ADD COLUMN created_by_user_id TEXT DEFAULT NULL',
        ):
            try:
                cursor.execute(column_sql)
            except sqlite3.OperationalError:
                pass
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_documents_created ON knowledge_documents(created_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_documents_user ON knowledge_documents(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_documents_workspace ON knowledge_documents(workspace_id)')
        conn.commit()
        conn.close()
        KnowledgeDocument._initialized = True

    @staticmethod
    def create(title, content, tags='', source='manual', user_id=None, workspace_id=None, created_by_user_id=None):
        if pg.enabled():
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    INSERT INTO knowledge_documents (title, content, tags, source, user_id, workspace_id, created_by_user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (title, content, tags, source, user_id, workspace_id, created_by_user_id),
                ).fetchone()
                return pg.normalize_row(row)

        KnowledgeDocument.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO knowledge_documents (title, content, tags, source, user_id, workspace_id, created_by_user_id) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (title, content, tags, source, user_id, workspace_id, created_by_user_id),
        )
        conn.commit()
        doc_id = cursor.lastrowid
        conn.close()
        return KnowledgeDocument.get_by_id(doc_id)

    @staticmethod
    def get_all(limit=500, user_id=None, scope_to_user=False, workspace_id=None):
        """By default returns every document (back-compat for the admin/
        manual knowledge UI, which manages the shared/global library, and
        for KnowledgeService.rebuild_index's in-memory RAG index, which
        filters visibility itself per search call).

        Pass workspace_id to instead get only that workspace's curated docs
        (the Business Knowledge management list -- an owner/admin does not
        want to page through the whole global+personal library).

        Pass scope_to_user=True to get only what a specific user may see
        outside any workspace: global docs (user_id IS NULL) plus that
        user's own."""
        if pg.enabled():
            with pg.connection() as conn:
                if workspace_id:
                    rows = conn.execute(
                        'SELECT * FROM knowledge_documents WHERE workspace_id = %s '
                        'ORDER BY created_at DESC LIMIT %s',
                        (workspace_id, limit),
                    ).fetchall()
                elif scope_to_user:
                    rows = conn.execute(
                        'SELECT * FROM knowledge_documents WHERE user_id IS NULL OR user_id = %s '
                        'ORDER BY created_at DESC LIMIT %s',
                        (user_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        'SELECT * FROM knowledge_documents ORDER BY created_at DESC LIMIT %s',
                        (limit,),
                    ).fetchall()
                return pg.normalize_rows(rows)

        KnowledgeDocument.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if workspace_id:
            cursor.execute(
                'SELECT * FROM knowledge_documents WHERE workspace_id = ? '
                'ORDER BY created_at DESC LIMIT ?',
                (workspace_id, limit),
            )
        elif scope_to_user:
            cursor.execute(
                'SELECT * FROM knowledge_documents WHERE user_id IS NULL OR user_id = ? '
                'ORDER BY created_at DESC LIMIT ?',
                (user_id, limit),
            )
        else:
            cursor.execute('SELECT * FROM knowledge_documents ORDER BY created_at DESC LIMIT ?', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def get_by_id(doc_id):
        if pg.enabled():
            with pg.connection() as conn:
                row = conn.execute(
                    'SELECT * FROM knowledge_documents WHERE id = %s', (doc_id,)
                ).fetchone()
                return pg.normalize_row(row)

        KnowledgeDocument.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM knowledge_documents WHERE id = ?', (doc_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_by_id_and_workspace(doc_id, workspace_id):
        """Like get_by_id, but only returns the row if it actually belongs
        to workspace_id -- the WHERE clause does the comparison so a UUID
        column vs. a str workspace_id from resolve_context can never
        mismatch the way a Python-side `==` after fetch could."""
        if pg.enabled():
            with pg.connection() as conn:
                row = conn.execute(
                    'SELECT * FROM knowledge_documents WHERE id = %s AND workspace_id = %s',
                    (doc_id, workspace_id),
                ).fetchone()
                return pg.normalize_row(row)

        KnowledgeDocument.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM knowledge_documents WHERE id = ? AND workspace_id = ?',
            (doc_id, workspace_id),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def update(doc_id, title=None, content=None, tags=None):
        fields = {}
        if title is not None:
            fields['title'] = title
        if content is not None:
            fields['content'] = content
        if tags is not None:
            fields['tags'] = tags
        if not fields:
            return KnowledgeDocument.get_by_id(doc_id)

        if pg.enabled():
            with pg.connection() as conn:
                set_clause = ', '.join(f'{key} = %s' for key in fields) + ', updated_at = NOW()'
                conn.execute(
                    f'UPDATE knowledge_documents SET {set_clause} WHERE id = %s',
                    (*fields.values(), doc_id),
                )
            return KnowledgeDocument.get_by_id(doc_id)

        KnowledgeDocument.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        cursor = conn.cursor()
        set_clause = ', '.join(f'{key} = ?' for key in fields) + ', updated_at = CURRENT_TIMESTAMP'
        cursor.execute(
            f'UPDATE knowledge_documents SET {set_clause} WHERE id = ?',
            (*fields.values(), doc_id),
        )
        conn.commit()
        updated = cursor.rowcount
        conn.close()
        return KnowledgeDocument.get_by_id(doc_id) if updated else None

    @staticmethod
    def delete(doc_id):
        if pg.enabled():
            with pg.connection() as conn:
                cur = conn.execute('DELETE FROM knowledge_documents WHERE id = %s', (doc_id,))
                return cur.rowcount > 0

        KnowledgeDocument.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM knowledge_documents WHERE id = ?', (doc_id,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted > 0

    @staticmethod
    def count():
        if pg.enabled():
            with pg.connection() as conn:
                row = conn.execute('SELECT COUNT(*) AS total FROM knowledge_documents').fetchone()
                return int(row['total']) if row else 0

        KnowledgeDocument.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM knowledge_documents')
        total = cursor.fetchone()[0]
        conn.close()
        return int(total)
