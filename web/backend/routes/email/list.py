"""Inbox listing/detail: the main /get-unread scan+cache+paginate pipeline,
the background new-mail-watcher poll target, on-demand body/attachment/AI
summary fetch, and the cache admin endpoints.

Split out of the former monolithic routes/email.py -- see
routes/email/__init__.py for the package-level overview.
"""
import logging
import os
import socket
import ssl
from datetime import datetime
from io import BytesIO

from flask import request, jsonify, url_for, session, send_file

from models.cache import Cache
from models.history import History
from utils.user_context import get_current_user_id, get_user_db_path
from utils.quota import enforce_ai_quota

from routes.email.shared import (
    email_bp,
    ai_service,
    EMAIL_SCAN_DEFAULT,
    EMAIL_SCAN_MAX,
    EMAIL_LIST_CACHE_TTL,
    EMAIL_BODY_CACHE_TTL,
    EMAIL_SUMMARY_CACHE_TTL,
    _get_cache_key,
    _email_body_cache_key,
    _email_summary_cache_key,
    _gmail_query_for_email_list,
    _compact_preview,
    _are_emails_cached,
    _get_cached_emails,
    _cache_emails,
    _clear_all_cache,
    _clear_email_list_cache,
)
from routes.email.smart_inbox import _classify_email_lightweight, _smart_inbox_bucket, _extract_deadline_date
from routes.email.meeting import (
    _store_meeting_suggestions,
    _safe_prune_existing_meeting_suggestions,
    _safe_pending_meeting_suggestions,
)
from routes.email.oauth import _load_gmail_service

# Configure module logger
logger = logging.getLogger(__name__)

# GmailService already retries transient errors internally (num_retries= on
# every .execute()); this only covers the rarer case where retries are
# exhausted. Without it, a raw exception like "[SSL] record layer failure"
# was reaching the mobile Alert verbatim instead of an actionable message.
_TRANSIENT_NETWORK_ERRORS = (ssl.SSLError, socket.timeout, ConnectionError, TimeoutError)


def _friendly_network_error(e):
    if isinstance(e, _TRANSIENT_NETWORK_ERRORS):
        return 'Không thể kết nối tới Gmail lúc này, vui lòng thử lại sau ít phút.'
    return None


def _clamp_scan_limit(raw_value):
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = EMAIL_SCAN_DEFAULT
    return max(1, min(value, EMAIL_SCAN_MAX))


def _matches_filter(email, filter_type):
    if filter_type == 'all':
        return True
    tag = email.get('tag') or _classify_email_lightweight(email)
    aliases = {
        'work': {'work', 'business'},
        'promotion': {'promotion', 'ads'},
        'meeting': {'meeting'}
    }
    return tag == filter_type or tag in aliases.get(filter_type, set())


def _hydrate_email_for_list(email, user_id, cached_entries=None):
    email = dict(email or {})
    email['tag'] = email.get('tag') or _classify_email_lightweight(email)
    email['tag_confidence'] = email.get('tag_confidence', 0.65 if email['tag'] != 'other' else 0.0)
    email['smart_bucket'] = _smart_inbox_bucket(email)
    deadline_date = _extract_deadline_date(email)
    email['deadline_date'] = deadline_date.isoformat() if deadline_date else None
    cached_entries = cached_entries or {}

    summary_key = _email_summary_cache_key(user_id, email.get('id', ''))
    body_key = _email_body_cache_key(user_id, email.get('id', ''))
    cached_summary = cached_entries.get(summary_key)
    if isinstance(cached_summary, dict) and cached_summary.get('summary'):
        email['summary'] = cached_summary.get('summary')
        email['summary_type'] = 'ai_cached'
    else:
        email['summary'] = _compact_preview(email.get('snippet', ''), max_chars=180)
        email['summary_type'] = 'preview'

    email['body_cached'] = bool(cached_entries.get(body_key))
    return email


