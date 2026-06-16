import os
import sys
import logging
import pickle
import json
import base64
import re
import requests
import unicodedata
from io import BytesIO
from flask import Blueprint, request, jsonify, redirect, url_for, session, send_file
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from googleapiclient.discovery import build
from services.gmail_service import GmailService
from services.mistral_service import MistralService
from services.ai_service import AIService
from models.history import History
from models.schedule import Schedule
from models.user import User
from models.cache import Cache
from models.meeting_suggestion import MeetingSuggestion
from config import Config
from config import GMAIL_CLIENT_ID_KEYS, GMAIL_CLIENT_SECRET_KEYS, GMAIL_CREDENTIALS_JSON_KEYS
from utils.user_context import get_current_user_id, get_user_db_path, get_user_token_file
from utils.security import issue_mobile_token

# Configure module logger
logger = logging.getLogger(__name__)

# Email-related endpoints including OAuth login and Gmail access
email_bp = Blueprint('email', __name__, url_prefix='/api/email')

# Initialize services
mistral_service = MistralService()
ai_service = AIService()

# Simple in-memory cache for email lists (10 minute TTL for optimal performance)
_email_cache = {}
EMAIL_SCAN_DEFAULT = 70
EMAIL_SCAN_MAX = 70
EMAIL_LIST_CACHE_TTL = 1800
EMAIL_BODY_CACHE_TTL = 86400
EMAIL_SUMMARY_CACHE_TTL = 86400

def _get_cache_key(user_id, filter_type, include_read=False, scan_limit=EMAIL_SCAN_DEFAULT):
    """Generate cache key"""
    read_scope = 'with_read' if include_read else 'unread'
    return f"{user_id}:emails:list:{filter_type}:{read_scope}:{scan_limit}"


def _email_body_cache_key(user_id, email_id):
    return f"{user_id}:email:body:{email_id}"


def _email_summary_cache_key(user_id, email_id):
    return f"{user_id}:email:summary:{email_id}"


def _clamp_scan_limit(raw_value):
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = EMAIL_SCAN_DEFAULT
    return max(1, min(value, EMAIL_SCAN_MAX))


def _compact_preview(text, max_chars=220):
    value = re.sub(r'\s+', ' ', (text or '').strip())
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + '...'


def _classify_email_lightweight(email):
    text = ' '.join([
        email.get('subject', '') or '',
        email.get('sender', '') or '',
        email.get('snippet', '') or ''
    ]).lower()

    rules = [
        ('meeting', ['meeting', 'hop', 'họp', 'lich hen', 'lịch hẹn', 'appointment', 'schedule', 'calendar', 'zoom', 'meet', 'teams']),
        ('education', ['school', 'class', 'student', 'teacher', 'course', 'lesson', 'assignment', 'giao duc', 'giáo dục', 'hoc sinh', 'học sinh']),
        ('finance', ['invoice', 'payment', 'receipt', 'bank', 'billing', 'hoa don', 'hóa đơn', 'thanh toan', 'thanh toán']),
        ('promotion', ['sale', 'discount', 'promotion', 'newsletter', 'unsubscribe', 'coupon', 'marketing', 'khuyến mãi']),
        ('work', ['task', 'project', 'deadline', 'report', 'proposal', 'contract', 'cong viec', 'công việc']),
        ('personal', ['family', 'friend', 'personal'])
    ]

    for tag, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return tag
    return 'other'


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


def _normalize_search_text(value):
    text = unicodedata.normalize('NFKD', str(value or '').lower())
    return ''.join(char for char in text if not unicodedata.combining(char))


def _matches_search(email, keyword):
    normalized_keyword = _normalize_search_text(keyword).strip()
    if not normalized_keyword:
        return True
    searchable = ' '.join([
        email.get('sender', ''),
        email.get('subject', ''),
        email.get('snippet', ''),
        email.get('summary', ''),
        email.get('tag', '')
    ])
    return normalized_keyword in _normalize_search_text(searchable)


def _hydrate_email_for_list(email, user_id, cached_entries=None):
    email = dict(email or {})
    email['tag'] = email.get('tag') or _classify_email_lightweight(email)
    email['tag_confidence'] = email.get('tag_confidence', 0.65 if email['tag'] != 'other' else 0.0)
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


