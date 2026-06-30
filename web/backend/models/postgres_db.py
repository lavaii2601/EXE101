import os
import sys
from contextlib import contextmanager
from datetime import date, datetime

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # Local SQLite-only development can run before pip install.
    psycopg = None
    dict_row = None
    Jsonb = None

try:
    from psycopg_pool import ConnectionPool
except ImportError:
    ConnectionPool = None

from config import Config

_pool = None
_pool_url = None


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
    pool = _connection_pool()
    if pool:
        conn_ctx = pool.connection()
    else:
        conn_ctx = psycopg.connect(database_url(), row_factory=dict_row)
    conn = conn_ctx.__enter__()
    exc_info = (None, None, None)
    try:
        yield conn
        conn.commit()
    except Exception:
        exc_info = sys.exc_info()
        conn.rollback()
        raise
    finally:
        conn_ctx.__exit__(*exc_info)


def _connection_pool():
    """Reuse PostgreSQL connections on Railway instead of reconnecting per query."""
    global _pool, _pool_url
    if ConnectionPool is None:
        return None
    url = database_url()
    if not url:
        return None
    if _pool is None or _pool_url != url:
        _pool_url = url
        _pool = ConnectionPool(
            conninfo=url,
            min_size=int(os.getenv("POSTGRES_POOL_MIN", "1")),
            max_size=int(os.getenv("POSTGRES_POOL_MAX", "8")),
            kwargs={"row_factory": dict_row},
        )
    return _pool


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
    # Every JSON-ish column in the shared schema is JSONB, not JSON -- using
    # psycopg's Json() adapter (plain `json` type) makes operators like
    # `jsonb || json` fail with "operator does not exist", since Postgres
    # doesn't implicitly cast between the two JSON types.
    return Jsonb(value)


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