@email_bp.route('/get-unread', methods=['GET'])
def get_unread_emails():
    """Get unread emails filtered by selected category with caching and parallel fetching."""
    user_id = get_current_user_id(request, session=session)
    logger.info(f"get_unread_emails: user_id = {user_id}")

    try:
        scan_limit = _clamp_scan_limit(request.args.get('max_results', EMAIL_SCAN_DEFAULT))
        page = request.args.get('page', 1, type=int)
        filter_type = request.args.get('filter', 'education', type=str).strip().lower()
        smart_bucket_filter = request.args.get('smart_bucket', '', type=str).strip().lower()
        search = request.args.get('search', '', type=str).strip()
        include_read = request.args.get('include_read', 'false', type=str).lower() == 'true'
        fresh = request.args.get('fresh', 'false', type=str).lower() in {'1', 'true', 'yes'}
        cache_only = request.args.get('cache_only', 'false', type=str).lower() in {'1', 'true', 'yes'}
        db_path = get_user_db_path(user_id)

        cache_key = _get_cache_key(
            user_id, filter_type, include_read=include_read, scan_limit=scan_limit, search=search,
        )
        db_cache_key = cache_key

        # Try in-memory cache first, then DB cache.
        suggestions_scanned = False
        cache_hit = False
        cached_emails, cached_total = (None, None) if fresh else _get_cached_emails(cache_key)
        if cached_emails is not None:
            inbox_emails = cached_emails
            total_raw = cached_total
            cache_hit = True
        else:
            cached_db = None if fresh else Cache.get(db_cache_key, db_path=db_path)
            if isinstance(cached_db, dict) and cached_db.get('emails') is not None:
                inbox_emails = cached_db.get('emails') or []
                total_raw = cached_db.get('total', len(inbox_emails))
                _cache_emails(cache_key, inbox_emails, total_raw)
                cache_hit = True
            else:
                if cache_only:
                    suggestions = _safe_prune_existing_meeting_suggestions(db_path)
                    return jsonify({
                        'success': True,
                        'filter': filter_type,
                        'search': search,
                        'emails': [],
                        'total_filtered': 0,
                        'matched_count': 0,
                        'cache_hit': False,
                        'cache_miss': True,
                        'needs_refresh': True,
                        'fresh': fresh,
                        'cache_only': cache_only,
                        'scan_limit': scan_limit,
                        'debug': {
                            'raw_email_count': 0,
                            'filtered_email_count': 0,
                            'current_page_items': 0
                        },
                        'pagination': {
                            'current_page': 1,
                            'total_pages': 0,
                            'per_page': scan_limit,
                            'total_items': 0
                        },
                        'meeting_suggestions': suggestions
                    })

                service = _load_gmail_service(user_id)
                if not service:
                    logger.warning(f"Gmail service not available for user: {user_id}")
                    return jsonify({
                        'error': 'not_authenticated',
                        'auth_url': url_for('email.gmail_auth_url', _external=True),
                        'debug': {
                            'user_id': user_id,
                            'session_has_email': 'gmail_user_email' in session if session else False
                        }
                    }), 401

                raw_emails = service.get_emails(
                    max_results=scan_limit,
                    query=_gmail_query_for_email_list(search),
                    include_read=include_read,
                    raise_errors=True,
                )
                logger.info(f"Fetched {len(raw_emails)} raw email metadata records from Gmail")

                hydrated = []
                for email in raw_emails:
                    email = dict(email or {})
                    email['tag'] = _classify_email_lightweight(email)
                    email['tag_confidence'] = 0.65 if email['tag'] != 'other' else 0.0
                    email['smart_bucket'] = _smart_inbox_bucket(email)
                    deadline_date = _extract_deadline_date(email)
                    email['deadline_date'] = deadline_date.isoformat() if deadline_date else None
                    email['summary'] = _compact_preview(email.get('snippet', ''), max_chars=180)
                    email['summary_type'] = 'preview'
                    hydrated.append(email)

                _store_meeting_suggestions(hydrated, db_path)
                suggestions_scanned = True
                inbox_emails = hydrated
                total_raw = len(raw_emails)

                _cache_emails(cache_key, inbox_emails, total_raw)
                Cache.set(db_cache_key, {
                    'emails': inbox_emails,
                    'total': total_raw,
                    'filter': 'all',
                    'include_read': include_read,
                    'scan_limit': scan_limit,
                    'timestamp': datetime.now().isoformat()
                }, ttl=EMAIL_LIST_CACHE_TTL, db_path=db_path)
                cache_hit = False

        filtered_emails = [
            email for email in inbox_emails
            if _matches_filter(email, filter_type)
        ]
        if smart_bucket_filter:
            filtered_emails = [
                email for email in filtered_emails
                if (email.get('smart_bucket') or _smart_inbox_bucket(email)) == smart_bucket_filter
            ]
        # No local _matches_search re-filter here: when `search` is set,
        # `inbox_emails` already came from a Gmail-side search query (see
        # above), which searches the full message body/headers across the
        # whole mailbox. Re-applying a local substring check against just
        # sender/subject/snippet/summary/tag would incorrectly drop a
        # legitimate Gmail match whose only hit was in body text this
        # narrower local check never looks at.

        # Calculate pagination
        total_emails = len(filtered_emails)
        per_page = scan_limit
        total_pages = (total_emails + per_page - 1) // per_page
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1

        # Get page emails
        offset = (page - 1) * per_page
        selected_emails = filtered_emails[offset:offset + per_page]
        detail_cache_keys = []
        for email in selected_emails:
            email_id = email.get('id', '')
            detail_cache_keys.append(_email_summary_cache_key(user_id, email_id))
            detail_cache_keys.append(_email_body_cache_key(user_id, email_id))
        cached_entries = Cache.get_many(detail_cache_keys, db_path=db_path)
        page_emails = [
            _hydrate_email_for_list(email, user_id, cached_entries=cached_entries)
            for email in selected_emails
        ]
        if not suggestions_scanned:
            _store_meeting_suggestions(page_emails, db_path)

        return jsonify({
            'success': True,
            'filter': filter_type,
            'search': search,
            'emails': page_emails,
            'total_filtered': total_raw,
            'matched_count': total_emails,
            'cache_hit': cache_hit,
            'fresh': fresh,
            'cache_only': cache_only,
            'scan_limit': scan_limit,
            'debug': {
                'raw_email_count': total_raw,
                'filtered_email_count': total_emails,
                'current_page_items': len(page_emails)
            },
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'per_page': per_page,
                'total_items': total_emails
            },
            'meeting_suggestions': _safe_pending_meeting_suggestions(db_path)
        })
    except Exception as e:
        logger.error(f"Error in get_unread_emails: {str(e)}", exc_info=True)
        google_status = getattr(getattr(e, 'resp', None), 'status', None)
        if google_status in (401, 403):
            return jsonify({
                'error': 'google_reauthentication_required',
                'message': 'Phiên Google đã hết hạn hoặc thiếu quyền Gmail. Vui lòng kết nối lại.',
                'needs_reauth': True,
                'google_status': google_status,
            }), 401
        friendly = _friendly_network_error(e)
        if friendly:
            # `error` is what the mobile/web clients display verbatim (see
            # api/client.js: `data.error || data.message`) -- it must be the
            # human-readable text itself, not a machine code, unless the
            # caller has a special-case branch for that code (it doesn't here).
            return jsonify({'error': friendly, 'error_type': 'gmail_network_error'}), 503
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500


