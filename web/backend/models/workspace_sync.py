import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg


WORKSPACE_SYNC_DOMAINS = (
    "chat",
    "history",
    "email",
    "schedule",
    "calendar",
    "overview",
    "profile",
    "settings",
    "knowledge",
    "providers",
)
_DOMAIN_SET = frozenset(WORKSPACE_SYNC_DOMAINS)


def _empty_domains():
    return {domain: 0 for domain in WORKSPACE_SYNC_DOMAINS}


def _normalize_domains(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            value = {}
    if not isinstance(value, dict):
        value = {}

    normalized = _empty_domains()
    for domain in WORKSPACE_SYNC_DOMAINS:
        try:
            normalized[domain] = max(0, int(value.get(domain) or 0))
        except (TypeError, ValueError):
            normalized[domain] = 0
    return normalized


def _normalize_requested_domains(domains):
    requested = set()
    for value in domains or ():
        domain = str(value or "").strip().lower()
        if domain in _DOMAIN_SET:
            requested.add(domain)
    return tuple(domain for domain in WORKSPACE_SYNC_DOMAINS if domain in requested)


def _require_user_id(user_id):
    value = str(user_id or "").strip()
    if not value:
        raise ValueError("user_id is required for workspace sync state")
    return value


class WorkspaceSync:
    """Per-user revision cursor used to invalidate web/mobile workspace views."""

    _initialized_dbs = set()

    @staticmethod
    def init_db(db_path=None):
        if pg.enabled():
            # PostgreSQL is initialized from database/postgres_schema.sql.
            return True

        db_path = os.path.abspath(db_path or Config.DATABASE_PATH)
        if db_path in WorkspaceSync._initialized_dbs and os.path.exists(db_path):
            return True

        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workspace_sync_state (
                    user_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
                    domains TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workspace_sync_state_updated
                ON workspace_sync_state(updated_at)
                """
            )
            conn.commit()
        finally:
            conn.close()
        WorkspaceSync._initialized_dbs.add(db_path)
        return True

    @staticmethod
    def get_state(user_id, db_path=None):
        user_id = _require_user_id(user_id)
        if pg.enabled():
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    SELECT revision, domains
                    FROM workspace_sync_state
                    WHERE user_id = %s
                    """,
                    (user_id,),
                ).fetchone()
        else:
            db_path = os.path.abspath(db_path or Config.DATABASE_PATH)
            WorkspaceSync.init_db(db_path)
            conn = sqlite3.connect(db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    """
                    SELECT revision, domains
                    FROM workspace_sync_state
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchone()
            finally:
                conn.close()

        if not row:
            return {"revision": 0, "domains": _empty_domains()}
        return {
            "revision": max(0, int(row["revision"] or 0)),
            "domains": _normalize_domains(row["domains"]),
        }

    @staticmethod
    def bump(user_id, domains, db_path=None):
        """Atomically advance one user's cursor and affected domain revisions."""
        user_id = _require_user_id(user_id)
        requested = _normalize_requested_domains(domains)
        if not requested:
            return WorkspaceSync.get_state(user_id, db_path=db_path)

        if pg.enabled():
            pg.ensure_user(user_id)
            with pg.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO workspace_sync_state (user_id, revision, domains)
                    VALUES (%s, 0, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (user_id, pg.json_value({})),
                )
                row = conn.execute(
                    """
                    SELECT revision, domains
                    FROM workspace_sync_state
                    WHERE user_id = %s
                    FOR UPDATE
                    """,
                    (user_id,),
                ).fetchone()
                current_revision = max(0, int(row["revision"] or 0))
                next_revision = current_revision + 1
                next_domains = _normalize_domains(row["domains"])
                for domain in requested:
                    next_domains[domain] = next_revision
                conn.execute(
                    """
                    UPDATE workspace_sync_state
                    SET revision = %s, domains = %s, updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (next_revision, pg.json_value(next_domains), user_id),
                )
            return {"revision": next_revision, "domains": next_domains}

        db_path = os.path.abspath(db_path or Config.DATABASE_PATH)
        WorkspaceSync.init_db(db_path)
        conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            # BEGIN IMMEDIATE serializes competing writers before either reads
            # the current revision, preserving a gap-free monotonic cursor.
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT OR IGNORE INTO workspace_sync_state (
                    user_id, revision, domains, updated_at
                )
                VALUES (?, 0, '{}', ?)
                """,
                (user_id, datetime.now(timezone.utc).isoformat()),
            )
            row = conn.execute(
                """
                SELECT revision, domains
                FROM workspace_sync_state
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            current_revision = max(0, int(row["revision"] or 0))
            next_revision = current_revision + 1
            next_domains = _normalize_domains(row["domains"])
            for domain in requested:
                next_domains[domain] = next_revision
            conn.execute(
                """
                UPDATE workspace_sync_state
                SET revision = ?, domains = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (
                    next_revision,
                    json.dumps(next_domains, separators=(",", ":"), sort_keys=True),
                    datetime.now(timezone.utc).isoformat(),
                    user_id,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return {"revision": next_revision, "domains": next_domains}
