import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg


class IntentPattern:
    """Global cache of message phrasings the AI has classified for a
    confirmation-gated intent (see CACHEABLE_INTENTS in
    services/intent_orchestrator.py). Shared across every user on purpose --
    'how people phrase a request' is a language-pattern fact, not personal
    data, so one user's resolved phrasing safely benefits everyone.

    Every pattern starts as status='candidate': the AI is still called and
    asked to confirm it every time a similar message comes in, spending
    quota deliberately during this "still learning" period. Only once the
    AI has agreed on the same intent CONFIRM_THRESHOLD times in a row does
    it graduate to status='trusted', at which point the cache is allowed to
    answer on Bob's own without calling the AI at all.
    """

    _initialized = False
    CONFIRM_THRESHOLD = 3

    @staticmethod
    def init_db():
        if pg.enabled():
            return
        if IntentPattern._initialized:
            return
        db_path = Config.DATABASE_PATH
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS intent_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phrase TEXT NOT NULL,
                intent TEXT NOT NULL,
                confidence REAL DEFAULT 0.6,
                status TEXT DEFAULT 'candidate',
                confirm_count INTEGER DEFAULT 1,
                hit_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Add columns if missing (installs that already had the table from
        # before status/confirm_count existed).
        for ddl in (
            "ALTER TABLE intent_patterns ADD COLUMN status TEXT DEFAULT 'candidate'",
            "ALTER TABLE intent_patterns ADD COLUMN confirm_count INTEGER DEFAULT 1",
            "ALTER TABLE intent_patterns ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP",
        ):
            try:
                cursor.execute(ddl)
            except sqlite3.OperationalError:
                pass
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_patterns_created ON intent_patterns(created_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_patterns_status ON intent_patterns(status)')
        conn.commit()
        conn.close()
        IntentPattern._initialized = True

    @staticmethod
    def create(phrase, intent, confidence=0.6, status='candidate', confirm_count=1):
        if pg.enabled():
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    INSERT INTO intent_patterns (phrase, intent, confidence, status, confirm_count)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (phrase, intent, confidence, status, confirm_count),
                ).fetchone()
                return pg.normalize_row(row)

        IntentPattern.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO intent_patterns (phrase, intent, confidence, status, confirm_count) VALUES (?, ?, ?, ?, ?)',
            (phrase, intent, confidence, status, confirm_count),
        )
        conn.commit()
        pattern_id = cursor.lastrowid
        conn.close()
        return {
            'id': pattern_id, 'phrase': phrase, 'intent': intent, 'confidence': confidence,
            'status': status, 'confirm_count': confirm_count, 'hit_count': 0,
        }

    @staticmethod
    def get_all(limit=3000, status=None):
        if pg.enabled():
            with pg.connection() as conn:
                if status:
                    rows = conn.execute(
                        'SELECT * FROM intent_patterns WHERE status = %s ORDER BY created_at DESC LIMIT %s',
                        (status, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        'SELECT * FROM intent_patterns ORDER BY created_at DESC LIMIT %s',
                        (limit,),
                    ).fetchall()
                return pg.normalize_rows(rows)

        IntentPattern.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if status:
            cursor.execute(
                'SELECT * FROM intent_patterns WHERE status = ? ORDER BY created_at DESC LIMIT ?',
                (status, limit),
            )
        else:
            cursor.execute('SELECT * FROM intent_patterns ORDER BY created_at DESC LIMIT ?', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def reinforce(pattern_id):
        """Called when the AI confirms the same intent again for a phrase
        similar to this candidate -- bumps confirm_count and promotes to
        'trusted' once CONFIRM_THRESHOLD is reached."""
        if pg.enabled():
            with pg.connection() as conn:
                conn.execute(
                    """
                    UPDATE intent_patterns
                    SET confirm_count = confirm_count + 1,
                        status = CASE WHEN confirm_count + 1 >= %s THEN 'trusted' ELSE status END,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (IntentPattern.CONFIRM_THRESHOLD, pattern_id),
                )
            return

        IntentPattern.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE intent_patterns
            SET confirm_count = confirm_count + 1,
                status = CASE WHEN confirm_count + 1 >= ? THEN 'trusted' ELSE status END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (IntentPattern.CONFIRM_THRESHOLD, pattern_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def increment_hit(pattern_id):
        if pg.enabled():
            with pg.connection() as conn:
                conn.execute(
                    'UPDATE intent_patterns SET hit_count = hit_count + 1 WHERE id = %s',
                    (pattern_id,),
                )
            return

        IntentPattern.init_db()
        conn = sqlite3.connect(Config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('UPDATE intent_patterns SET hit_count = hit_count + 1 WHERE id = ?', (pattern_id,))
        conn.commit()
        conn.close()
