import os
from contextlib import contextmanager
from datetime import date, datetime

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Json
except ImportError:  # Local SQLite-only development can run before pip install.
    psycopg = None
    dict_row = None
    Json = None

from config import Config


def database_url():
    return os.getenv("DATABASE_URL") or getattr(Config, "DATABASE_URL", "")


def enabled():
    return bool(database_url())


def schema_path():
    here = os.path.abspath(__file__)
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here)))), "database", "postgres_schema.sql"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(here))), "database", "postgres_schema.sql"),
        os.path.join(os.getcwd(), "database", "postgres_schema.sql"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[0]


def initialize_schema():
    """Create the shared PostgreSQL schema when DATABASE_URL is configured."""
    if not enabled():
        return False
    path = schema_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"PostgreSQL schema not found: {path}")
    with open(path, encoding="utf-8") as schema_file:
        schema_sql = schema_file.read()
    with connection() as conn:
        conn.execute(schema_sql)
    return True


@contextmanager
def connection():
    if psycopg is None:
        raise RuntimeError("psycopg is required when DATABASE_URL is configured")
    conn = psycopg.connect(database_url(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def user_id_from_db_path(db_path):
    if not db_path:
        return "default"
    name = os.path.splitext(os.path.basename(str(db_path)))[0]
    return name or "default"


def ensure_user(user_id, name="Teacher", email=""):
    user_id = user_id or "default"
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO users (user_id, name, email)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET user_id = EXCLUDED.user_id
            RETURNING *
            """,
            (user_id, name, email),
        ).fetchone()
        return normalize_row(row)


def json_value(value):
    return Json(value)


def normalize_row(row):
    if not row:
        return None
    result = {}
    for key, value in dict(row).items():
        if isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def normalize_rows(rows):
    return [normalize_row(row) for row in rows or []]
