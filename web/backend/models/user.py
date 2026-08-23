import sqlite3
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg


class User:
    _initialized_dbs = set()

    @staticmethod
    def init_db():
        """Initialize users table"""
        if pg.enabled():
            return
        db_path = Config.DATABASE_PATH
        if db_path in User._initialized_dbs:
            return
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                name TEXT,
                email TEXT,
                avatar_url TEXT,
                password_hash TEXT,
                gmail_email TEXT,
                gmail_name TEXT,
                gmail_picture TEXT,
                gmail_connected INTEGER DEFAULT 0,
                gmail_connected_at DATETIME,
                user_mode TEXT DEFAULT '',
                user_mode_selected_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Migration: Add new columns if they don't exist
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN gmail_email TEXT')
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN gmail_name TEXT')
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN gmail_picture TEXT')
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN gmail_connected_at DATETIME')
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN user_mode TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN user_mode_selected_at DATETIME")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        except sqlite3.OperationalError:
            pass

        conn.commit()
        conn.close()
        User._initialized_dbs.add(db_path)

    @staticmethod
    def get_or_create(user_id, name='Teacher', email=''):
        """Get or create user"""
        if pg.enabled():
            return pg.ensure_user(user_id, name=name, email=email)

        db_path = Config.DATABASE_PATH
        User.init_db()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.execute('''
                INSERT INTO users (user_id, name, email)
                VALUES (?, ?, ?)
            ''', (user_id, name, email))
            conn.commit()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()
        
        conn.close()
        return dict(user) if user else None

    @staticmethod
    def update(user_id, **kwargs):
        """Update user info"""
        if pg.enabled():
            allowed_fields = [
                'name', 'email', 'avatar_url', 'gmail_connected', 'gmail_email',
                'gmail_name', 'gmail_picture', 'gmail_connected_at', 'user_mode',
                'user_mode_selected_at', 'password_hash'
            ]
            updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
            if not updates:
                return False
            if updates.get('user_mode') == '':
                updates['user_mode'] = None
            if 'gmail_connected' in updates:
                updates['gmail_connected'] = bool(updates['gmail_connected'])
            pg.ensure_user(user_id)
            set_parts = [
                f'{key} = %s::user_mode' if key == 'user_mode' else f'{key} = %s'
                for key in updates.keys()
            ]
            set_clause = ', '.join(set_parts)
            values = list(updates.values()) + [user_id]
            with pg.connection() as conn:
                cur = conn.execute(
                    f"UPDATE users SET {set_clause} WHERE user_id = %s",
                    values,
                )
                return cur.rowcount > 0

        db_path = Config.DATABASE_PATH
        User.init_db()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        allowed_fields = [
            'name', 'email', 'avatar_url', 'gmail_connected', 'gmail_email',
            'gmail_name', 'gmail_picture', 'gmail_connected_at', 'user_mode',
            'user_mode_selected_at', 'password_hash'
        ]
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not updates:
            conn.close()
            return False
        
        updates['updated_at'] = datetime.now().isoformat()
        
        set_clause = ', '.join([f'{k} = ?' for k in updates.keys()])
        values = list(updates.values())
        values.append(user_id)
        
        cursor.execute(f'''
            UPDATE users
            SET {set_clause}
            WHERE user_id = ?
        ''', values)
        
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    @staticmethod
    def get(user_id):
        """Get user by ID"""
        if pg.enabled():
            with pg.connection() as conn:
                user = conn.execute(
                    "SELECT * FROM users WHERE user_id = %s",
                    (user_id,),
                ).fetchone()
                return pg.normalize_row(user)

        db_path = Config.DATABASE_PATH
        User.init_db()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        return dict(user) if user else None

    @staticmethod
    def get_by_email(email):
        """Look up a user by their login email or connected Gmail address.

        Used by password-based register/login, which have no user_id to key
        off of until the account is found. Case-insensitive; returns the
        oldest matching account if more than one row happens to match.
        """
        email = (email or '').strip().lower()
        if not email:
            return None

        if pg.enabled():
            with pg.connection() as conn:
                user = conn.execute(
                    """
                    SELECT * FROM users
                    WHERE LOWER(COALESCE(email, '')) = %s
                       OR LOWER(COALESCE(gmail_email, '')) = %s
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (email, email),
                ).fetchone()
                return pg.normalize_row(user)

        db_path = Config.DATABASE_PATH
        User.init_db()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM users
            WHERE LOWER(COALESCE(email, '')) = ?
               OR LOWER(COALESCE(gmail_email, '')) = ?
            ORDER BY created_at ASC
            LIMIT 1
            ''',
            (email, email),
        )
        user = cursor.fetchone()
        conn.close()
        return dict(user) if user else None

    @staticmethod
    def list_user_ids(connected_only=False, limit=500):
        """Return known user identifiers for background jobs."""
        if pg.enabled():
            where = "WHERE gmail_connected = TRUE" if connected_only else ""
            with pg.connection() as conn:
                rows = conn.execute(
                    f"""
                    SELECT user_id FROM users
                    {where}
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
                return [row['user_id'] for row in rows if row.get('user_id')]

        db_path = Config.DATABASE_PATH
        User.init_db()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        where = "WHERE gmail_connected = 1" if connected_only else ""
        cursor.execute(
            f'''
            SELECT user_id FROM users
            {where}
            ORDER BY updated_at DESC
            LIMIT ?
            ''',
            (limit,)
        )
        users = [row['user_id'] for row in cursor.fetchall() if row['user_id']]
        conn.close()
        return users
