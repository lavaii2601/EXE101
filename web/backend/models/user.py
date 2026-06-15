import sqlite3
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config


class User:
    _initialized_dbs = set()

    @staticmethod
    def init_db():
        """Initialize users table"""
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
        
        conn.commit()
        conn.close()
        User._initialized_dbs.add(db_path)

    @staticmethod
    def get_or_create(user_id, name='Teacher', email=''):
        """Get or create user"""
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
        db_path = Config.DATABASE_PATH
        User.init_db()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        allowed_fields = [
            'name', 'email', 'avatar_url', 'gmail_connected', 'gmail_email',
            'gmail_name', 'gmail_picture', 'gmail_connected_at', 'user_mode',
            'user_mode_selected_at'
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
        db_path = Config.DATABASE_PATH
        User.init_db()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        return dict(user) if user else None