def _extract_meeting_suggestion(email):
    subject = str(email.get('subject', '') or '').strip()
    sender = str(email.get('sender', '') or '').strip()
    snippet = str(email.get('snippet', '') or '').strip()
    body = str(email.get('body', '') or '').strip()
    text = ' '.join([subject, snippet, body])
    normalized = _normalize_search_text(text)

    direct_terms = [
        'cuoc hop', 'cuoc hen', 'hop luc', 'lich hen', 'hen gap', 'gap mat',
        'meeting', 'appointment',
        'google meet', 'zoom', 'microsoft teams', 'book slot', 'booked',
    ]
    schedule_terms = ['schedule', 'calendar', 'dat lich', 'xep lich', 'time slot']
    time_signal = bool(re.search(r'(?<!\d)(?:[01]?\d|2[0-3])[:h]\d{2}(?!\d)', normalized))
    date_signal = bool(re.search(
        r'(?<!\d)(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})(?!\d)',
        normalized
    ))
    is_meeting = (
        any(term in normalized for term in direct_terms)
        or (any(term in normalized for term in schedule_terms) and (time_signal or date_signal))
    )
    if not is_meeting:
        return None

    meeting_date = None
    date_match = re.search(
        r'(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})(?!\d)',
        normalized
    )
    iso_date_match = re.search(
        r'(?<!\d)(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?!\d)',
        normalized
    )
    text_date_match = re.search(
        r'(?<!\d)(\d{1,2})\s+thang\s+(\d{1,2})\s*,?\s*(\d{4})(?!\d)',
        normalized
    )
    try:
        if date_match:
            day, month, year = map(int, date_match.groups())
            if year < 100:
                year += 2000
            meeting_date = datetime(year, month, day).date()
        elif iso_date_match:
            year, month, day = map(int, iso_date_match.groups())
            meeting_date = datetime(year, month, day).date()
        elif text_date_match:
            day, month, year = map(int, text_date_match.groups())
            meeting_date = datetime(year, month, day).date()
    except ValueError:
        meeting_date = None

    start_time = None
    end_time = None
    time_matches = re.findall(
        r'(?<!\d)((?:[01]?\d|2[0-3]))[:h](\d{2})(?!\d)',
        normalized
    )
    if meeting_date and time_matches:
        start_hour, start_minute = map(int, time_matches[0])
        start_dt = datetime.combine(
            meeting_date,
            datetime.strptime(f'{start_hour:02d}:{start_minute:02d}', '%H:%M').time()
        )
        start_time = start_dt.isoformat()
        if len(time_matches) > 1:
            end_hour, end_minute = map(int, time_matches[1])
            end_dt = datetime.combine(
                meeting_date,
                datetime.strptime(f'{end_hour:02d}:{end_minute:02d}', '%H:%M').time()
            )
            if end_dt > start_dt:
                end_time = end_dt.isoformat()
        if not end_time:
            end_time = (start_dt + timedelta(hours=1)).isoformat()

    email_addresses = re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text)
    attendees = ','.join(dict.fromkeys(email_addresses))
    description = _compact_preview(
        f"Nguồn email từ {sender}\n{snippet or body}",
        max_chars=700
    )
    return {
        'sender': sender,
        'subject': subject,
        'email_date': email.get('date', ''),
        'snippet': snippet,
        'title': subject or 'Lịch hẹn từ email',
        'description': description,
        'start_time': start_time,
        'end_time': end_time,
        'location': '',
        'attendees': attendees,
    }


def _meeting_suggestion_exists_in_schedule(suggestion, db_path):
    suggested_start = suggestion.get('start_time')
    if not suggested_start:
        return False
    try:
        suggested_dt = datetime.fromisoformat(suggested_start)
    except (TypeError, ValueError):
        return False

    subject = _normalize_search_text(suggestion.get('subject', ''))
    for schedule in Schedule.get_all(limit=200, db_path=db_path):
        try:
            schedule_dt = datetime.fromisoformat(
                str(schedule.get('start_time') or '').replace('Z', '+00:00')
            )
            if schedule_dt.tzinfo is not None:
                schedule_dt = schedule_dt.replace(tzinfo=None)
        except (TypeError, ValueError):
            continue
        if abs((schedule_dt - suggested_dt).total_seconds()) > 300:
            continue
        title = _normalize_search_text(schedule.get('title', ''))
        if title and (title in subject or subject in title):
            return True
    return False


def _store_meeting_suggestions(emails, db_path):
    detected = []
    for email in emails:
        email_id = email.get('id')
        if not email_id:
            continue
        suggestion = _extract_meeting_suggestion(email)
        if not suggestion:
            continue
        if _meeting_suggestion_exists_in_schedule(suggestion, db_path):
            MeetingSuggestion.dismiss_email(email_id, db_path=db_path)
            continue
        suggestion_id = MeetingSuggestion.upsert(email_id, suggestion, db_path=db_path)
        detected.append({'id': suggestion_id, 'email_id': email_id, **suggestion})
    return detected

def _are_emails_cached(cache_key):
    """Check if cache is still valid (10 minute TTL for better performance)"""
    if cache_key not in _email_cache:
        return False
    cached_time, _, _ = _email_cache[cache_key]
    return datetime.now() - cached_time < timedelta(minutes=10)

def _get_cached_emails(cache_key):
    """Get cached emails if valid"""
    if _are_emails_cached(cache_key):
        _, cached_emails, cached_total = _email_cache[cache_key]
        return cached_emails, cached_total
    return None, None

