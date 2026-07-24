import hmac
import os
import sqlite3
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from config import Config
from models import postgres_db as pg
from models.knowledge import KnowledgeDocument
from models.user import User
from utils.security import authenticated_user_id
from utils.user_context import sanitize_user_id


admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')
_PROCESS_STARTED_AT = time.time()


def _admin_key_matches():
    configured = (Config.ADMIN_DASHBOARD_TOKEN or '').strip()
    provided = (request.headers.get('X-Admin-Key') or '').strip()
    return bool(configured and provided and hmac.compare_digest(configured, provided))


def _identity_values(user_id):
    user = User.get(user_id) or {}
    return {
        str(value or '').strip().lower()
        for value in (
            user_id,
            user.get('user_id'),
            user.get('email'),
            user.get('gmail_email'),
        )
        if str(value or '').strip()
    }


def _bootstrap_admin_values():
    if not Config.ADMIN_BOOTSTRAP_FIRST_USER:
        return set()

    if pg.enabled():
        with pg.connection() as conn:
            row = conn.execute(
                """
                SELECT user_id, email, gmail_email
                FROM users
                WHERE gmail_connected = TRUE
                ORDER BY gmail_connected_at NULLS LAST, created_at
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return set()
            return {
                str(value or '').strip().lower()
                for value in (row.get('user_id'), row.get('email'), row.get('gmail_email'))
                if str(value or '').strip()
            }

    User.init_db()
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT user_id, email, gmail_email
            FROM users
            WHERE gmail_connected = 1
            ORDER BY gmail_connected_at, created_at
            LIMIT 1
            """
        ).fetchone()
        return {
            str(value or '').strip().lower()
            for value in (dict(row).values() if row else [])
            if str(value or '').strip()
        }
    finally:
        conn.close()


def _authorize_admin():
    if _admin_key_matches():
        return {'identity': 'admin-key', 'mode': 'token'}

    raw_user_id = authenticated_user_id()
    if not raw_user_id:
        return None
    user_id = sanitize_user_id(raw_user_id)
    identity_values = _identity_values(user_id)

    if Config.ADMIN_EMAILS:
        if identity_values & Config.ADMIN_EMAILS:
            return {'identity': user_id, 'mode': 'email_allowlist'}
        return None

    bootstrap_values = _bootstrap_admin_values()
    if identity_values & bootstrap_values:
        return {'identity': user_id, 'mode': 'first_connected_user'}
    return None


