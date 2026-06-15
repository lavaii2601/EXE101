from datetime import datetime
import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config

class Schedule:
    _initialized_dbs = set()

    @staticmethod
    def init_db(db_path=None):
        """Initialize schedule table"""
        db_path = db_path or Config.DATABASE_PATH
        if db_path in Schedule._initialized_dbs:
            return
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                attendees TEXT,
                email_body TEXT,
                calendar_event_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add calendar_event_id column if it doesn't exist (migration)
        try:
            cursor.execute('ALTER TABLE schedules ADD COLUMN calendar_event_id TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        # Add location column if missing
        try:
            cursor.execute('ALTER TABLE schedules ADD COLUMN location TEXT')
        except sqlite3.OperationalError:
            pass
        
        conn.commit()
        conn.close()
        Schedule._initialized_dbs.add(db_path)

    @staticmethod
    def create(title, description, start_time, end_time, attendees, email_body='', location=None, calendar_event_id=None, db_path=None):
        """Create new schedule"""
        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO schedules (title, description, start_time, end_time, attendees, email_body, location, calendar_event_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ''', (title, description, start_time, end_time, attendees, email_body, location, calendar_event_id))
        conn.commit()
        schedule_id = cursor.lastrowid
        conn.close()
        return schedule_id

    @staticmethod
    def get_by_calendar_event_id(calendar_event_id, db_path=None):
        """Get schedule by Google Calendar event ID"""
        if not calendar_event_id:
            return None
        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM schedules WHERE calendar_event_id = ?', (calendar_event_id,))
        schedule = cursor.fetchone()
        conn.close()
        return dict(schedule) if schedule else None
    
    @staticmethod
    def get_all(limit=50, db_path=None):
        """Get all schedules"""
        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM schedules ORDER BY start_time DESC LIMIT ?', (limit,))
        schedules = cursor.fetchall()
        conn.close()
        return [dict(s) for s in schedules]
    
    @staticmethod
    def get_by_id(schedule_id, db_path=None):
        """Get schedule by ID"""
        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,))
        schedule = cursor.fetchone()
        conn.close()
        return dict(schedule) if schedule else None
    
    @staticmethod
    def update_status(schedule_id, status, db_path=None):
        """Update schedule status"""
        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE schedules 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, schedule_id))
        conn.commit()
        conn.close()

    @staticmethod
    def update(schedule_id, **kwargs):
        """Update schedule information"""
        db_path = kwargs.pop('db_path', None) or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        allowed_fields = ['title', 'description', 'start_time', 'end_time', 'attendees', 'email_body', 'status', 'location', 'calendar_event_id']
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            conn.close()
            return False
        
        updates['updated_at'] = datetime.now().isoformat()
        
        set_clause = ', '.join([f'{k} = ?' for k in updates.keys()])
        values = list(updates.values())
        values.append(schedule_id)
        
        cursor.execute(f'''
            UPDATE schedules
            SET {set_clause}
            WHERE id = ?
        ''', values)
        
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    @staticmethod
    def delete(schedule_id, db_path=None):
        """Delete schedule"""
        db_path = db_path or Config.DATABASE_PATH
        Schedule.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM schedules WHERE id = ?', (schedule_id,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted > 0