def _cache_emails(cache_key, emails, total):
    """Cache emails with timestamp"""
    _email_cache[cache_key] = (datetime.now(), emails, total)

def _clear_all_cache(user_id):
    """Clear all cached emails for a user"""
    keys_to_delete = [k for k in _email_cache.keys() if k.startswith(f"{user_id}:")]
    for key in keys_to_delete:
        del _email_cache[key]
    logger.info(f"Cleared {len(keys_to_delete)} cache entries for user {user_id}")


def _clear_email_list_cache(user_id):
    """Invalidate list caches while preserving full bodies and AI summaries."""
    _clear_all_cache(user_id)
    try:
        db_path = get_user_db_path(user_id)
        Cache.clear_pattern(f"{user_id}:emails:list:%", db_path=db_path)
    except Exception as e:
        logger.warning(f"Failed to clear DB email list cache for {user_id}: {e}")


def _fetch_google_userinfo(creds):
    """Fetch Google account profile (email, name, picture) from UserInfo endpoint."""
    try:
        token_value = getattr(creds, 'token', None)
        if not token_value:
            return {}

        response = requests.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {token_value}'},
            timeout=8
        )
        if response.status_code != 200:
            return {}

        data = response.json() or {}
        return {
            'email': data.get('email', ''),
            'name': data.get('name', ''),
            'picture': data.get('picture', '')
        }
    except Exception:
        return {}


def _fetch_google_people_profile(creds):
    """Fetch Google People API profile data, including the avatar photo if available."""
    try:
        people_service = build('people', 'v1', credentials=creds)
        profile = people_service.people().get(
            resourceName='people/me',
            personFields='names,emailAddresses,photos'
        ).execute()

        names = profile.get('names') or []
        emails = profile.get('emailAddresses') or []
        photos = profile.get('photos') or []

        display_name = ''
        if names:
            display_name = names[0].get('displayName', '') or ''

        email = ''
        if emails:
            email = emails[0].get('value', '') or ''

        picture = ''
        if photos:
            for photo in photos:
                if photo.get('url'):
                    picture = photo.get('url')
                    break

        return {
            'email': email,
            'name': display_name,
            'picture': picture
        }
    except Exception as e:
        logger.debug(f"People API profile fetch failed: {e}")
        return {}


def _load_gmail_service(user_id):
    """Return GmailService instance if credentials token exists."""
    if not user_id or user_id == 'default':
        return None
    token_file = get_user_token_file(user_id)
    if os.path.exists(token_file):
        try:
            return GmailService(token_file=token_file)
        except Exception as e:
            print(f"Error creating GmailService: {e}")
    return None


def _clear_oauth_state(user_id):
    """Clear OAuth token/session so another user can sign in."""
    token_file = get_user_token_file(user_id)

    if os.path.exists(token_file):
        try:
            os.remove(token_file)
        except Exception as e:
            print(f"Error deleting token file: {e}")

    # Clear oauth session keys
    session.pop('oauth_state', None)
    session.pop('oauth_code_verifier', None)
    session.pop('oauth_user_id', None)
    session.pop('gmail_user_email', None)
    session.pop('gmail_user_name', None)
    session.pop('gmail_user_picture', None)
    session.pop('user_id', None)


def _get_redirect_uri():
    """Return the redirect URI registered in Google Console for this client."""
    configured_uri = (Config.GMAIL_REDIRECT_URI or '').strip()
    if configured_uri:
        return configured_uri

    forwarded_proto = request.headers.get('x-forwarded-proto', '').split(',')[0].strip()
    forwarded_host = request.headers.get('x-forwarded-host', '').split(',')[0].strip()
    scheme = forwarded_proto or request.scheme
    host = forwarded_host or request.host

    if os.getenv('VERCEL'):
        scheme = 'https'
        host = host or os.getenv('VERCEL_URL', '')

    if scheme and host:
        return f"{scheme}://{host}/api/email/oauth2callback"

    return "http://127.0.0.1:5000/api/email/oauth2callback"


