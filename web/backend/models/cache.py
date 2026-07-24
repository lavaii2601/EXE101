import sqlite3
import os
import json
from datetime import datetime, timedelta
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg

class Cache:
    """Cache model for storing temporary data (emails, calendar events, schedules)"""

    # Cache TTL in seconds (5 minutes)
    DEFAULT_TTL = 300

    _initialized_dbs = set()

    @staticmethod
    def init_db(db_path=None):
        """Initialize cache table"""
        if pg.enabled():
            return
        db_path = db_path or Config.DATABASE_PATH
        if db_path in Cache._initialized_dbs:
            return
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                expires_at DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index for faster lookups
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cache_key ON cache(key)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cache_key_expires ON cache(key, expires_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at)')
        except sqlite3.OperationalError:
            pass

        conn.commit()
        conn.close()
        Cache._initialized_dbs.add(db_path)

    @staticmethod
    def set(key, value, ttl=DEFAULT_TTL, db_path=None):
        """Store data in cache"""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            pg.ensure_user(user_id)
            expires_at = datetime.utcnow() + timedelta(seconds=ttl)
            with pg.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO cache (user_id, key, value, expires_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id, key) DO UPDATE
                    SET value = EXCLUDED.value,
                        expires_at = EXCLUDED.expires_at
                    """,
                    (user_id, key, pg.json_value(value), expires_at),
                )
            return

        db_path = db_path or Config.DATABASE_PATH
        Cache.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        value_str = json.dumps(value) if not isinstance(value, str) else value
        
        cursor.execute('''
            INSERT OR REPLACE INTO cache (key, value, expires_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (key, value_str, expires_at.isoformat()))
        
        conn.commit()
        conn.close()

    @staticmethod
    def set_versioned(key, value, expected_revision, ttl=DEFAULT_TTL, db_path=None):
        """Atomically store a JSON value when its revision still matches.

        This is used for editable state such as the shared checklist. The
        returned tuple is ``(saved, value)``; on conflict, ``value`` is the
        current server copy so clients can reload without overwriting edits
        made by the web or APK.
        """
        try:
            expected_revision = max(0, int(expected_revision or 0))
        except (TypeError, ValueError):
            expected_revision = 0

        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            pg.ensure_user(user_id)
            expires_at = datetime.utcnow() + timedelta(seconds=ttl)
            with pg.connection() as conn:
                # Materialize the row before locking it so two first-time
                # writers also serialize correctly across Railway workers.
                conn.execute(
                    """
                    INSERT INTO cache (user_id, key, value, expires_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id, key) DO NOTHING
                    """,
                    (user_id, key, pg.json_value({'revision': 0}), expires_at),
                )
                row = conn.execute(
                    """
                    SELECT value, expires_at <= NOW() AS expired
                    FROM cache
                    WHERE user_id = %s AND key = %s
                    FOR UPDATE
                    """,
                    (user_id, key),
                ).fetchone()
                current = (
                    row.get('value')
                    if row and not row.get('expired')
                    else {}
                )
                current = current if isinstance(current, dict) else {}
                try:
                    current_revision = max(0, int(current.get('revision') or 0))
                except (TypeError, ValueError):
                    current_revision = 0
                if current_revision != expected_revision:
                    return False, current

                saved = dict(value or {})
                saved['revision'] = current_revision + 1
                conn.execute(
                    """
                    UPDATE cache
                    SET value = %s, expires_at = %s
                    WHERE user_id = %s AND key = %s
                    """,
                    (pg.json_value(saved), expires_at, user_id, key),
                )
                return True, saved

        db_path = db_path or Config.DATABASE_PATH
        Cache.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(
                """
                SELECT
                    value,
                    datetime(expires_at) <= CURRENT_TIMESTAMP AS expired
                FROM cache
                WHERE key = ?
                """,
                (key,),
            ).fetchone()
            current = {}
            if row and not row['expired']:
                try:
                    current = json.loads(row['value'])
                except Exception:
                    current = {}
            current = current if isinstance(current, dict) else {}
            try:
                current_revision = max(0, int(current.get('revision') or 0))
            except (TypeError, ValueError):
                current_revision = 0
            if current_revision != expected_revision:
                conn.rollback()
                return False, current

            saved = dict(value or {})
            saved['revision'] = current_revision + 1
            expires_at = datetime.utcnow() + timedelta(seconds=ttl)
            conn.execute(
                """
                INSERT INTO cache (key, value, expires_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    expires_at = excluded.expires_at,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, json.dumps(saved), expires_at.isoformat()),
            )
            conn.commit()
            return True, saved
        finally:
            conn.close()
    
    @staticmethod
    def get(key, db_path=None):
        """Get data from cache if not expired"""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    SELECT value FROM cache
                    WHERE user_id = %s AND key = %s AND expires_at > NOW()
                    """,
                    (user_id, key),
                ).fetchone()
                return row['value'] if row else None

        db_path = db_path or Config.DATABASE_PATH
        Cache.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT value FROM cache 
            WHERE key = ? AND datetime(expires_at) > CURRENT_TIMESTAMP
        ''', (key,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            try:
                return json.loads(result['value'])
            except:
                return result['value']
        return None

    @staticmethod
    def get_many(keys, db_path=None):
        """Get multiple non-expired cache entries in one database query."""
        keys = [key for key in (keys or []) if key]
        if not keys:
            return {}

        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT key, value FROM cache
                    WHERE user_id = %s
                      AND key = ANY(%s)
                      AND expires_at > NOW()
                    """,
                    (user_id, keys),
                ).fetchall()
                return {row['key']: row['value'] for row in rows}

        db_path = db_path or Config.DATABASE_PATH
        Cache.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        placeholders = ','.join(['?'] * len(keys))
        cursor.execute(
            f'''
            SELECT key, value FROM cache
            WHERE key IN ({placeholders})
              AND datetime(expires_at) > CURRENT_TIMESTAMP
            ''',
            keys
        )
        rows = cursor.fetchall()
        conn.close()

        result = {}
        for row in rows:
            try:
                result[row['key']] = json.loads(row['value'])
            except Exception:
                result[row['key']] = row['value']
        return result
    
    @staticmethod
    def delete(key, db_path=None):
        """Delete cache entry"""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                conn.execute(
                    "DELETE FROM cache WHERE user_id = %s AND key = %s",
                    (user_id, key),
                )
            return

        db_path = db_path or Config.DATABASE_PATH
        Cache.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM cache WHERE key = ?', (key,))
        conn.commit()
        conn.close()
    
    @staticmethod
    def clear_pattern(pattern, db_path=None):
        """Clear all cache entries matching pattern"""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                conn.execute(
                    "DELETE FROM cache WHERE user_id = %s AND key LIKE %s",
                    (user_id, pattern),
                )
            return

        db_path = db_path or Config.DATABASE_PATH
        Cache.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM cache WHERE key LIKE ?', (pattern,))
        conn.commit()
        conn.close()
    
    @staticmethod
    def clear_expired(db_path=None):
        """Clear expired cache entries"""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                conn.execute(
                    "DELETE FROM cache WHERE user_id = %s AND expires_at < NOW()",
                    (user_id,),
                )
            return

        db_path = db_path or Config.DATABASE_PATH
        Cache.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            'DELETE FROM cache WHERE datetime(expires_at) < CURRENT_TIMESTAMP'
        )
        conn.commit()
        conn.close()
    
    @staticmethod
    def clear_all(db_path=None):
        """Clear all cache entries"""
        if pg.enabled():
            user_id = pg.user_id_from_db_path(db_path)
            with pg.connection() as conn:
                conn.execute("DELETE FROM cache WHERE user_id = %s", (user_id,))
            return

        db_path = db_path or Config.DATABASE_PATH
        Cache.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM cache')
        conn.commit()
        conn.close()
