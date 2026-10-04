import base64
import binascii
import hmac
import os
import re
import sqlite3
import struct
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from hashlib import sha1

from flask import Blueprint, jsonify, request, session

from config import Config
from models import admin_totp
from models import postgres_db as pg
from models.knowledge import KnowledgeDocument
from models.user import User
from models import subscription as subscription_model
from models import workspace as workspace_model
from models import workspace_subscription
from models import admin_ops
from models.workspace_sync import WorkspaceSync
from utils.security import authenticated_user_id
from utils.user_context import sanitize_user_id


admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')
_PROCESS_STARTED_AT = time.time()
_totp_attempts = defaultdict(deque)
_totp_attempts_lock = threading.Lock()
# Last RFC 6238 time-step counter successfully consumed per admin user_id --
# _verify_totp's +-1 step window means a captured, still-valid code could
# otherwise be replayed for up to ~90s. Consuming a counter once makes a
# second submission of the identical code fail even inside that window.
_totp_consumed_counters = {}
_totp_consumed_lock = threading.Lock()
# Both dicts above only work correctly with Railway's current single
# gunicorn worker (railpack.json's --workers 1): a second worker process
# gets its own separate copy, so attempt throttling and TOTP-replay
# protection would silently stop being enforced across the whole account,
# not just within one process, with no error to notice it. See RAILWAY.md's
# "Do not raise --workers above 1 without adding Redis first".