def _build_oauth_flow(state=None, native=False):
    """Create OAuth flow from env vars (preferred) or credentials file."""
    redirect_uri = _get_redirect_uri() if not native else ""

    # Android requests its server auth code for the web client bundled with
    # the app. During local development, use the matching downloaded Google
    # credentials instead of an unrelated/stale client left in web/.env.
    if native and os.path.exists(Config.GMAIL_CREDENTIALS_FILE):
        return Flow.from_client_secrets_file(
            Config.GMAIL_CREDENTIALS_FILE,
            scopes=GmailService.SCOPES,
            state=state,
            redirect_uri=redirect_uri
        )

    raw_credentials_json = (Config.GMAIL_CREDENTIALS_JSON or '').strip()
    if raw_credentials_json:
        # ... (giữ nguyên logic xử lý candidates)
        candidates = [raw_credentials_json]

        # Remove wrapping quotes if env was pasted as a quoted JSON string
        if (raw_credentials_json.startswith('"') and raw_credentials_json.endswith('"')) or (
            raw_credentials_json.startswith("'") and raw_credentials_json.endswith("'")
        ):
            candidates.append(raw_credentials_json[1:-1])

        # Try base64-decoded variant as well
        try:
            decoded = base64.b64decode(raw_credentials_json).decode('utf-8')
            if decoded:
                candidates.append(decoded)
        except Exception:
            pass

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and 'installed' in parsed and 'web' not in parsed:
                    parsed = {'web': parsed.get('installed', {})}

                if isinstance(parsed, dict) and 'web' in parsed:
                    web_cfg = parsed.get('web') or {}
                    redirect_uris = web_cfg.get('redirect_uris') or []
                    if redirect_uri and redirect_uri not in redirect_uris:
                        web_cfg['redirect_uris'] = redirect_uris + [redirect_uri]
                    parsed['web'] = web_cfg

                return Flow.from_client_config(
                    parsed,
                    scopes=GmailService.SCOPES,
                    state=state,
                    redirect_uri=redirect_uri
                )
            except Exception:
                continue

    client_id = (Config.GMAIL_CLIENT_ID or '').strip()
    client_secret = (Config.GMAIL_CLIENT_SECRET or '').strip()
    if client_id and client_secret:
        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": [redirect_uri]
            }
        }
        return Flow.from_client_config(
            client_config,
            scopes=GmailService.SCOPES,
            state=state,
            redirect_uri=redirect_uri
        )

    if os.path.exists(Config.GMAIL_CREDENTIALS_FILE):
        return Flow.from_client_secrets_file(
            Config.GMAIL_CREDENTIALS_FILE,
            scopes=GmailService.SCOPES,
            state=state,
            redirect_uri=redirect_uri
        )

    raise RuntimeError(
        'Gmail OAuth chưa được cấu hình. Vui lòng set GMAIL_CLIENT_ID/GMAIL_CLIENT_SECRET '
        'hoặc GMAIL_CREDENTIALS_JSON trên Vercel.'
    )


@email_bp.route('/oauth-config-check', methods=['GET'])
def oauth_config_check():
    """Safe diagnostics for OAuth configuration (no secret values)."""
    id_env_presence = {key: bool((os.getenv(key) or '').strip()) for key in GMAIL_CLIENT_ID_KEYS}
    secret_env_presence = {key: bool((os.getenv(key) or '').strip()) for key in GMAIL_CLIENT_SECRET_KEYS}
    json_env_presence = {key: bool((os.getenv(key) or '').strip()) for key in GMAIL_CREDENTIALS_JSON_KEYS}

    return jsonify({
        'success': True,
        'has_client_id': bool((Config.GMAIL_CLIENT_ID or '').strip()),
        'has_client_secret': bool((Config.GMAIL_CLIENT_SECRET or '').strip()),
        'has_credentials_json': bool((Config.GMAIL_CREDENTIALS_JSON or '').strip()),
        'has_credentials_file': os.path.exists(Config.GMAIL_CREDENTIALS_FILE),
        'redirect_uri_preview': _get_redirect_uri(),
        'deployment': {
            'vercel': bool(os.getenv('VERCEL')),
            'vercel_url': os.getenv('VERCEL_URL', ''),
            'host_header': request.headers.get('host', ''),
            'forwarded_host': request.headers.get('x-forwarded-host', '')
        },
        'env_presence': {
            'client_id_keys': id_env_presence,
            'client_secret_keys': secret_env_presence,
            'credentials_json_keys': json_env_presence
        }
    })


