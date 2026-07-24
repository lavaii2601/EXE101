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
from models import postgres_db as pg
from models.knowledge import KnowledgeDocument
from models.user import User
from utils.security import authenticated_user_id
from utils.user_context import sanitize_user_id


admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')
_PROCESS_STARTED_AT = time.time()
_totp_attempts = defaultdict(deque)
_totp_attempts_lock = threading.Lock()


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
    code = str(code or '').strip()
    if not re.fullmatch(r'\d{6}', code):
        return False
    now = time.time() if timestamp is None else float(timestamp)
    return any(
        hmac.compare_digest(code, _totp_at(secret, now + offset * 30))
        for offset in range(-window, window + 1)
    )


def _trusted_google_email(user_id):
    user = User.get(user_id) or {}
    session_email = str(session.get('gmail_user_email') or '').strip().lower()
    stored_email = str(user.get('gmail_email') or '').strip().lower()
    if session_email:
        return session_email
    if user.get('gmail_connected') and stored_email:
        return stored_email
    return ''


def _configuration_error():
    if not Config.ADMIN_EMAILS:
        return 'ADMIN_EMAILS is not configured'
    try:
        _decode_totp_secret(Config.ADMIN_TOTP_SECRET)
    except ValueError as exc:
        return str(exc)
    return None


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
    google_email = _trusted_google_email(user_id)
    if not google_email or google_email not in Config.ADMIN_EMAILS:
        return None, (
            jsonify({
                'error': 'admin_not_allowed',
                'message': 'Tài khoản Google này không có quyền quản trị.',
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


def _attempt_key(user_id):
    forwarded = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
    return user_id, forwarded or request.remote_addr or 'unknown'


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


def _empty_finance():
    return {
        'has_data': False,
        'currencies': [{
            'currency': 'VND',
            'gross_revenue_month': 0,
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
        }],
        'revenue_12m': [],
        'subscriptions_by_plan': [],
        'recent_payments': [],
        'recent_subscriptions': [],
        'money_unit': 'minor',
        'reporting_timezone': 'Asia/Ho_Chi_Minh',
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
                    COUNT(*) AS total_transactions
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
                COALESCE(payment_stats.total_transactions, 0)::BIGINT AS total_transactions
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
                subscription.provider,
                subscription.plan_code,
                COALESCE(NULLIF(subscription.plan_name, ''), subscription.plan_code) AS plan_name,
                subscription.status,
                subscription.billing_interval,
                subscription.currency,
                subscription.unit_amount,
                subscription.current_period_end,
                subscription.cancel_at_period_end,
                subscription.created_at,
                COALESCE(
                    NULLIF(users.gmail_email, ''),
                    NULLIF(users.email, ''),
                    subscription.user_id
                ) AS customer
            FROM subscriptions subscription
            LEFT JOIN users ON users.user_id = subscription.user_id
            ORDER BY subscription.updated_at DESC
            LIMIT 30
            """
        ).fetchall()

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
        'money_unit': 'minor',
        'reporting_timezone': 'Asia/Ho_Chi_Minh',
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

    code = (request.get_json(silent=True) or {}).get('code')
    if not _verify_totp(code, Config.ADMIN_TOTP_SECRET):
        return jsonify({
            'error': 'admin_totp_invalid',
            'message': 'Mã Authenticator không đúng hoặc đã hết hạn.',
        }), 401

    session['admin_totp_user'] = user_id
    session['admin_totp_verified_at'] = int(time.time())
    session.modified = True
    _clear_totp_attempts(user_id)
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
