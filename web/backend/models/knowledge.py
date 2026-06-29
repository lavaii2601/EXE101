import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg


class KnowledgeDocument:
    """Shared knowledge base for Bob's RAG lookups.

    Unlike Schedule/History this is not per-user data -- it's product/feature
    knowledge (and any open-source reference material fed in later), so it
    always lives in the shared database rather than a per-user db_path.
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_documents_created ON knowledge_documents(created_at DESC)')
        conn.commit()
        conn.close()
        KnowledgeDocument._initialized = True

    @staticmethod
    def create(title, content, tags='', source='manual'):
        if pg.enabled():
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    INSERT INTO knowledge_documents (title, content, tags, source)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *
                    """,
                    (title, content, tags, source),
                ).fetchone()
                return pg.normalize_row(row)

        KnowledgeDocument.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO knowledge_documents (title, content, tags, source) VALUES (?, ?, ?, ?)',
            (title, content, tags, source),
        )
        conn.commit()
        doc_id = cursor.lastrowid
        conn.close()
        return KnowledgeDocument.get_by_id(doc_id)

    @staticmethod
    def get_all(limit=500):
        if pg.enabled():
            with pg.connection() as conn:
                rows = conn.execute(
                    'SELECT * FROM knowledge_documents ORDER BY created_at DESC LIMIT %s',
                    (limit,),
                ).fetchall()
                return pg.normalize_rows(rows)

        KnowledgeDocument.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
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
