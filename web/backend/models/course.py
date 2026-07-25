import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg


class Course:
    """A saved course/grade row for the Student-mode GPA calculator
    (Premium-only persistence -- see entitlements.STUDENT_*_LIMITS
    ['gpa_persist']). Free Student users still compute a GPA, just from
    values sent in the request each time (see calculate_gpa below), never
    stored here.
    """

    _initialized_dbs = set()

    @staticmethod
    def init_db(db_path=None):
        if pg.enabled():
            return
        db_path = db_path or Config.DATABASE_PATH
        if db_path in Course._initialized_dbs:
            return
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                term TEXT,
                name TEXT NOT NULL,
                credits REAL NOT NULL,
                grade REAL NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_user ON courses(user_id)')
        conn.commit()
        conn.close()
        Course._initialized_dbs.add(db_path)

    @staticmethod
    def create(user_id, name, credits, grade, term=None, db_path=None):
        if pg.enabled():
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    INSERT INTO courses (user_id, term, name, credits, grade)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (user_id, term, name, credits, grade),
                ).fetchone()
                return pg.normalize_row(row)

        db_path = db_path or Config.DATABASE_PATH
        Course.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO courses (user_id, term, name, credits, grade) VALUES (?, ?, ?, ?, ?)',
            (user_id, term, name, credits, grade),
        )
        conn.commit()
        course_id = cursor.lastrowid
        conn.close()
        return Course.get_by_id(course_id, db_path=db_path)

    @staticmethod
    def get_by_id(course_id, db_path=None):
        if pg.enabled():
            with pg.connection() as conn:
                row = conn.execute(
                    'SELECT * FROM courses WHERE id = %s', (course_id,)
                ).fetchone()
                return pg.normalize_row(row)

        db_path = db_path or Config.DATABASE_PATH
        Course.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM courses WHERE id = ?', (course_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_all(user_id, term=None, db_path=None):
        if pg.enabled():
            with pg.connection() as conn:
                if term:
                    rows = conn.execute(
                        'SELECT * FROM courses WHERE user_id = %s AND term = %s ORDER BY created_at',
                        (user_id, term),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        'SELECT * FROM courses WHERE user_id = %s ORDER BY term, created_at',
                        (user_id,),
                    ).fetchall()
                return pg.normalize_rows(rows)

        db_path = db_path or Config.DATABASE_PATH
        Course.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if term:
            cursor.execute(
                'SELECT * FROM courses WHERE user_id = ? AND term = ? ORDER BY created_at',
                (user_id, term),
            )
        else:
            cursor.execute(
                'SELECT * FROM courses WHERE user_id = ? ORDER BY term, created_at',
                (user_id,),
            )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def delete(course_id, user_id, db_path=None):
        """Scoped to user_id so one user can never delete another's row by
        guessing an id (matches the cross-tenant lesson from Knowledge/RAG)."""
        if pg.enabled():
            with pg.connection() as conn:
                cur = conn.execute(
                    'DELETE FROM courses WHERE id = %s AND user_id = %s',
                    (course_id, user_id),
                )
                return cur.rowcount > 0

        db_path = db_path or Config.DATABASE_PATH
        Course.init_db(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM courses WHERE id = ? AND user_id = ?', (course_id, user_id))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted > 0


def calculate_gpa(courses):
    """Weighted average of `grade` by `credits` -- scale-agnostic (works for
    a 4.0, 10.0, or any other consistent grading scale the caller uses
    across all rows). Returns None if there are no valid credit-bearing
    rows, so callers can distinguish "0.0 GPA" from "nothing to compute"."""
    total_credits = 0.0
    weighted_sum = 0.0
    for course in courses or []:
        try:
            credits = float(course.get('credits') or 0)
            grade = float(course.get('grade') or 0)
        except (TypeError, ValueError):
            continue
        if credits <= 0:
            continue
        total_credits += credits
        weighted_sum += credits * grade
    if total_credits <= 0:
        return None
    return round(weighted_sum / total_credits, 3)