def _postgres_dashboard():
    with pg.connection() as conn:
        summary = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM users) AS users_total,
                (SELECT COUNT(*) FROM users WHERE gmail_connected = TRUE) AS google_connected_users,
                (SELECT COUNT(*) FROM oauth_tokens WHERE revoked_at IS NULL) AS oauth_active,
                (SELECT COUNT(*) FROM oauth_tokens WHERE revoked_at IS NOT NULL) AS oauth_revoked,
                (SELECT COUNT(*) FROM oauth_tokens
                 WHERE revoked_at IS NULL AND expires_at IS NOT NULL AND expires_at < NOW()) AS oauth_access_expired,
                (SELECT COUNT(*) FROM oauth_tokens
                 WHERE revoked_at IS NULL
                   AND NOT (
                       scopes @> ARRAY['https://www.googleapis.com/auth/gmail.modify']::TEXT[]
                       AND scopes @> ARRAY['https://www.googleapis.com/auth/calendar.events']::TEXT[]
                   )) AS oauth_missing_scopes,
                (SELECT COUNT(*) FROM schedules) AS schedules_total,
                (SELECT COUNT(*) FROM schedules WHERE start_time >= NOW()) AS schedules_upcoming,
                (SELECT COUNT(*) FROM schedules WHERE calendar_event_id IS NOT NULL) AS schedules_synced,
                (SELECT COUNT(*) FROM schedules WHERE calendar_sync_error IS NOT NULL) AS schedules_sync_failed,
                (SELECT COUNT(*) FROM calendar_events) AS calendar_events_total,
                (SELECT COUNT(*) FROM calendar_events WHERE fetched_at >= NOW() - INTERVAL '24 hours') AS calendar_events_fetched_24h,
                (SELECT COUNT(*) FROM history) AS history_total,
                (SELECT COUNT(*) FROM history WHERE created_at >= NOW() - INTERVAL '24 hours') AS actions_24h,
                (SELECT COUNT(*) FROM chat_sessions WHERE archived_at IS NULL) AS chat_sessions_active,
                (SELECT COUNT(*) FROM meeting_suggestions WHERE status = 'pending') AS meeting_suggestions_pending,
                (SELECT COUNT(*) FROM knowledge_documents) AS knowledge_documents,
                (SELECT COUNT(*) FROM sync_jobs WHERE status = 'failed'
                    AND created_at >= NOW() - INTERVAL '24 hours') AS sync_failures_24h,
                (SELECT COUNT(*) FROM cache WHERE expires_at >= NOW()) AS cache_entries_active
            """
        ).fetchone()
        modes = conn.execute(
            """
            SELECT COALESCE(user_mode::TEXT, 'not_selected') AS label, COUNT(*) AS value
            FROM users
            GROUP BY COALESCE(user_mode::TEXT, 'not_selected')
            ORDER BY value DESC
            """
        ).fetchall()
        activity = conn.execute(
            """
            SELECT day::DATE::TEXT AS day, COALESCE(counts.value, 0) AS value
            FROM generate_series(
                CURRENT_DATE - INTERVAL '13 days',
                CURRENT_DATE,
                INTERVAL '1 day'
            ) AS day
            LEFT JOIN (
                SELECT created_at::DATE AS activity_day, COUNT(*) AS value
                FROM history
                WHERE created_at >= CURRENT_DATE - INTERVAL '13 days'
                GROUP BY created_at::DATE
            ) AS counts ON counts.activity_day = day::DATE
            ORDER BY day
            """
        ).fetchall()
        sync_jobs = conn.execute(
            """
            SELECT id, user_id, job_type, status, started_at, finished_at,
                   error_message, created_at
            FROM sync_jobs
            ORDER BY created_at DESC
            LIMIT 20
            """
        ).fetchall()
        recent_users = conn.execute(
            """
            SELECT user_id, name, email, gmail_email, gmail_connected,
                   user_mode::TEXT AS user_mode, created_at, updated_at
            FROM users
            ORDER BY updated_at DESC
            LIMIT 20
            """
        ).fetchall()
        table_sizes = conn.execute(
            """
            SELECT relname AS table_name,
                   pg_total_relation_size(relid) AS bytes
            FROM pg_catalog.pg_statio_user_tables
            ORDER BY pg_total_relation_size(relid) DESC
            LIMIT 12
            """
        ).fetchall()
        database = conn.execute(
            """
            SELECT current_database() AS name,
                   pg_database_size(current_database()) AS bytes,
                   NOW() AS server_time
            """
        ).fetchone()

    return {
        'summary': pg.normalize_row(summary),
        'users_by_mode': pg.normalize_rows(modes),
        'activity_14d': pg.normalize_rows(activity),
        'recent_sync_jobs': pg.normalize_rows(sync_jobs),
        'recent_users': pg.normalize_rows(recent_users),
        'table_sizes': pg.normalize_rows(table_sizes),
        'database': pg.normalize_row(database),
    }


def _sqlite_dashboard():
    User.init_db()
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        users_total = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        connected = conn.execute(
            'SELECT COUNT(*) FROM users WHERE gmail_connected = 1'
        ).fetchone()[0]
        recent_users = [
            dict(row)
            for row in conn.execute(
                """
                SELECT user_id, name, email, gmail_email, gmail_connected,
                       user_mode, created_at, updated_at
                FROM users ORDER BY updated_at DESC LIMIT 20
                """
            ).fetchall()
        ]
    finally:
        conn.close()
    return {
        'summary': {
            'users_total': users_total,
            'google_connected_users': connected,
            'knowledge_documents': KnowledgeDocument.count(),
        },
        'users_by_mode': [],
        'activity_14d': [],
        'recent_sync_jobs': [],
        'recent_users': recent_users,
        'table_sizes': [],
        'database': {
            'name': os.path.basename(Config.DATABASE_PATH),
            'bytes': os.path.getsize(Config.DATABASE_PATH) if os.path.exists(Config.DATABASE_PATH) else 0,
            'server_time': datetime.now(timezone.utc).isoformat(),
        },
    }


@admin_bp.route('/overview', methods=['GET'])
def admin_overview():
    admin = _authorize_admin()
    if not admin:
        return jsonify({
            'error': 'admin_auth_required',
            'message': 'Đăng nhập bằng tài khoản quản trị hoặc nhập khóa quản trị.',
        }), 401

    payload = _postgres_dashboard() if pg.enabled() else _sqlite_dashboard()
    return jsonify({
        'success': True,
        'admin': admin,
        'backend': 'postgres' if pg.enabled() else 'sqlite',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'process_uptime_seconds': int(time.time() - _PROCESS_STARTED_AT),
        **payload,
    })
