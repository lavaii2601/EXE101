import sqlite3
import os
import json
from datetime import datetime, timedelta
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config

class Cache:
    """Cache model for storing temporary data (emails, calendar events, schedules)"""

    # Cache TTL in seconds (5 minutes)
    DEFAULT_TTL = 300

    _initialized_dbs = set()

    @staticmethod
    def init_db(db_path=None):
        """Initialize cache table"""
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
        except sqlite3.OperationalError:
            pass

        conn.commit()
        conn.close()
        Cache._initialized_dbs.add(db_path)

    @staticmethod
    def set(key, value, ttl=DEFAULT_TTL, db_path=None):
        """Store data in cache"""
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
    def get(key, db_path=None):
        """Get data from cache if not expired"""
        db_path = db_path or Config.DATABASE_PATH
        Cache.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT value FROM cache 
            WHERE key = ? AND expires_at > CURRENT_TIMESTAMP
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
                  AND expires_at > CURRENT_TIMESTAMP
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
        db_path = db_path or Config.DATABASE_PATH
        Cache.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM cache WHERE expires_at < CURRENT_TIMESTAMP')
        conn.commit()
        conn.close()
    
    @staticmethod
    def clear_all(db_path=None):
        """Clear all cache entries"""
        db_path = db_path or Config.DATABASE_PATH
        Cache.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM cache')
        conn.commit()
        conn.close()