NEW_MAIL_CHECK_CACHE_TTL = 2


def _new_mail_check_cache_key(user_id):
    return f"{user_id}:email:new_mail_check"


@email_bp.route('/new-mail-check', methods=['GET'])
def new_mail_check():
    """Lightweight poll target for the client's background new-mail watcher.

    Returns just the newest unread message id, its sender/subject, and an
    unread count -- cheap enough to call every ~90s from every open tab.
    Cached briefly server-side so several tabs/devices for the same user
    share one Gmail round trip instead of each paying for their own.
    """
    user_id = get_current_user_id(request, session=session)
    db_path = get_user_db_path(user_id)
    cache_key = _new_mail_check_cache_key(user_id)

    cached = Cache.get(cache_key, db_path=db_path)
    if isinstance(cached, dict):
        return jsonify({'success': True, **cached})

    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    try:
        snapshot = service.list_unread_ids(max_results=5)
        latest_id = snapshot['ids'][0] if snapshot['ids'] else None
        payload = {
            'unread_count': snapshot['unread_count'],
            'latest_id': latest_id,
            'latest_subject': '',
            'latest_sender': '',
        }
        if latest_id:
            details = service.get_email_details(latest_id, lazy=False)
            if details:
                payload['latest_subject'] = details.get('subject', '')
                payload['latest_sender'] = details.get('sender', '')
                detected = _store_meeting_suggestions([details], db_path)
                matching = next(
                    (item for item in detected if item.get('email_id') == latest_id),
                    None,
                )
                if matching:
                    payload['meeting_suggestion'] = matching

        Cache.set(cache_key, payload, ttl=NEW_MAIL_CHECK_CACHE_TTL, db_path=db_path)
        return jsonify({'success': True, **payload})
    except Exception as e:
        logger.warning(f"Error in new_mail_check: {e}")
        return jsonify({'error': str(e)}), 500