@email_bp.route('/get-unread', methods=['GET'])
def get_unread_emails():
    """Get unread emails filtered by selected category with caching and parallel fetching."""
    user_id = get_current_user_id(request, session=session)
    logger.info(f"get_unread_emails: user_id = {user_id}")
    
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

    try:
        scan_limit = _clamp_scan_limit(request.args.get('max_results', EMAIL_SCAN_DEFAULT))
        page = request.args.get('page', 1, type=int)
        filter_type = request.args.get('filter', 'education', type=str).strip().lower()
        search = request.args.get('search', '', type=str).strip()
        include_read = request.args.get('include_read', 'false', type=str).lower() == 'true'
        db_path = get_user_db_path(user_id)
        
        cache_key = _get_cache_key(user_id, filter_type, include_read=include_read, scan_limit=scan_limit)
        db_cache_key = cache_key
        
        # Try in-memory cache first, then DB cache.
        cached_emails, cached_total = _get_cached_emails(cache_key)
        if cached_emails is not None:
            filtered_emails = cached_emails
            total_raw = cached_total
            cache_hit = True
        else:
            cached_db = Cache.get(db_cache_key, db_path=db_path)
            if isinstance(cached_db, dict) and cached_db.get('emails') is not None:
                filtered_emails = cached_db.get('emails') or []
                total_raw = cached_db.get('total', len(filtered_emails))
                _cache_emails(cache_key, filtered_emails, total_raw)
                cache_hit = True
            else:
                raw_emails = service.get_emails(
                    max_results=scan_limit,
                    query='is:unread',
                    include_read=include_read
                )
                logger.info(f"Fetched {len(raw_emails)} raw email metadata records from Gmail")

                hydrated = []
                for email in raw_emails:
                    email = dict(email or {})
                    email['tag'] = _classify_email_lightweight(email)
                    email['tag_confidence'] = 0.65 if email['tag'] != 'other' else 0.0
                    email['summary'] = _compact_preview(email.get('snippet', ''), max_chars=180)
                    email['summary_type'] = 'preview'
                    hydrated.append(email)

                _store_meeting_suggestions(hydrated, db_path)
                filtered_emails = [email for email in hydrated if _matches_filter(email, filter_type)]
                total_raw = len(raw_emails)

                _cache_emails(cache_key, filtered_emails, total_raw)
                Cache.set(db_cache_key, {
                    'emails': filtered_emails,
                    'total': total_raw,
                    'filter': filter_type,
                    'include_read': include_read,
                    'scan_limit': scan_limit,
                    'timestamp': datetime.now().isoformat()
                }, ttl=EMAIL_LIST_CACHE_TTL, db_path=db_path)
                cache_hit = False
        
        if search:
            filtered_emails = [email for email in filtered_emails if _matches_search(email, search)]

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
        _store_meeting_suggestions(page_emails, db_path)

        return jsonify({
            'success': True,
            'filter': filter_type,
            'search': search,
            'emails': page_emails,
            'total_filtered': total_raw,
            'matched_count': total_emails,
            'cache_hit': cache_hit,
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
            'meeting_suggestions': MeetingSuggestion.get_pending(db_path=db_path)
        })
    except Exception as e:
        logger.error(f"Error in get_unread_emails: {str(e)}", exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500


@email_bp.route('/meeting-suggestions', methods=['GET'])
def get_meeting_suggestions():
    user_id = get_current_user_id(request, session=session)
    db_path = get_user_db_path(user_id)
    suggestions = MeetingSuggestion.get_pending(db_path=db_path)
    return jsonify({
        'success': True,
        'suggestions': suggestions,
        'count': len(suggestions),
    })


@email_bp.route('/meeting-suggestions/scan', methods=['POST'])
def scan_meeting_suggestions():
    user_id = get_current_user_id(request, session=session)
    db_path = get_user_db_path(user_id)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    emails = service.get_emails(
        max_results=20,
        query='in:inbox',
        include_read=True,
    )
    detected = _store_meeting_suggestions(emails, db_path)
    pending = MeetingSuggestion.get_pending(db_path=db_path)
    return jsonify({
        'success': True,
        'scanned': len(emails),
        'detected': len(detected),
        'suggestions': pending,
        'count': len(pending),
    })


@email_bp.route('/meeting-suggestions/<int:suggestion_id>/status', methods=['PATCH'])
def update_meeting_suggestion_status(suggestion_id):
    user_id = get_current_user_id(request, session=session)
    db_path = get_user_db_path(user_id)
    data = request.get_json() or {}
    status = str(data.get('status') or '').strip().lower()
    if status not in {'dismissed', 'created'}:
        return jsonify({'error': 'Invalid suggestion status'}), 400
    updated = MeetingSuggestion.update_status(
        suggestion_id,
        status,
        schedule_id=data.get('schedule_id'),
        db_path=db_path,
    )
    if not updated:
        return jsonify({'error': 'Suggestion not found'}), 404
    return jsonify({'success': True, 'status': status})


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


@email_bp.route('/mark-as-read/<email_id>', methods=['POST'])
def mark_email_as_read(email_id):
    """Mark an email as read"""
    user_id = get_current_user_id(request, session=session)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    try:
        success = service.mark_as_read(email_id)
        if success:
            # Clear cache to force refresh
            _clear_email_list_cache(user_id)
            return jsonify({'success': True, 'message': 'Đã đánh dấu đã đọc'})
        return jsonify({'error': 'Failed to mark as read'}), 500
    except Exception as e:
        logger.error(f"Error marking as read: {str(e)}")
        return jsonify({'error': str(e)}), 500


@email_bp.route('/mark-as-unread/<email_id>', methods=['POST'])
def mark_email_as_unread(email_id):
    """Mark an email as unread"""
    user_id = get_current_user_id(request, session=session)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    try:
        success = service.mark_as_unread(email_id)
        if success:
            # Clear cache to force refresh
            _clear_email_list_cache(user_id)
            return jsonify({'success': True, 'message': 'Đã đánh dấu chưa đọc'})
        return jsonify({'error': 'Failed to mark as unread'}), 500
    except Exception as e:
        logger.error(f"Error marking as unread: {str(e)}")
        return jsonify({'error': str(e)}), 500


@email_bp.route('/send-reply', methods=['POST'])
def send_email_reply():
    """Send email reply; requires authentication."""
    user_id = get_current_user_id(request, session=session)
    service = _load_gmail_service(user_id)
    db_path = get_user_db_path(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated', 'auth_url': url_for('email.gmail_auth', _external=True)}), 401

    data = request.get_json()
    to_email = data.get('to', '').strip()
    subject = data.get('subject', '').strip()
    body = data.get('body', '').strip()

    if not all([to_email, subject, body]):
        return jsonify({'error': 'Missing email details'}), 400

    try:
        success = service.send_email(to_email, subject, body)
        if success:
            History.create(f"Gửi email tới {to_email}", body, action_type='email_sent', db_path=db_path)
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to send email'}), 500
    except Exception as e:
        logger.exception("Failed to send email to %s", to_email)
        return jsonify({'error': str(e)}), 500


@email_bp.route('/auth-status', methods=['GET'])
def gmail_auth_status():
    """Return whether Gmail is currently authenticated."""
    user_id = get_current_user_id(request, session=session)
    token_file = get_user_token_file(user_id)
    authenticated = user_id != 'default' and os.path.exists(token_file)
    connected_at = None
    if os.path.exists(token_file):
        try:
            connected_at = os.path.getmtime(token_file)
        except Exception:
            connected_at = None

    return jsonify({
        'success': True,
        'user_id': user_id,
        'gmail_email': session.get('gmail_user_email'),
        'gmail_name': session.get('gmail_user_name'),
        'gmail_picture': session.get('gmail_user_picture'),
        'connected_at': connected_at,
        'authenticated': authenticated
    })


@email_bp.route('/logout', methods=['POST'])
def gmail_logout():
    """Log out Gmail by revoking token (if possible) and clearing local credentials."""
    try:
        user_id = get_current_user_id(request, session=session)
        token_file = get_user_token_file(user_id)

        # Best-effort revoke
        if os.path.exists(token_file):
            try:
                with open(token_file, 'rb') as token_handle:
                    creds = pickle.load(token_handle)
                token_value = getattr(creds, 'token', None)
                if token_value:
                    requests.post(
                        'https://oauth2.googleapis.com/revoke',
                        params={'token': token_value},
                        headers={'content-type': 'application/x-www-form-urlencoded'},
                        timeout=8
                    )
            except Exception as revoke_err:
                print(f"Token revoke skipped: {revoke_err}")

        User.update(user_id, gmail_connected=0)
        _clear_oauth_state(user_id)
        return jsonify({'success': True, 'message': 'Đã đăng xuất Gmail'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@email_bp.route('/summarize-by-date', methods=['POST'])
def summarize_emails_by_date():
    """Summarize emails received on a specific date and return tabular report with caching."""
    user_id = get_current_user_id(request, session=session)
    db_path = get_user_db_path(user_id)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated', 'auth_url': url_for('email.gmail_auth', _external=True)}), 401

    data = request.get_json() or {}
    date_str = (data.get('date') or '').strip()
    max_results = int(data.get('max_results', 20))

    if not date_str:
        return jsonify({'error': 'Missing date. Expected format dd/mm/yyyy'}), 400

    try:
        emails = service.get_emails_by_date(date_str, max_results=max_results)
        if not emails:
            return jsonify({
                'success': True,
                'date': date_str,
                'total_emails': 0,
                'rows': []
            })

        # Try to read cached report first
        cache_key = f"email_report::{user_id}::{date_str}"
        rows = None
        try:
            from models.cache import Cache
            cached = Cache.get(cache_key, db_path=db_path)
            if cached:
                logger.info(f"Using cached summary for {date_str}")
                rows = cached
        except Exception as e:
            logger.debug(f"Cache read error: {e}")

        # Generate summary if not cached
        if not rows:
            rows = ai_service.summarize_email_report(emails, report_date=date_str, user_id=user_id)
            # Cache the results for future use (24 hour TTL)
            try:
                from models.cache import Cache
                Cache.set(cache_key, rows, db_path=db_path, ttl=86400)
                logger.info(f"Cached summary for {date_str}")
            except Exception as e:
                logger.debug(f"Cache write error: {e}")

        report_details = []
        for index, row in enumerate(rows, start=1):
            detail = [
                f"{index}. {row.get('subject') or '(Không có tiêu đề)'}",
                f"Người gửi: {row.get('sender') or 'Không xác định'}",
                f"Tóm tắt: {row.get('summary') or 'Không có tóm tắt'}",
            ]
            if row.get('is_meeting'):
                detail.append(
                    f"Gợi ý lịch: {row.get('meeting_note') or row.get('schedule_title') or 'Có nội dung liên quan đến lịch hẹn'}"
                )
            report_details.append("\n".join(detail))

        History.create(
            f"Báo cáo tóm tắt email theo ngày {date_str}",
            f"Tổng {len(rows)} email đã được tóm tắt\n\n" + "\n\n".join(report_details),
            action_type='email_daily_summary',
            db_path=db_path
        )

        return jsonify({
            'success': True,
            'date': date_str,
            'total_emails': len(emails),
            'rows': rows
        })
    except Exception as e:
        logger.exception("Failed to summarize emails for date %s", date_str)
        return jsonify({'error': str(e)}), 500


# OAuth flow endpoints


@email_bp.route('/google-auth', methods=['POST'])
def google_auth_native():
    """Authenticate user from Android using Server Auth Code to get full Gmail access"""
    data = request.get_json()
    auth_code = data.get('server_auth_code')
    email_hint = data.get('email')

    if not auth_code:
        return jsonify({'success': False, 'error': 'Missing server_auth_code'}), 400

    try:
        # Build the flow to exchange the code for tokens.
        # For native Android exchange, redirect_uri must be empty.
        flow = _build_oauth_flow(native=True)
        flow.fetch_token(code=auth_code)
        creds = flow.credentials

        # Identify Gmail account email from profile
        gmail_service_api = build('gmail', 'v1', credentials=creds)
        profile = gmail_service_api.users().getProfile(userId='me').execute()
        gmail_email = profile.get('emailAddress', email_hint or '')

        # Fetch richer account profile for UI
        userinfo = _fetch_google_userinfo(creds)
        gmail_name = userinfo.get('name', 'Teacher')
        gmail_picture = userinfo.get('picture', '')

        user_id = gmail_email or 'default'

        # Save token to file (Crucial for _load_gmail_service)
        token_file = get_user_token_file(user_id)
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)

        # Update User in Database
        db_path = get_user_db_path(user_id)
        User.get_or_create(user_id, name=gmail_name, email=gmail_email)
        User.update(
            user_id,
            gmail_email=gmail_email,
            gmail_name=gmail_name,
            gmail_picture=gmail_picture,
            gmail_connected=1,
            gmail_connected_at=datetime.now().isoformat(),
            avatar_url=gmail_picture,
            name=gmail_name,
            email=gmail_email
        )

        # Initialize user-specific components
        try:
            Schedule.init_db(db_path=db_path)
            History.init_db(db_path=db_path)
        except Exception:
            pass

        # Set session
        session['user_id'] = user_id
        session['gmail_user_email'] = gmail_email
        session.modified = True

        logger.info(f"Native Google Auth & Token exchange successful for: {user_id}")
        return jsonify({
            'success': True,
            'user_id': user_id,
            'email': gmail_email,
            'access_token': issue_mobile_token(user_id),
            'message': 'Đăng nhập và cấp quyền thành công'
        })

    except Exception as e:
        logger.error(f"Native Auth/Exchange error: {e}", exc_info=True)
        error_message = str(e)
        if 'unauthorized_client' in error_message.lower():
            error_message = (
                'Google OAuth client mismatch. The Android app and backend '
                'must use the same Web OAuth client ID.'
            )
        return jsonify({'success': False, 'error': error_message}), 500


@email_bp.route('/auth', methods=['GET'])
def gmail_auth():
    """Initiate OAuth2 login flow."""
    try:
        flow = _build_oauth_flow()
    except Exception as e:
        return jsonify({'error': str(e)}), 503

    auth_url, state = flow.authorization_url(
        access_type='offline',
        prompt='select_account consent'
    )
    # store the state and PKCE code_verifier in session; do not pickle the flow object
    session['oauth_state'] = state
    # try to capture code_verifier used for PKCE (name may differ by implementation)
    try:
        code_verifier = getattr(flow, 'code_verifier', None)
        if not code_verifier and hasattr(flow, '_client'):
            code_verifier = getattr(flow._client, 'code_verifier', None)
        if code_verifier:
            session['oauth_code_verifier'] = code_verifier
    except Exception:
        pass
    return redirect(auth_url)


@email_bp.route('/oauth2callback', methods=['GET'])
def oauth2callback():
    """Handle redirect from Google and store credentials."""
    logger.info("OAuth2 callback invoked")

    # Rebuild the Flow using the stored state and client secrets
    state = session.get('oauth_state') or (request.args.get('state') or '').strip()
    if not state:
        logger.error("OAuth state not found in session")
        return jsonify({'error': 'flow_not_initialized', 'message': 'OAuth state expired or missing'}), 400

    try:
        flow = _build_oauth_flow(state=state)
    except Exception as e:
        logger.error(f"Failed to build OAuth flow: {e}")
        return jsonify({'error': str(e)}), 503

    # restore PKCE code_verifier from session if present
    code_verifier = session.get('oauth_code_verifier')
    try:
        if code_verifier:
            try:
                setattr(flow, 'code_verifier', code_verifier)
            except Exception:
                pass
            if hasattr(flow, '_client'):
                try:
                    setattr(flow._client, 'code_verifier', code_verifier)
                except Exception:
                    pass
    except Exception:
        pass

    try:
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials
    except Exception as e:
        logger.error(f"Failed to fetch token: {e}")
        return jsonify({'error': 'token_fetch_failed', 'message': str(e)}), 400

    # Clear transient OAuth state only after a successful token exchange.
    try:
        session.pop('oauth_state', None)
        session.pop('oauth_code_verifier', None)
    except Exception:
        pass

    try:
        # Identify Gmail account email from profile
        gmail_service = build('gmail', 'v1', credentials=creds)
        profile = gmail_service.users().getProfile(userId='me').execute()
        gmail_email = profile.get('emailAddress', '')
        logger.info(f"Gmail profile retrieved: {gmail_email}")

        # Fetch richer account profile for UI
        userinfo = _fetch_google_userinfo(creds)
        people_profile = _fetch_google_people_profile(creds)
        gmail_name = userinfo.get('name', '')
        gmail_picture = userinfo.get('picture', '')
        if userinfo.get('email'):
            gmail_email = userinfo.get('email')

        if people_profile.get('name'):
            gmail_name = people_profile.get('name')
        if people_profile.get('email'):
            gmail_email = people_profile.get('email')
        if people_profile.get('picture'):
            gmail_picture = people_profile.get('picture')

        user_id = gmail_email or 'default'
        logger.info(f"Setting session for user: {user_id}")

        # Save token
        token_file = get_user_token_file(user_id)
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
        logger.info(f"Token saved for user: {token_file}")

        # Save user info to database and initialize per-user DB
        db_path = get_user_db_path(user_id)
        user = User.get_or_create(user_id, name=gmail_name or 'Teacher', email=gmail_email)
        # Update both Gmail-specific fields and common profile fields so frontend
        # that reads `avatar_url`, `name`, or `email` sees up-to-date data.
        User.update(
            user_id,
            gmail_email=gmail_email,
            gmail_name=gmail_name,
            gmail_picture=gmail_picture,
            gmail_connected=1,
            gmail_connected_at=datetime.now().isoformat(),
            avatar_url=gmail_picture,
            name=(gmail_name or (user.get('name') if user else gmail_name)),
            email=(gmail_email or (user.get('email') if user else gmail_email))
        )

        # Initialize per-user databases (schedules, history, cache) so related
        # features work immediately after login.
        try:
            Schedule.init_db(db_path=db_path)
        except Exception:
            pass
        try:
            History.init_db(db_path=db_path)
        except Exception:
            pass
        logger.info(f"User info saved for: {user_id}")

        # Clear cache for emails when new user connects
        Cache.clear_pattern(f"{user_id}:*", db_path=db_path)

        # Set session variables and mark session modified so Flask persists them
        session['gmail_user_email'] = gmail_email
        session['gmail_user_name'] = gmail_name
        session['gmail_user_picture'] = gmail_picture
        session['user_id'] = user_id
        try:
            session.modified = True
        except Exception:
            pass

        logger.info(f"Session variables set. Email: {gmail_email}, Name: {gmail_name}")

        # Return HTML page that notifies the opener or redirects back to SPA
        html = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Gmail Connected</title>
  </head>
  <body>
    <script>
      try {
        if (window.opener && typeof window.opener.postMessage === 'function') {
          window.opener.postMessage({type: 'gmail_auth', status: 'success'}, window.location.origin);
          window.close();
        } else {
          window.location.replace('/?gmail_auth=success');
        }
      } catch (e) {
        window.location.replace('/?gmail_auth=success');
      }
    </script>
    <p>Đang chuyển hướng...</p>
  </body>
</html>
"""
        from flask import Response
        return Response(html, mimetype='text/html')
    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)
        return jsonify({'error': 'callback_error', 'message': str(e)}), 500


@email_bp.route('/auth_url', methods=['GET'])
def gmail_auth_url():
    """Return the OAuth authorization URL (JSON) so frontend can redirect."""
    try:
        flow = _build_oauth_flow()
    except Exception as e:
        return jsonify({'error': str(e)}), 503

    auth_url, state = flow.authorization_url(
        access_type='offline',
        prompt='select_account consent'
    )
    session['oauth_state'] = state
    # store PKCE verifier as well so callback can exchange token
    try:
        code_verifier = getattr(flow, 'code_verifier', None)
        if not code_verifier and hasattr(flow, '_client'):
            code_verifier = getattr(flow._client, 'code_verifier', None)
        if code_verifier:
            session['oauth_code_verifier'] = code_verifier
    except Exception:
        pass
    return jsonify({'auth_url': auth_url})


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
 