def _decode_totp_secret(secret):
    normalized = re.sub(r'[\s-]+', '', str(secret or '')).upper()
    if not normalized:
        raise ValueError('ADMIN_TOTP_SECRET is not configured')
    padding = '=' * ((8 - len(normalized) % 8) % 8)
    try:
        decoded = base64.b32decode(normalized + padding, casefold=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError('ADMIN_TOTP_SECRET must be valid Base32') from exc
    if len(decoded) < 20:
        raise ValueError('ADMIN_TOTP_SECRET must contain at least 160 bits')
    return decoded


def _totp_at(secret, timestamp=None, digits=6, period=30):
    """Return an RFC 6238 HMAC-SHA1 TOTP code for one timestamp."""
    timestamp = time.time() if timestamp is None else float(timestamp)
    counter = int(timestamp // period)
    digest = hmac.new(
        _decode_totp_secret(secret),
        struct.pack('>Q', counter),
        sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    binary = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    return str(binary % (10 ** digits)).zfill(digits)


def _verify_totp(code, secret, timestamp=None, window=1):
    """Return the matched RFC 6238 time-step counter, or None if `code`
    doesn't match any step in the +-window. (Not a plain bool: the matched
    counter is what _consume_totp_counter needs to detect a replay of the
    same code within its still-valid window.)"""
    code = str(code or '').strip()
    if not re.fullmatch(r'\d{6}', code):
        return None
    now = time.time() if timestamp is None else float(timestamp)
    for offset in range(-window, window + 1):
        candidate_time = now + offset * 30
        if hmac.compare_digest(code, _totp_at(secret, candidate_time)):
            return int(candidate_time // 30)
    return None


def _consume_totp_counter(user_id, counter):
    """True the first time this (user, time-step) pair is seen; False if
    that exact code has already been used once (a replay), even though
    it's still inside _verify_totp's valid window."""
    with _totp_consumed_lock:
        if _totp_consumed_counters.get(user_id) == counter:
            return False
        _totp_consumed_counters[user_id] = counter
        return True


def _trusted_admin_email(user_id):
    """Return this FlowMate account's own registered email.

    Covers both Google-linked accounts (oauth2callback/google_auth_native
    always mirror gmail_email into this same `email` column) and local
    email/password accounts uniformly. Trusting this column for the admin
    allowlist check relies on the write paths -- /api/auth/register and
    POST /api/user/profile -- refusing to let anyone self-assign an
    ADMIN_EMAILS address that isn't verifiably theirs; see the
    `email_reserved` guards in routes/auth.py and routes/user.py.
    """
    user = User.get(user_id) or {}
    return str(user.get('email') or '').strip().lower()


def is_current_user_admin():
    """Return whether the signed-in account's email is allowlisted.

    This is deliberately only a role check. Opening the dashboard still
    requires the independent TOTP gate enforced by ``_require_admin``.
    """
    raw_user_id = authenticated_user_id()
    if not raw_user_id or not Config.ADMIN_EMAILS:
        return False
    user_id = sanitize_user_id(raw_user_id)
    account = User.get(user_id) or {}
    if str(account.get('account_status') or 'active').lower() != 'active':
        return None, (
            jsonify({'error': 'admin_account_inactive', 'message': 'Tài khoản quản trị đang bị khóa.'}),
            403,
        )
    admin_email = _trusted_admin_email(user_id)
    return bool(admin_email and admin_email in Config.ADMIN_EMAILS)


def _configuration_error():
    if not Config.ADMIN_EMAILS:
        return 'ADMIN_EMAILS is not configured'
    return None


def _resolve_admin_totp_secret(email):
    """Return the TOTP secret that should validate `email`'s codes.

    Prefers a personal secret (models.admin_totp); falls back to the
    legacy secret shared by every admin so nothing breaks for an admin
    who hasn't been migrated to a personal one yet (see
    scripts/manage_admin_totp.py).
    """
    personal_secret = admin_totp.get_secret(email)
    if personal_secret:
        return personal_secret
    if Config.ADMIN_TOTP_SECRET:
        return Config.ADMIN_TOTP_SECRET
    raise ValueError('No TOTP secret is configured for this admin')


def _google_admin_identity():
    config_error = _configuration_error()
    if config_error:
        return None, (
            jsonify({
                'error': 'admin_not_configured',
                'message': 'Dashboard admin đang khóa vì server chưa cấu hình allowlist và TOTP.',
            }),
            503,
        )

    raw_user_id = authenticated_user_id()
    if not raw_user_id:
        return None, (
            jsonify({
                'error': 'admin_google_login_required',
                'message': 'Đăng nhập Google bằng tài khoản quản trị để tiếp tục.',
            }),
            401,
        )

    user_id = sanitize_user_id(raw_user_id)
    admin_email = _trusted_admin_email(user_id)
    if not admin_email or admin_email not in Config.ADMIN_EMAILS:
        return None, (
            jsonify({
                'error': 'admin_not_allowed',
                'message': 'Tài khoản này không có quyền quản trị.',
            }),
            403,
        )
    return user_id, None


def _totp_session_valid(user_id):
    verified_at = session.get('admin_totp_verified_at')
    verified_user = session.get('admin_totp_user')
    try:
        age = time.time() - float(verified_at)
    except (TypeError, ValueError):
        return False
    return (
        verified_user == user_id
        and 0 <= age <= max(60, Config.ADMIN_TOTP_SESSION_SECONDS)
    )


def _require_admin():
    user_id, error_response = _google_admin_identity()
    if error_response:
        return None, error_response
    if not _totp_session_valid(user_id):
        return None, (
            jsonify({
                'error': 'admin_totp_required',
                'message': 'Nhập mã 6 số từ ứng dụng Authenticator.',
                'totp_period_seconds': 30,
            }),
            403,
        )
    return {'identity': user_id, 'mode': 'google_allowlist_totp'}, None


def _admin_actor_id(admin):
    """Normalize the authenticated admin payload for routes and test doubles."""
    if isinstance(admin, dict):
        return admin.get('identity')
    return str(admin or '')


def _attempt_key(user_id):
    # request.remote_addr (not a raw X-Forwarded-For read) -- app.py's
    # ProxyFix(x_for=1) already resolves the one trusted Railway edge hop
    # into this value. Re-parsing the header directly here used to take its
    # client-supplied leftmost entry instead, letting an attacker pick a
    # fresh, unthrottled bucket on every request and bypass the TOTP
    # brute-force cap entirely.
    return user_id, request.remote_addr or 'unknown'


def _consume_totp_attempt(user_id):
    now = time.monotonic()
    window = max(60, Config.ADMIN_TOTP_ATTEMPT_WINDOW_SECONDS)
    max_attempts = max(1, Config.ADMIN_TOTP_MAX_ATTEMPTS)
    key = _attempt_key(user_id)
    with _totp_attempts_lock:
        bucket = _totp_attempts[key]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= max_attempts:
            retry_after = max(1, int(window - (now - bucket[0])))
            return False, retry_after
        bucket.append(now)
    return True, 0


def _clear_totp_attempts(user_id):
    key = _attempt_key(user_id)
    with _totp_attempts_lock:
        _totp_attempts.pop(key, None)


def _workspace_access_alert_counts(conn=None):
    """Phase 6 operational alerts: access_state has no pure-SQL equivalent
    (it's computed live by workspace_subscription.get_access_state), so
    reuse the exact same decorated rows Stage A's lifecycle scheduler reads
    from -- this can never silently disagree with what the scheduler /
    assert_writable actually enforce. Extracted as its own function so it's
    testable without scripting every unrelated query _postgres_dashboard
    also runs.

    Pass the connection _postgres_dashboard already has open so this reuses
    that round trip instead of opening a second one."""
    workspaces_in_grace = 0
    workspaces_read_only = 0
    for row in workspace_subscription.list_all_with_owner(conn=conn):
        state = row.get('access_state')
        if state == workspace_subscription.ACCESS_GRACE:
            workspaces_in_grace += 1
        elif state == workspace_subscription.ACCESS_READ_ONLY:
            workspaces_read_only += 1
    return {
        'workspaces_in_grace': workspaces_in_grace,
        'workspaces_read_only': workspaces_read_only,
    }


def _postgres_dashboard():
    with pg.connection() as conn:
        summary = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM users) AS users_total,
                (SELECT COUNT(*) FROM users WHERE last_active_at >= CURRENT_DATE) AS users_active_today,
                (SELECT COUNT(*) FROM users WHERE last_active_at >= DATE_TRUNC('month', NOW())) AS users_active_month,
                (SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE) AS users_new_today,
                (SELECT COUNT(*) FROM users WHERE created_at >= DATE_TRUNC('month', NOW())) AS users_new_month,
                (SELECT COUNT(*) FROM users u WHERE NOT EXISTS (
                    SELECT 1 FROM subscriptions s WHERE s.user_id = u.user_id
                    AND s.status IN ('trialing', 'active')
                    AND (s.current_period_end IS NULL OR s.current_period_end > NOW())
                )) AS users_free,
                (SELECT COUNT(DISTINCT user_id) FROM subscriptions
                 WHERE user_id IS NOT NULL AND status IN ('trialing', 'active')
                 AND (current_period_end IS NULL OR current_period_end > NOW())) AS users_plus,
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
                (SELECT COUNT(*) FROM cache WHERE expires_at >= NOW()) AS cache_entries_active,
                (SELECT COUNT(*) FROM payment_transactions WHERE status = 'failed'
                    AND created_at >= NOW() - INTERVAL '24 hours') AS failed_payments_24h,
                (SELECT COALESCE(SUM(gross_amount - fee_amount - refund_amount), 0)
                 FROM payment_transactions WHERE status IN ('paid', 'partially_refunded')
                 AND currency = 'VND'
                 AND paid_at >= DATE_TRUNC('month', NOW())) AS revenue_month,
                (SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM ai_cost_log
                 WHERE created_at >= DATE_TRUNC('month', NOW())) AS ai_cost_month_usd,
                (SELECT COUNT(*) FROM ai_cost_log
                 WHERE created_at >= DATE_TRUNC('month', NOW())) AS ai_requests_month,
                (SELECT COUNT(*) FROM ai_cost_log WHERE success = FALSE
                 AND created_at >= DATE_TRUNC('month', NOW())) AS ai_errors_month
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
        user_growth = conn.execute(
            """
            SELECT day::DATE::TEXT AS day, COALESCE(counts.value, 0) AS value
            FROM generate_series(CURRENT_DATE - INTERVAL '29 days', CURRENT_DATE, INTERVAL '1 day') day
            LEFT JOIN (
                SELECT created_at::DATE AS created_day, COUNT(*) AS value
                FROM users WHERE created_at >= CURRENT_DATE - INTERVAL '29 days'
                GROUP BY created_at::DATE
            ) counts ON counts.created_day = day::DATE
            ORDER BY day
            """
        ).fetchall()
        revenue_daily = conn.execute(
            """
            SELECT paid_at::DATE::TEXT AS day, currency,
                   SUM(gross_amount - fee_amount - refund_amount) AS value
            FROM payment_transactions
            WHERE status IN ('paid', 'partially_refunded')
              AND paid_at >= CURRENT_DATE - INTERVAL '29 days'
            GROUP BY paid_at::DATE, currency ORDER BY paid_at::DATE
            """
        ).fetchall()
        ai_cost_daily = conn.execute(
            """
            SELECT day::DATE::TEXT AS day,
                   COALESCE(cost.value, 0) AS value,
                   COALESCE(cost.requests, 0) AS requests
            FROM generate_series(CURRENT_DATE - INTERVAL '29 days', CURRENT_DATE, INTERVAL '1 day') day
            LEFT JOIN (
                SELECT created_at::DATE AS cost_day,
                       SUM(COALESCE(estimated_cost_usd, 0)) AS value,
                       COUNT(*) AS requests
                FROM ai_cost_log WHERE created_at >= CURRENT_DATE - INTERVAL '29 days'
                GROUP BY created_at::DATE
            ) cost ON cost.cost_day = day::DATE
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
            SELECT u.user_id, u.name, u.email, u.gmail_email, u.gmail_connected,
                   u.user_mode::TEXT AS user_mode, u.created_at, u.updated_at,
                   sub.plan_code AS subscription_plan_code,
                   sub.plan_name AS subscription_plan_name,
                   sub.billing_interval AS subscription_billing_interval,
                   sub.current_period_end AS subscription_current_period_end,
                   sub.remaining_seconds AS subscription_remaining_seconds
            FROM users u
            LEFT JOIN LATERAL (
                SELECT
                    plan_code,
                    plan_name,
                    billing_interval,
                    current_period_end,
                    CASE
                        WHEN current_period_end IS NULL THEN NULL
                        ELSE GREATEST(
                            0,
                            FLOOR(EXTRACT(EPOCH FROM (current_period_end - NOW())))
                        )::BIGINT
                    END AS remaining_seconds
                FROM subscriptions
                WHERE subscriptions.user_id = u.user_id
                  AND status IN ('trialing', 'active')
                  AND (current_period_end IS NULL OR current_period_end > NOW())
                ORDER BY current_period_end DESC NULLS LAST
                LIMIT 1
            ) sub ON TRUE
            ORDER BY u.updated_at DESC
            LIMIT 200
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
        alert_counts = _workspace_access_alert_counts(conn=conn)

    summary_row = pg.normalize_row(summary)
    summary_row.update(alert_counts)

    return {
        'summary': summary_row,
        'users_by_mode': pg.normalize_rows(modes),
        'activity_14d': pg.normalize_rows(activity),
        'user_growth_30d': pg.normalize_rows(user_growth),
        'revenue_30d': pg.normalize_rows(revenue_daily),
        'ai_cost_30d': pg.normalize_rows(ai_cost_daily),
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
        'user_growth_30d': [],
        'revenue_30d': [],
        'ai_cost_30d': [],
        'recent_sync_jobs': [],
        'recent_users': recent_users,
        'table_sizes': [],
        'database': {
            'name': os.path.basename(Config.DATABASE_PATH),
            'bytes': os.path.getsize(Config.DATABASE_PATH) if os.path.exists(Config.DATABASE_PATH) else 0,
            'server_time': datetime.now(timezone.utc).isoformat(),
        },
    }


def _empty_finance():
    return {
        'has_data': False,
        'currencies': [{
            'currency': 'VND',
            'gross_revenue_month': 0,
            'revenue_today': 0,
            'fees_month': 0,
            'refunds_month': 0,
            'net_revenue_month': 0,
            'payments_month': 0,
            'active_subscriptions': 0,
            'trialing_subscriptions': 0,
            'past_due_subscriptions': 0,
            'new_subscriptions_month': 0,
            'canceled_subscriptions_month': 0,
            'mrr': 0,
            'total_subscriptions': 0,
            'total_transactions': 0,
            'failed_payments': 0,
        }],
        'revenue_12m': [],
        'subscriptions_by_plan': [],
        'recent_payments': [],
        'recent_subscriptions': [],
        'audience': {
            'free_users': 0, 'plus_users': 0, 'monthly_subscriptions': 0,
            'annual_subscriptions': 0, 'conversion_rate': 0, 'churn_rate': 0,
        },
        'money_unit': 'minor',
        'reporting_timezone': 'Asia/Ho_Chi_Minh',
    }


def _empty_workspace_dashboard():
    return {
        'summary': {
            'business_workspaces': 0,
            'active_workspaces': 0,
            'attention_workspaces': 0,
            'active_seats': 0,
            'seat_capacity': 0,
            'pending_seat_requests': 0,
        },
        'workspaces': [],
    }


def _postgres_workspace_dashboard():
    """Return one operational row per Business workspace without N+1 reads."""
    with pg.connection() as conn:
        rows = conn.execute(
            """
            SELECT
                workspace.id::TEXT AS workspace_id,
                workspace.name,
                workspace.slug,
                workspace.status AS workspace_status,
                workspace.owner_user_id,
                COALESCE(NULLIF(owner.gmail_email, ''), NULLIF(owner.email, ''), workspace.owner_user_id) AS owner,
                workspace.created_at,
                workspace.updated_at,
                COALESCE(members.active_seats, 0)::BIGINT AS active_seats,
                COALESCE(invitations.pending_invitations, 0)::BIGINT AS pending_invitations,
                COALESCE(seat_requests.pending_seat_requests, 0)::BIGINT AS pending_seat_requests,
                subscription.id AS subscription_id,
                subscription.plan_code,
                subscription.plan_name,
                subscription.status AS subscription_status,
                subscription.billing_interval,
                subscription.currency,
                subscription.unit_amount,
                subscription.current_period_start,
                subscription.current_period_end,
                subscription.grace_period_ends_at,
                subscription.included_seats,
                subscription.extra_seats,
                subscription.cancel_at_period_end
            FROM workspaces workspace
            LEFT JOIN users owner ON owner.user_id = workspace.owner_user_id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS active_seats
                FROM workspace_memberships
                WHERE workspace_id = workspace.id AND status = 'active'
            ) members ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS pending_invitations
                FROM workspace_invitations
                WHERE workspace_id = workspace.id
                  AND status IN ('pending', 'capacity_blocked')
            ) invitations ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS pending_seat_requests
                FROM workspace_seat_requests
                WHERE workspace_id = workspace.id
                  AND status IN ('pending_owner', 'payment_pending')
            ) seat_requests ON TRUE
            LEFT JOIN LATERAL (
                SELECT * FROM subscriptions
                WHERE workspace_id = workspace.id
                ORDER BY created_at DESC
                LIMIT 1
            ) subscription ON TRUE
            WHERE workspace.type = 'business'
            ORDER BY workspace.updated_at DESC
            """
        ).fetchall()

    workspaces = []
    for raw_row in pg.normalize_rows(rows):
        row = dict(raw_row)
        subscription = None
        if row.get('subscription_id') is not None:
            subscription = {
                'status': row.get('subscription_status'),
                'current_period_end': row.get('current_period_end'),
                'grace_period_ends_at': row.get('grace_period_ends_at'),
            }
        row['access_state'] = workspace_subscription.get_access_state(subscription)
        row['seat_capacity'] = (
            int(row.get('included_seats') or 0) + int(row.get('extra_seats') or 0)
            if subscription
            else workspace_subscription.DEFAULT_BUSINESS_INCLUDED_SEATS
        )
        workspaces.append(row)

    attention_states = {
        workspace_subscription.ACCESS_GRACE,
        workspace_subscription.ACCESS_READ_ONLY,
        workspace_subscription.ACCESS_NONE,
    }
    return {
        'summary': {
            'business_workspaces': len(workspaces),
            'active_workspaces': sum(row['access_state'] == workspace_subscription.ACCESS_ACTIVE for row in workspaces),
            'attention_workspaces': sum(row['access_state'] in attention_states for row in workspaces),
            'active_seats': sum(int(row.get('active_seats') or 0) for row in workspaces),
            'seat_capacity': sum(int(row.get('seat_capacity') or 0) for row in workspaces),
            'pending_seat_requests': sum(int(row.get('pending_seat_requests') or 0) for row in workspaces),
        },
        'workspaces': workspaces,
    }


def _postgres_finance():
    """Return provider-neutral finance metrics without combining currencies."""
    with pg.connection() as conn:
        currency_summary = conn.execute(
            """
            WITH currencies AS (
                SELECT 'VND'::TEXT AS currency
                UNION SELECT currency FROM subscriptions
                UNION SELECT currency FROM payment_transactions
            ),
            payment_stats AS (
                SELECT
                    currency,
                    COALESCE(SUM(gross_amount) FILTER (
                        WHERE status IN ('paid', 'partially_refunded', 'refunded')
                          AND paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
                              >= DATE_TRUNC('month', NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh')
                    ), 0)::BIGINT AS gross_revenue_month,
                    COALESCE(SUM(gross_amount - fee_amount - refund_amount) FILTER (
                        WHERE status IN ('paid', 'partially_refunded')
                          AND paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh' >= CURRENT_DATE
                    ), 0)::BIGINT AS revenue_today,
                    COALESCE(SUM(fee_amount) FILTER (
                        WHERE status IN ('paid', 'partially_refunded', 'refunded')
                          AND paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
                              >= DATE_TRUNC('month', NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh')
                    ), 0)::BIGINT AS fees_month,
                    COALESCE(SUM(refund_amount) FILTER (
                        WHERE refunded_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
                              >= DATE_TRUNC('month', NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh')
                    ), 0)::BIGINT AS refunds_month,
                    COUNT(*) FILTER (
                        WHERE status IN ('paid', 'partially_refunded', 'refunded')
                          AND paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
                              >= DATE_TRUNC('month', NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh')
                    ) AS payments_month,
                    COUNT(*) AS total_transactions,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed_payments
                FROM payment_transactions
                GROUP BY currency
            ),
            subscription_stats AS (
                SELECT
                    currency,
                    COUNT(*) FILTER (WHERE status = 'active') AS active_subscriptions,
                    COUNT(*) FILTER (WHERE status = 'trialing') AS trialing_subscriptions,
                    COUNT(*) FILTER (WHERE status = 'past_due') AS past_due_subscriptions,
                    COUNT(*) FILTER (
                        WHERE created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
                              >= DATE_TRUNC('month', NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh')
                    ) AS new_subscriptions_month,
                    COUNT(*) FILTER (
                        WHERE canceled_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
                              >= DATE_TRUNC('month', NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh')
                    ) AS canceled_subscriptions_month,
                    COALESCE(SUM(
                        CASE
                            WHEN status <> 'active' THEN 0
                            WHEN billing_interval = 'yearly' THEN unit_amount / 12
                            ELSE unit_amount
                        END
                    ), 0)::BIGINT AS mrr,
                    COUNT(*) AS total_subscriptions
                FROM subscriptions
                GROUP BY currency
            )
            SELECT
                currencies.currency,
                COALESCE(payment_stats.gross_revenue_month, 0)::BIGINT AS gross_revenue_month,
                COALESCE(payment_stats.revenue_today, 0)::BIGINT AS revenue_today,
                COALESCE(payment_stats.fees_month, 0)::BIGINT AS fees_month,
                COALESCE(payment_stats.refunds_month, 0)::BIGINT AS refunds_month,
                (
                    COALESCE(payment_stats.gross_revenue_month, 0)
                    - COALESCE(payment_stats.fees_month, 0)
                    - COALESCE(payment_stats.refunds_month, 0)
                )::BIGINT AS net_revenue_month,
                COALESCE(payment_stats.payments_month, 0)::BIGINT AS payments_month,
                COALESCE(subscription_stats.active_subscriptions, 0)::BIGINT AS active_subscriptions,
                COALESCE(subscription_stats.trialing_subscriptions, 0)::BIGINT AS trialing_subscriptions,
                COALESCE(subscription_stats.past_due_subscriptions, 0)::BIGINT AS past_due_subscriptions,
                COALESCE(subscription_stats.new_subscriptions_month, 0)::BIGINT AS new_subscriptions_month,
                COALESCE(subscription_stats.canceled_subscriptions_month, 0)::BIGINT AS canceled_subscriptions_month,
                COALESCE(subscription_stats.mrr, 0)::BIGINT AS mrr,
                COALESCE(subscription_stats.total_subscriptions, 0)::BIGINT AS total_subscriptions,
                COALESCE(payment_stats.total_transactions, 0)::BIGINT AS total_transactions,
                COALESCE(payment_stats.failed_payments, 0)::BIGINT AS failed_payments
            FROM currencies
            LEFT JOIN payment_stats USING (currency)
            LEFT JOIN subscription_stats USING (currency)
            ORDER BY
                CASE WHEN currencies.currency = 'VND' THEN 0 ELSE 1 END,
                currencies.currency
            """
        ).fetchall()

        revenue_12m = conn.execute(
            """
            WITH months AS (
                SELECT GENERATE_SERIES(
                    DATE_TRUNC('month', NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh') - INTERVAL '11 months',
                    DATE_TRUNC('month', NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh'),
                    INTERVAL '1 month'
                ) AS month
            ),
            currencies AS (
                SELECT 'VND'::TEXT AS currency
                UNION SELECT currency FROM subscriptions
                UNION SELECT currency FROM payment_transactions
            ),
            paid AS (
                SELECT
                    DATE_TRUNC('month', paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh') AS month,
                    currency,
                    SUM(gross_amount)::BIGINT AS gross,
                    SUM(fee_amount)::BIGINT AS fees,
                    COUNT(*) AS payments
                FROM payment_transactions
                WHERE status IN ('paid', 'partially_refunded', 'refunded')
                  AND paid_at >= NOW() - INTERVAL '13 months'
                GROUP BY 1, 2
            ),
            refunded AS (
                SELECT
                    DATE_TRUNC('month', refunded_at AT TIME ZONE 'Asia/Ho_Chi_Minh') AS month,
                    currency,
                    SUM(refund_amount)::BIGINT AS refunds
                FROM payment_transactions
                WHERE refunded_at IS NOT NULL
                  AND refunded_at >= NOW() - INTERVAL '13 months'
                GROUP BY 1, 2
            )
            SELECT
                TO_CHAR(months.month, 'YYYY-MM') AS month,
                currencies.currency,
                COALESCE(paid.gross, 0)::BIGINT AS gross,
                COALESCE(paid.fees, 0)::BIGINT AS fees,
                COALESCE(refunded.refunds, 0)::BIGINT AS refunds,
                (
                    COALESCE(paid.gross, 0)
                    - COALESCE(paid.fees, 0)
                    - COALESCE(refunded.refunds, 0)
                )::BIGINT AS net,
                COALESCE(paid.payments, 0)::BIGINT AS payments
            FROM months
            CROSS JOIN currencies
            LEFT JOIN paid
                ON paid.month = months.month
               AND paid.currency = currencies.currency
            LEFT JOIN refunded
                ON refunded.month = months.month
               AND refunded.currency = currencies.currency
            ORDER BY months.month, currencies.currency
            """
        ).fetchall()

        subscriptions_by_plan = conn.execute(
            """
            SELECT
                currency,
                plan_code,
                COALESCE(NULLIF(plan_name, ''), plan_code) AS label,
                COUNT(*) FILTER (WHERE status = 'active') AS active,
                COUNT(*) FILTER (WHERE status = 'trialing') AS trialing,
                COUNT(*) FILTER (WHERE status = 'past_due') AS past_due,
                COUNT(*) FILTER (WHERE status = 'canceled') AS canceled,
                COALESCE(SUM(
                    CASE
                        WHEN status <> 'active' THEN 0
                        WHEN billing_interval = 'yearly' THEN unit_amount / 12
                        ELSE unit_amount
                    END
                ), 0)::BIGINT AS mrr
            FROM subscriptions
            GROUP BY currency, plan_code, COALESCE(NULLIF(plan_name, ''), plan_code)
            ORDER BY active DESC, trialing DESC, label
            """
        ).fetchall()

        recent_payments = conn.execute(
            """
            SELECT
                payment.id,
                payment.provider,
                payment.provider_payment_id,
                payment.status,
                payment.currency,
                payment.gross_amount,
                payment.fee_amount,
                payment.refund_amount,
                (
                    payment.gross_amount
                    - payment.fee_amount
                    - payment.refund_amount
                )::BIGINT AS net_amount,
                payment.description,
                payment.paid_at,
                payment.refunded_at,
                payment.created_at,
                payment.user_id,
                COALESCE(
                    NULLIF(users.gmail_email, ''),
                    NULLIF(users.email, ''),
                    payment.user_id
                ) AS customer,
                subscription.plan_code,
                COALESCE(NULLIF(subscription.plan_name, ''), subscription.plan_code) AS plan_name
            FROM payment_transactions payment
            LEFT JOIN users ON users.user_id = payment.user_id
            LEFT JOIN subscriptions subscription ON subscription.id = payment.subscription_id
            ORDER BY COALESCE(payment.paid_at, payment.created_at) DESC
            LIMIT 30
            """
        ).fetchall()

        recent_subscriptions = conn.execute(
            """
            SELECT
                subscription.id,
                subscription.user_id,
                subscription.workspace_id::TEXT AS workspace_id,
                subscription.provider,
                subscription.plan_code,
                COALESCE(NULLIF(subscription.plan_name, ''), subscription.plan_code) AS plan_name,
                subscription.status,
                subscription.billing_interval,
                subscription.currency,
                subscription.unit_amount,
                subscription.current_period_end,
                CASE
                    WHEN subscription.current_period_end IS NULL THEN NULL
                    ELSE GREATEST(
                        0,
                        FLOOR(EXTRACT(EPOCH FROM (
                            subscription.current_period_end - NOW()
                        )))
                    )::BIGINT
                END AS remaining_seconds,
                subscription.cancel_at_period_end,
                subscription.created_at,
                COALESCE(
                    NULLIF(users.gmail_email, ''),
                    NULLIF(users.email, ''),
                    NULLIF(workspaces.name, ''),
                    subscription.user_id,
                    subscription.workspace_id::TEXT
                ) AS customer
            FROM subscriptions subscription
            LEFT JOIN users ON users.user_id = subscription.user_id
            LEFT JOIN workspaces ON workspaces.id = subscription.workspace_id
            ORDER BY subscription.updated_at DESC
            LIMIT 30
            """
        ).fetchall()
        audience = conn.execute(
            """
            WITH active_plus AS (
                SELECT DISTINCT user_id, billing_interval
                FROM subscriptions
                WHERE user_id IS NOT NULL AND status IN ('active', 'trialing')
                  AND (current_period_end IS NULL OR current_period_end > NOW())
            ), totals AS (
                SELECT COUNT(*)::NUMERIC AS users_total FROM users
            ), churn AS (
                SELECT COUNT(*) FILTER (WHERE canceled_at >= DATE_TRUNC('month', NOW()))::NUMERIC AS canceled,
                       COUNT(*) FILTER (WHERE status IN ('active', 'trialing'))::NUMERIC AS active
                FROM subscriptions WHERE user_id IS NOT NULL
            )
            SELECT totals.users_total - COUNT(DISTINCT active_plus.user_id) AS free_users,
                   COUNT(DISTINCT active_plus.user_id) AS plus_users,
                   COUNT(DISTINCT active_plus.user_id) FILTER (WHERE billing_interval = 'monthly') AS monthly_subscriptions,
                   COUNT(DISTINCT active_plus.user_id) FILTER (WHERE billing_interval = 'yearly') AS annual_subscriptions,
                   CASE WHEN totals.users_total > 0 THEN ROUND(COUNT(DISTINCT active_plus.user_id) * 100.0 / totals.users_total, 2) ELSE 0 END AS conversion_rate,
                   CASE WHEN churn.active + churn.canceled > 0 THEN ROUND(churn.canceled * 100.0 / (churn.active + churn.canceled), 2) ELSE 0 END AS churn_rate
            FROM totals CROSS JOIN churn
            LEFT JOIN active_plus ON TRUE
            GROUP BY totals.users_total, churn.active, churn.canceled
            """
        ).fetchone()

    normalized_currencies = pg.normalize_rows(currency_summary)
    has_data = any(
        int(row.get('total_subscriptions') or 0) > 0
        or int(row.get('total_transactions') or 0) > 0
        for row in normalized_currencies
    )
    return {
        'has_data': has_data,
        'currencies': normalized_currencies,
        'revenue_12m': pg.normalize_rows(revenue_12m),
        'subscriptions_by_plan': pg.normalize_rows(subscriptions_by_plan),
        'recent_payments': pg.normalize_rows(recent_payments),
        'recent_subscriptions': pg.normalize_rows(recent_subscriptions),
        'audience': pg.normalize_row(audience),
        'money_unit': 'minor',
        'reporting_timezone': 'Asia/Ho_Chi_Minh',
    }


def _postgres_admin_users(user_id=None):
    where = "WHERE u.user_id = %s" if user_id else ""
    params = (user_id,) if user_id else ()
    with pg.connection() as conn:
        rows = conn.execute(
            f"""
            SELECT u.user_id, u.name, u.email, u.gmail_email, u.gmail_connected,
                   u.user_mode::TEXT AS user_mode, u.account_status,
                   u.created_at, u.updated_at, u.last_login_at, u.last_active_at,
                   u.quota_reset_at,
                   COALESCE(oauth.calendar_connected, FALSE) AS calendar_connected,
                   sub.plan_code, sub.plan_name, sub.billing_interval,
                   sub.status AS subscription_status, sub.current_period_end,
                   COALESCE(usage.request_count, 0) AS ai_usage_month,
                   COALESCE(usage.cost_usd, 0) AS ai_cost_month_usd,
                   COALESCE(usage.input_tokens, 0) AS ai_input_tokens_month,
                   COALESCE(usage.output_tokens, 0) AS ai_output_tokens_month
            FROM users u
            LEFT JOIN LATERAL (
                SELECT plan_code, plan_name, billing_interval, status, current_period_end
                FROM subscriptions s
                WHERE s.user_id = u.user_id AND s.status IN ('trialing', 'active')
                  AND (s.current_period_end IS NULL OR s.current_period_end > NOW())
                ORDER BY s.current_period_end DESC NULLS LAST LIMIT 1
            ) sub ON TRUE
            LEFT JOIN LATERAL (
                SELECT BOOL_OR(
                    revoked_at IS NULL AND scopes @> ARRAY[
                        'https://www.googleapis.com/auth/calendar.events'
                    ]::TEXT[]
                ) AS calendar_connected
                FROM oauth_tokens ot WHERE ot.user_id = u.user_id
            ) oauth ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS request_count,
                       SUM(COALESCE(estimated_cost_usd, 0)) AS cost_usd,
                       SUM(COALESCE(input_tokens, 0)) AS input_tokens,
                       SUM(COALESCE(output_tokens, 0)) AS output_tokens
                FROM ai_cost_log cost
                WHERE cost.user_id = u.user_id
                  AND cost.created_at >= DATE_TRUNC('month', NOW())
            ) usage ON TRUE
            {where}
            ORDER BY COALESCE(u.last_active_at, u.updated_at) DESC
            LIMIT 1000
            """,
            params,
        ).fetchall()
    return pg.normalize_rows(rows)


def _postgres_ai_usage(days=30):
    with pg.connection() as conn:
        summary = conn.execute(
            """
            SELECT COUNT(*) AS requests,
                   SUM(COALESCE(input_tokens, 0)) AS input_tokens,
                   SUM(COALESCE(output_tokens, 0)) AS output_tokens,
                   SUM(COALESCE(estimated_cost_usd, 0)) AS cost_usd,
                   AVG(COALESCE(estimated_cost_usd, 0)) AS avg_cost_request_usd,
                   CASE WHEN COUNT(DISTINCT user_id) > 0
                        THEN SUM(COALESCE(estimated_cost_usd, 0)) / COUNT(DISTINCT user_id)
                        ELSE 0 END AS avg_cost_user_usd,
                   AVG(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)) AS avg_tokens_request,
                   AVG(latency_ms) AS avg_latency_ms,
                   COUNT(DISTINCT user_id) AS users,
                   COUNT(*) FILTER (WHERE cache_hit) AS cache_hits,
                   COUNT(*) FILTER (WHERE success) AS successes,
                   COUNT(*) FILTER (WHERE NOT success) AS errors
            FROM ai_cost_log WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
            """,
            (days,),
        ).fetchone()
        groups = {}
        for key, expression in (
            ('providers', 'provider'), ('models', "COALESCE(NULLIF(model, ''), 'unknown')"),
            ('tiers', 'tier'), ('features', 'task'),
        ):
            rows = conn.execute(
                f"""
                SELECT {expression} AS label, COUNT(*) AS requests,
                       SUM(COALESCE(input_tokens, 0)) AS input_tokens,
                       SUM(COALESCE(output_tokens, 0)) AS output_tokens,
                       SUM(COALESCE(estimated_cost_usd, 0)) AS cost_usd,
                       AVG(latency_ms) AS avg_latency_ms,
                       COUNT(*) FILTER (WHERE NOT success) AS errors
                FROM ai_cost_log WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
                GROUP BY {expression} ORDER BY cost_usd DESC, requests DESC
                """,
                (days,),
            ).fetchall()
            groups[key] = pg.normalize_rows(rows)
        daily = conn.execute(
            """
            SELECT day::DATE::TEXT AS day,
                   COALESCE(cost.requests, 0) AS requests,
                   COALESCE(cost.cost_usd, 0) AS cost_usd,
                   COALESCE(cost.input_tokens, 0) AS input_tokens,
                   COALESCE(cost.output_tokens, 0) AS output_tokens,
                   COALESCE(cost.errors, 0) AS errors
            FROM generate_series(CURRENT_DATE - ((%s - 1) * INTERVAL '1 day'), CURRENT_DATE, INTERVAL '1 day') day
            LEFT JOIN (
                SELECT created_at::DATE AS cost_day, COUNT(*) AS requests,
                       SUM(COALESCE(estimated_cost_usd, 0)) AS cost_usd,
                       SUM(COALESCE(input_tokens, 0)) AS input_tokens,
                       SUM(COALESCE(output_tokens, 0)) AS output_tokens,
                       COUNT(*) FILTER (WHERE NOT success) AS errors
                FROM ai_cost_log WHERE created_at >= CURRENT_DATE - ((%s - 1) * INTERVAL '1 day')
                GROUP BY created_at::DATE
            ) cost ON cost.cost_day = day::DATE ORDER BY day
            """,
            (days, days),
        ).fetchall()
        recent_errors = conn.execute(
            """
            SELECT created_at, user_id, task AS feature, provider, model,
                   error_type, latency_ms
            FROM ai_cost_log WHERE NOT success
              AND created_at >= NOW() - (%s * INTERVAL '1 day')
            ORDER BY created_at DESC LIMIT 100
            """,
            (days,),
        ).fetchall()
    return {
        'summary': pg.normalize_row(summary),
        'daily': pg.normalize_rows(daily),
        'recent_errors': pg.normalize_rows(recent_errors),
        **groups,
    }


def _postgres_integrations():
    with pg.connection() as conn:
        google = conn.execute(
            """
            SELECT
                COUNT(DISTINCT user_id) AS connected_users,
                COUNT(*) FILTER (WHERE revoked_at IS NULL) AS active_connections,
                COUNT(*) FILTER (WHERE revoked_at IS NOT NULL) AS revoked_access,
                COUNT(*) FILTER (WHERE revoked_at IS NULL AND expires_at < NOW()) AS expired_tokens,
                COUNT(*) FILTER (WHERE revoked_at IS NULL AND scopes @> ARRAY[
                    'https://www.googleapis.com/auth/gmail.modify']::TEXT[]) AS gmail_active,
                COUNT(*) FILTER (WHERE revoked_at IS NULL AND scopes @> ARRAY[
                    'https://www.googleapis.com/auth/calendar.events']::TEXT[]) AS calendar_active
            FROM oauth_tokens
            """
        ).fetchone()
        api_errors = conn.execute(
            """
            SELECT feature, COUNT(*) AS errors
            FROM operational_events
            WHERE event_type IN ('oauth_failure', 'api_error')
              AND created_at >= NOW() - INTERVAL '30 days'
              AND (feature ILIKE '%%email%%' OR feature ILIKE '%%calendar%%')
            GROUP BY feature ORDER BY errors DESC
            """
        ).fetchall()
        provider_metrics = conn.execute(
            """
            SELECT provider,
                   ROUND(AVG(latency_ms))::BIGINT AS avg_latency_ms,
                   COUNT(*) FILTER (WHERE error_type IN ('quota', 'rate_limit')) AS rate_limit_errors,
                   COUNT(*) AS requests
            FROM ai_cost_log
            WHERE created_at >= NOW() - INTERVAL '24 hours'
              AND provider IN ('openai', 'claude')
            GROUP BY provider
            """
        ).fetchall()
    return {
        'google': pg.normalize_row(google),
        'api_errors': pg.normalize_rows(api_errors),
        'provider_metrics': pg.normalize_rows(provider_metrics),
    }


def _postgres_system_health():
    with pg.connection() as conn:
        database = conn.execute("SELECT NOW() AS checked_at, current_database() AS name").fetchone()
        metrics = conn.execute(
            """
            SELECT SUM(request_count) AS requests, SUM(error_count) AS errors,
                   CASE WHEN SUM(request_count) > 0
                        THEN SUM(total_latency_ms)::NUMERIC / SUM(request_count) ELSE 0 END AS avg_latency_ms
            FROM api_metrics_daily WHERE metric_date >= CURRENT_DATE - INTERVAL '29 days'
            """
        ).fetchone()
        events = conn.execute(
            """
            SELECT * FROM (
                SELECT created_at, request_id, user_id, event_type, feature,
                       provider, model, status, latency_ms, error_message
                FROM operational_events
                UNION ALL
                SELECT created_at, NULL::TEXT AS request_id, user_id,
                       'ai_provider_error' AS event_type, task AS feature,
                       provider, model, 'error' AS status, latency_ms,
                       error_type AS error_message
                FROM ai_cost_log WHERE NOT success
            ) logs ORDER BY created_at DESC LIMIT 100
            """
        ).fetchall()
    return {
        'database': pg.normalize_row(database),
        'metrics': pg.normalize_row(metrics),
        'events': pg.normalize_rows(events),
    }


def _postgres_security():
    with pg.connection() as conn:
        counts = conn.execute(
            """
            SELECT event_type, COUNT(*) AS value
            FROM operational_events WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY event_type ORDER BY value DESC
            """
        ).fetchall()
        audits = conn.execute(
            """
            SELECT id, admin_user_id, action, target_type, target_id,
                   before_state, after_state, request_id, created_at
            FROM admin_audit_events ORDER BY created_at DESC LIMIT 100
            """
        ).fetchall()
        suspicious_ai = conn.execute(
            """
            SELECT user_id, COUNT(*) AS requests,
                   SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)) AS tokens,
                   SUM(COALESCE(estimated_cost_usd, 0)) AS cost_usd
            FROM ai_cost_log WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY user_id
            HAVING COUNT(*) >= 100 OR SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)) >= 100000
            ORDER BY cost_usd DESC LIMIT 50
            """
        ).fetchall()
        suspicious_logins = conn.execute(
            """
            SELECT metadata->>'client_fingerprint' AS client_fingerprint,
                   COUNT(*) AS failed_attempts,
                   MIN(created_at) AS first_attempt_at,
                   MAX(created_at) AS last_attempt_at
            FROM operational_events
            WHERE event_type = 'failed_login'
              AND created_at >= NOW() - INTERVAL '24 hours'
              AND COALESCE(metadata->>'client_fingerprint', '') <> ''
            GROUP BY metadata->>'client_fingerprint'
            HAVING COUNT(*) >= 5
            ORDER BY failed_attempts DESC LIMIT 50
            """
        ).fetchall()
    return {
        'event_counts': pg.normalize_rows(counts),
        'admin_audit': pg.normalize_rows(audits),
        'suspicious_ai_usage': pg.normalize_rows(suspicious_ai),
        'suspicious_logins': pg.normalize_rows(suspicious_logins),
    }


@admin_bp.route('/session', methods=['GET'])
def admin_session_status():
    user_id, error_response = _google_admin_identity()
    if error_response:
        return error_response
    if not _totp_session_valid(user_id):
        return jsonify({
            'success': True,
            'google_admin_verified': True,
            'totp_verified': False,
            'error': 'admin_totp_required',
        }), 403
    return jsonify({
        'success': True,
        'google_admin_verified': True,
        'totp_verified': True,
        'user_id': user_id,
    })


@admin_bp.route('/verify-totp', methods=['POST'])
def verify_admin_totp():
    user_id, error_response = _google_admin_identity()
    if error_response:
        return error_response

    allowed, retry_after = _consume_totp_attempt(user_id)
    if not allowed:
        response = jsonify({
            'error': 'admin_totp_rate_limited',
            'message': 'Quá nhiều lần nhập sai. Vui lòng thử lại sau.',
            'retry_after_seconds': retry_after,
        })
        response.headers['Retry-After'] = str(retry_after)
        return response, 429

    admin_email = _trusted_admin_email(user_id)
    try:
        secret = _resolve_admin_totp_secret(admin_email)
    except ValueError:
        return jsonify({
            'error': 'admin_totp_not_configured',
            'message': 'Chưa cấu hình TOTP cho tài khoản này. Liên hệ quản trị viên khác để được cấp mã.',
        }), 503

    code = (request.get_json(silent=True) or {}).get('code')
    counter = _verify_totp(code, secret)
    if counter is None or not _consume_totp_counter(user_id, counter):
        return jsonify({
            'error': 'admin_totp_invalid',
            'message': 'Mã Authenticator không đúng hoặc đã hết hạn.',
        }), 401

    session['admin_totp_user'] = user_id
    session['admin_totp_verified_at'] = int(time.time())
    session.modified = True
    _clear_totp_attempts(user_id)
    admin_ops.record_admin_audit(
        user_id, 'admin_login', 'admin_session', user_id,
        after={'totp_verified': True}, request_id=request.headers.get('X-Request-Id'),
    )
    return jsonify({
        'success': True,
        'totp_verified': True,
        'expires_in_seconds': Config.ADMIN_TOTP_SESSION_SECONDS,
    })


@admin_bp.route('/logout', methods=['POST'])
def admin_logout():
    session.pop('admin_totp_user', None)
    session.pop('admin_totp_verified_at', None)
    session.modified = True
    return jsonify({'success': True})


@admin_bp.route('/overview', methods=['GET'])
def admin_overview():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    payload = _postgres_dashboard() if pg.enabled() else _sqlite_dashboard()
    return jsonify({
        'success': True,
        'admin': admin,
        'backend': 'postgres' if pg.enabled() else 'sqlite',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'process_uptime_seconds': int(time.time() - _PROCESS_STARTED_AT),
        **payload,
    })


@admin_bp.route('/finance', methods=['GET'])
def admin_finance():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    finance = _postgres_finance() if pg.enabled() else _empty_finance()
    return jsonify({
        'success': True,
        'admin': admin,
        'backend': 'postgres' if pg.enabled() else 'sqlite',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'finance': finance,
    })


@admin_bp.route('/users', methods=['GET'])
def admin_users():
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    users = _postgres_admin_users() if pg.enabled() else _sqlite_dashboard()['recent_users']
    return jsonify({
        'success': True, 'admin': admin,
        'generated_at': datetime.now(timezone.utc).isoformat(), 'users': users,
    })


@admin_bp.route('/users/<user_id>', methods=['GET'])
def admin_user_detail(user_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    if not pg.enabled():
        user = User.get(user_id)
        return (jsonify({'success': True, 'admin': admin, 'user': user}) if user
                else (jsonify({'error': 'user_not_found'}), 404))
    rows = _postgres_admin_users(user_id=user_id)
    if not rows:
        return jsonify({'error': 'user_not_found'}), 404
    return jsonify({'success': True, 'admin': admin, 'user': rows[0]})


@admin_bp.route('/users/<user_id>/status', methods=['POST'])
def admin_update_user_status(user_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    if not pg.enabled():
        return jsonify({'error': 'account_status_requires_postgres'}), 400
    status = str((request.get_json(silent=True) or {}).get('status') or '').strip().lower()
    if status not in {'active', 'suspended', 'disabled'}:
        return jsonify({'error': 'invalid_account_status'}), 400
    if user_id == _admin_actor_id(admin) and status != 'active':
        return jsonify({'error': 'cannot_disable_current_admin'}), 409
    before = User.get(user_id)
    if not before:
        return jsonify({'error': 'user_not_found'}), 404
    with pg.connection() as conn:
        row = conn.execute(
            """
            UPDATE users SET account_status = %s,
                token_version = token_version + CASE WHEN %s = 'active' THEN 0 ELSE 1 END,
                updated_at = NOW()
            WHERE user_id = %s RETURNING *
            """,
            (status, status, user_id),
        ).fetchone()
    after = pg.normalize_row(row)
    admin_ops.record_admin_audit(
        _admin_actor_id(admin), f'user_{status}', 'user', user_id,
        before={'account_status': before.get('account_status', 'active')},
        after={'account_status': status},
        request_id=getattr(request, 'request_id', None) or request.headers.get('X-Request-Id'),
    )
    return jsonify({'success': True, 'admin': admin, 'user': after})


@admin_bp.route('/users/<user_id>/usage/reset', methods=['POST'])
def admin_reset_user_usage(user_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    if not pg.enabled():
        return jsonify({'error': 'usage_reset_requires_postgres'}), 400
    scope = str((request.get_json(silent=True) or {}).get('scope') or 'today').lower()
    if scope not in {'today', 'all'}:
        return jsonify({'error': 'invalid_reset_scope'}), 400
    if not User.get(user_id):
        return jsonify({'error': 'user_not_found'}), 404
    with pg.connection() as conn:
        if scope == 'all':
            deleted = conn.execute(
                "DELETE FROM ai_usage_daily WHERE user_id = %s", (user_id,),
            ).rowcount
        else:
            deleted = conn.execute(
                "DELETE FROM ai_usage_daily WHERE user_id = %s AND usage_date = CURRENT_DATE",
                (user_id,),
            ).rowcount
        conn.execute("UPDATE users SET quota_reset_at = NOW() WHERE user_id = %s", (user_id,))
    admin_ops.record_admin_audit(
        _admin_actor_id(admin), 'reset_ai_usage', 'user', user_id,
        before={'scope': scope}, after={'deleted_counters': deleted},
        request_id=request.headers.get('X-Request-Id'),
    )
    return jsonify({'success': True, 'admin': admin, 'deleted_counters': deleted})


@admin_bp.route('/ai-usage', methods=['GET'])
def admin_ai_usage():
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    try:
        days = min(max(int(request.args.get('days', 30)), 1), 365)
    except (TypeError, ValueError):
        days = 30
    usage = _postgres_ai_usage(days) if pg.enabled() else {
        'summary': {}, 'providers': [], 'models': [], 'tiers': [],
        'features': [], 'daily': [], 'recent_errors': [],
    }
    return jsonify({
        'success': True, 'admin': admin, 'days': days, 'usage': usage,
        'generated_at': datetime.now(timezone.utc).isoformat(),
    })


@admin_bp.route('/ai-controls', methods=['GET', 'PUT'])
def admin_ai_controls():
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    if request.method == 'GET':
        controls = admin_ops.get_controls()
    else:
        before = admin_ops.get_controls()
        try:
            controls = admin_ops.save_controls(request.get_json(silent=True) or {}, _admin_actor_id(admin))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        admin_ops.record_admin_audit(
            _admin_actor_id(admin), 'update_ai_controls', 'settings', admin_ops.CONTROLS_KEY,
            before=before, after=controls, request_id=request.headers.get('X-Request-Id'),
        )
    return jsonify({
        'success': True, 'admin': admin, 'controls': controls,
        'budget_state': admin_ops.current_budget_state(),
    })


@admin_bp.route('/integrations', methods=['GET'])
def admin_integrations():
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    payload = _postgres_integrations() if pg.enabled() else {'google': {}, 'api_errors': []}
    from services.chat_agents import ai_service
    payload['ai_providers'] = ai_service.get_provider_status()
    return jsonify({'success': True, 'admin': admin, 'integrations': payload})


@admin_bp.route('/system-health', methods=['GET'])
def admin_system_health():
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    postgres_enabled = pg.enabled()
    payload = _postgres_system_health() if postgres_enabled else {
        'database': {'name': 'sqlite'}, 'metrics': {}, 'events': [],
    }
    integration = _postgres_integrations() if postgres_enabled else {'google': {}, 'api_errors': []}
    from services.chat_agents import ai_service
    payload.update({
        'frontend_status': 'operational', 'backend_status': 'operational',
        'database_status': 'operational',
        'uptime_seconds': int(time.time() - _PROCESS_STARTED_AT),
        'integration_status': integration,
        'ai_providers': ai_service.get_provider_status(),
    })
    return jsonify({'success': True, 'admin': admin, 'health': payload})


@admin_bp.route('/security', methods=['GET'])
def admin_security():
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    payload = _postgres_security() if pg.enabled() else {
        'event_counts': [], 'admin_audit': [], 'suspicious_ai_usage': [],
        'suspicious_logins': [],
    }
    return jsonify({'success': True, 'admin': admin, 'security': payload})


@admin_bp.route('/workspaces', methods=['GET'])
def admin_workspaces():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    payload = _postgres_workspace_dashboard() if pg.enabled() else _empty_workspace_dashboard()
    return jsonify({
        'success': True,
        'admin': admin,
        'backend': 'postgres' if pg.enabled() else 'sqlite',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        **payload,
    })


@admin_bp.route('/workspaces/<workspace_id>/audit', methods=['GET'])
def admin_workspace_audit(workspace_id):
    """Surface workspace_audit_events (Phase 5 runtime security monitoring).

    Every business-data mutation already writes one of these rows via
    models.workspace.record_audit_event (see models/project.py, task.py,
    status_report.py, shared_artifact.py, workspace_subscription.py) --
    nothing read them back before this endpoint existed."""
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    if not pg.enabled():
        return jsonify({'success': True, 'admin': admin, 'backend': 'sqlite', 'events': [], 'has_more': False})

    try:
        limit = min(max(int(request.args.get('limit', 50)), 1), 200)
    except (TypeError, ValueError):
        limit = 50
    event_type = (request.args.get('event_type') or '').strip() or None
    before = (request.args.get('before') or '').strip() or None

    # Fetch one extra row to know whether there's a next page without a
    # separate COUNT(*) query.
    events = workspace_model.list_audit_events(
        workspace_id, limit=limit + 1, event_type=event_type, before=before,
    )
    has_more = len(events) > limit
    events = events[:limit]
    return jsonify({
        'success': True,
        'admin': admin,
        'backend': 'postgres',
        'events': events,
        'has_more': has_more,
        'next_before': events[-1]['created_at'] if has_more and events else None,
    })


@admin_bp.route('/users/<user_id>/subscription', methods=['POST'])
def admin_grant_subscription(user_id):
    """Manually grant Premium to a user (provider='manual'), for the period
    before Google Play Billing/RevenueCat is wired up. Same subscriptions
    row shape a future payment-provider webhook would eventually insert."""
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    if not pg.enabled():
        return jsonify({'error': 'subscriptions_require_postgres'}), 400

    data = request.get_json(silent=True) or {}
    action = (data.get('action') or '').strip().lower() or None
    if action and action not in subscription_model.PURCHASE_ACTIONS:
        return jsonify({'error': 'invalid_subscription_action'}), 400
    plan_code = (data.get('plan_code') or 'premium_monthly').strip()
    plan_name = (data.get('plan_name') or 'Premium').strip()
    billing_interval = data.get('billing_interval') or 'monthly'
    if billing_interval not in ('monthly', 'yearly'):
        return jsonify({'error': 'invalid_billing_interval'}), 400
    try:
        unit_amount = int(data.get('unit_amount') or (520000 if billing_interval == 'yearly' else 49000))
        days = int(data.get('days') or (365 if billing_interval == 'yearly' else 30))
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid_amount_or_days'}), 400

    try:
        row = subscription_model.grant_manual(
            user_id,
            plan_code,
            plan_name=plan_name,
            billing_interval=billing_interval,
            unit_amount=unit_amount,
            currency=data.get('currency') or 'VND',
            days=days,
            action=action,
        )
    except subscription_model.SubscriptionStateError as exc:
        return jsonify({
            'error': exc.code,
            'allowed_action': exc.allowed_action,
            'subscription': exc.subscription,
        }), 409

    try:
        WorkspaceSync.bump(user_id, ('profile', 'settings', 'overview'))
    except Exception:
        pass
    admin_ops.record_admin_audit(
        _admin_actor_id(admin), 'subscription_upgrade', 'user', user_id,
        after={'plan_code': row.get('plan_code'), 'status': row.get('status')},
        request_id=request.headers.get('X-Request-Id'),
    )
    return jsonify({
        'success': True,
        'admin': admin,
        'action': row.get('entitlement_action'),
        'subscription': row,
    })


@admin_bp.route('/workspaces/<workspace_id>/subscription', methods=['POST'])
def admin_grant_workspace_subscription(workspace_id):
    """Manually grant/renew a Business workspace subscription (provider=
    'manual'), for the period before a real payment gateway is wired up.
    Same subscriptions row shape a future payment-provider webhook would
    eventually insert -- see routes/workspace.py's models/workspace_subscription
    module docstring."""
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    if not pg.enabled():
        return jsonify({'error': 'subscriptions_require_postgres'}), 400

    data = request.get_json(silent=True) or {}
    action = (data.get('action') or '').strip().lower() or None
    if action and action not in workspace_subscription.PURCHASE_ACTIONS:
        return jsonify({'error': 'invalid_subscription_action'}), 400
    plan_code = (data.get('plan_code') or 'business_monthly').strip()
    plan_name = (data.get('plan_name') or 'Business').strip()
    billing_interval = data.get('billing_interval') or 'monthly'
    if billing_interval not in ('monthly', 'yearly'):
        return jsonify({'error': 'invalid_billing_interval'}), 400
    try:
        unit_amount = int(data.get('unit_amount') or 0)
        days = int(data.get('days') or (365 if billing_interval == 'yearly' else 30))
        included_seats = int(
            data.get('included_seats') or workspace_subscription.DEFAULT_BUSINESS_INCLUDED_SEATS
        )
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid_amount_or_days'}), 400

    try:
        row = workspace_subscription.grant_manual(
            workspace_id,
            plan_code,
            plan_name=plan_name,
            billing_interval=billing_interval,
            unit_amount=unit_amount,
            currency=data.get('currency') or 'VND',
            included_seats=included_seats,
            days=days,
            action=action,
            actor_user_id=_admin_actor_id(admin),
        )
    except workspace_subscription.WorkspaceSubscriptionError as exc:
        return jsonify({
            'error': exc.code,
            'allowed_action': exc.extra.get('allowed_action'),
            'subscription': exc.extra.get('subscription'),
        }), 409

    admin_ops.record_admin_audit(
        _admin_actor_id(admin), 'workspace_subscription_update', 'workspace', workspace_id,
        after={'plan_code': row.get('plan_code'), 'status': row.get('status')},
        request_id=request.headers.get('X-Request-Id'),
    )

    return jsonify({
        'success': True,
        'admin': admin,
        'action': row.get('entitlement_action'),
        'subscription': row,
    })


@admin_bp.route('/workspaces/<workspace_id>/subscription/revoke', methods=['POST'])
def admin_revoke_workspace_subscription(workspace_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    if not pg.enabled():
        return jsonify({'error': 'subscriptions_require_postgres'}), 400

    revoked = workspace_subscription.revoke(
        workspace_id,
        actor_user_id=_admin_actor_id(admin),
    )
    if not revoked:
        return jsonify({'error': 'no_active_business_subscription'}), 404
    admin_ops.record_admin_audit(
        _admin_actor_id(admin), 'workspace_subscription_revoke', 'workspace', workspace_id,
        after={'revoked': True}, request_id=request.headers.get('X-Request-Id'),
    )
    return jsonify({'success': True, 'admin': admin, 'revoked': True})


@admin_bp.route('/users/<user_id>/subscription/revoke', methods=['POST'])
def admin_revoke_subscription(user_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    if not pg.enabled():
        return jsonify({'error': 'subscriptions_require_postgres'}), 400

    revoked = subscription_model.revoke(user_id)
    if not revoked:
        return jsonify({'error': 'no_active_premium'}), 404
    try:
        WorkspaceSync.bump(user_id, ('profile', 'settings', 'overview'))
    except Exception:
        pass
    admin_ops.record_admin_audit(
        _admin_actor_id(admin), 'subscription_downgrade', 'user', user_id,
        after={'revoked': True}, request_id=request.headers.get('X-Request-Id'),
    )
    return jsonify({'success': True, 'admin': admin, 'revoked': True})