@email_bp.route('/get-email-body/<email_id>', methods=['GET'])
def get_email_body(email_id):
    """Get full email body on-demand (lazy loading for performance)"""
    user_id = get_current_user_id(request, session=session)
    db_path = get_user_db_path(user_id)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    try:
        cached = Cache.get(_email_body_cache_key(user_id, email_id), db_path=db_path)
        if (
            isinstance(cached, dict)
            and cached.get('body')
            and 'attachments' in cached
        ):
            return jsonify({
                'success': True,
                'body': cached.get('body', ''),
                'email': cached,
                'cache_hit': True
            })

        email_data = service.get_email_details(email_id, lazy=False)
        if email_data:
            _store_meeting_suggestions([email_data], db_path)
            Cache.set(
                _email_body_cache_key(user_id, email_id),
                email_data,
                ttl=EMAIL_BODY_CACHE_TTL,
                db_path=db_path
            )
            return jsonify({
                'success': True,
                'body': email_data.get('body', ''),
                'email': email_data,
                'cache_hit': False
            })
        return jsonify({'error': 'Email not found'}), 404
    except Exception as e:
        logger.error(f"Error getting email body: {str(e)}")
        return jsonify({'error': str(e)}), 500


@email_bp.route('/attachment/<email_id>/<path:attachment_id>', methods=['GET'])
def get_email_attachment(email_id, attachment_id):
    """Download an attachment, or preview a small set of browser-safe formats."""
    user_id = get_current_user_id(request, session=session)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    attachment = service.get_attachment(email_id, attachment_id)
    if not attachment:
        return jsonify({'error': 'Attachment not found'}), 404

    filename = str(attachment.get('filename') or 'attachment')
    filename = os.path.basename(filename.replace('\\', '/')).replace('\r', '').replace('\n', '')
    mime_type = str(attachment.get('mime_type') or 'application/octet-stream').lower()
    preview_types = {
        'application/pdf',
        'image/gif',
        'image/jpeg',
        'image/png',
        'image/webp',
        'text/plain',
    }
    preview = request.args.get('preview') == '1' and mime_type in preview_types
    response = send_file(
        BytesIO(attachment.get('data') or b''),
        mimetype=mime_type,
        as_attachment=not preview,
        download_name=filename,
        max_age=0,
    )
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@email_bp.route('/summary/<email_id>', methods=['GET', 'POST'])
def summarize_email_detail(email_id):
    """Generate or return cached polished AI summary for one email."""
    user_id = get_current_user_id(request, session=session)
    db_path = get_user_db_path(user_id)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    try:
        summary_key = _email_summary_cache_key(user_id, email_id)
        cached_summary = Cache.get(summary_key, db_path=db_path)
        if isinstance(cached_summary, dict) and cached_summary.get('summary'):
            return jsonify({
                'success': True,
                'summary': cached_summary.get('summary', ''),
                'email': cached_summary.get('email', {}),
                'cache_hit': True
            })

        email_data = Cache.get(_email_body_cache_key(user_id, email_id), db_path=db_path)
        if not isinstance(email_data, dict) or not email_data.get('body'):
            email_data = service.get_email_details(email_id, lazy=False)
            if not email_data:
                return jsonify({'error': 'Email not found'}), 404
            _store_meeting_suggestions([email_data], db_path)
            Cache.set(
                _email_body_cache_key(user_id, email_id),
                email_data,
                ttl=EMAIL_BODY_CACHE_TTL,
                db_path=db_path
            )

        quota_rejection = enforce_ai_quota(user_id, 'email_summary')
        if quota_rejection:
            return jsonify({'error': 'ai_limit_reached', **quota_rejection}), 403

        summary = ai_service.summarize_email_polished(email_data, user_id=user_id)
        payload = {
            'summary': summary,
            'email': {
                'id': email_data.get('id'),
                'subject': email_data.get('subject'),
                'sender': email_data.get('sender'),
                'date': email_data.get('date')
            },
            'generated_at': datetime.now().isoformat()
        }
        Cache.set(summary_key, payload, ttl=EMAIL_SUMMARY_CACHE_TTL, db_path=db_path)

        try:
            History.create(
                f"Tom tat AI email: {email_data.get('subject', '')}",
                summary,
                action_type='email_summary',
                db_path=db_path
            )
        except Exception:
            pass

        return jsonify({
            'success': True,
            'summary': summary,
            'email': payload['email'],
            'cache_hit': False
        })
    except Exception as e:
        logger.error(f"Error summarizing email: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# CACHE MANAGEMENT ENDPOINTS

@email_bp.route('/cache/clear', methods=['POST'])
def clear_cache():
    """Clear all cached data for current user"""
    user_id = get_current_user_id(request, session=session)
    if not user_id or user_id == 'default':
        return jsonify({'error': 'User not authenticated'}), 401

    try:
        db_path = get_user_db_path(user_id)
        data = request.get_json(silent=True) or {}
        scope = (data.get('scope') or request.args.get('scope') or 'list').strip().lower()

        if scope == 'all':
            _clear_all_cache(user_id)
            Cache.clear_pattern(f"{user_id}:*", db_path=db_path)
            Cache.clear_pattern(f"ai::{user_id}:%", db_path=db_path)
        else:
            _clear_email_list_cache(user_id)

        logger.info(f"Cache cleared for user: {user_id}")
        return jsonify({
            'success': True,
            'message': 'Đã xóa bộ nhớ cache'
        })
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return jsonify({'error': str(e)}), 500


@email_bp.route('/cache/emails/<filter_type>', methods=['GET'])
def get_cached_emails_endpoint(filter_type):
    """Get cached emails for specific filter"""
    user_id = get_current_user_id(request, session=session)
    if not user_id or user_id == 'default':
        return jsonify({'error': 'User not authenticated'}), 401

    try:
        db_path = get_user_db_path(user_id)
        cache_key = f"{user_id}:emails:{filter_type}"

        cached_data = Cache.get(cache_key, db_path=db_path)

        if cached_data:
            return jsonify({
                'success': True,
                'cache_hit': True,
                'data': cached_data,
                'message': f'Dữ liệu từ cache ({filter_type})'
            })
        else:
            return jsonify({
                'success': True,
                'cache_hit': False,
                'data': None,
                'message': 'Không có dữ liệu trong cache'
            })
    except Exception as e:
        logger.error(f"Error getting cached emails: {e}")
        return jsonify({'error': str(e)}), 500
