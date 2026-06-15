import os
import sys
import logging
import pickle
import json
import base64
import requests
from flask import Blueprint, request, jsonify, redirect, url_for, session
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from services.gmail_service import GmailService
from services.mistral_service import MistralService
from services.ai_service import AIService
from models.history import History
from models.schedule import Schedule
from models.user import User
from models.cache import Cache
from config import Config
from config import GMAIL_CLIENT_ID_KEYS, GMAIL_CLIENT_SECRET_KEYS, GMAIL_CREDENTIALS_JSON_KEYS
from utils.user_context import get_current_user_id, get_user_db_path, get_user_token_file

# Configure module logger
logger = logging.getLogger(__name__)

# Email-related endpoints including OAuth login and Gmail access
email_bp = Blueprint('email', __name__, url_prefix='/api/email')

# Initialize services
mistral_service = MistralService()
ai_service = AIService()

# Simple in-memory cache for email lists (5 minute TTL)
_email_cache = {}

def _get_cache_key(user_id, filter_type):
    """Generate cache key"""
    return f"{user_id}:{filter_type}"

def _are_emails_cached(cache_key):
    """Check if cache is still valid"""
    if cache_key not in _email_cache:
        return False
    cached_time, _, _ = _email_cache[cache_key]
    return datetime.now() - cached_time < timedelta(minutes=5)

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
    """Return configured redirect URI or build from request."""
    configured = (getattr(Config, 'GMAIL_REDIRECT_URI', None) or '').strip()
    if configured:
        # Prevent localhost redirect leak when running on Vercel
        if not (os.getenv('VERCEL') and 'localhost' in configured.lower()):
            return configured

    # Prefer forwarded host/proto from reverse proxy (Vercel)
    forwarded_host = request.headers.get('x-forwarded-host', '').strip()
    forwarded_proto = request.headers.get('x-forwarded-proto', '').strip() or 'https'
    if forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}/api/email/oauth2callback"

    # Fallback to Flask-generated URL
    return url_for('email.oauth2callback', _external=True)


def _build_oauth_flow(state=None):
    """Create OAuth flow from env vars (preferred) or credentials file."""
    redirect_uri = _get_redirect_uri()

    raw_credentials_json = (Config.GMAIL_CREDENTIALS_JSON or '').strip()
    if raw_credentials_json:
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
        max_results = request.args.get('max_results', 10, type=int)
        page = request.args.get('page', 1, type=int)
        filter_type = request.args.get('filter', 'education', type=str).strip().lower()
        include_read = request.args.get('include_read', 'false', type=str).lower() == 'true'
        
        cache_key = _get_cache_key(user_id, filter_type)
        
        # Try to get from cache first (only for unread emails)
        cached_emails, cached_total = _get_cached_emails(cache_key) if not include_read else (None, None)
        if cached_emails is not None:
            filtered_emails = cached_emails
            total_raw = cached_total
            cache_hit = True
        else:
            # Fetch from Gmail with lazy body loading
            fetch_count = max_results if filter_type == 'all' else min(max_results * 4, 80)
            raw_emails = service.get_emails(max_results=fetch_count, query='is:unread', include_read=include_read)
            
            logger.info(f"Fetched {len(raw_emails)} raw emails from Gmail")
            
            # Bypass AI classification for now - just return all emails
            # TODO: Fix Mistral service if needed
            if filter_type == 'all' or len(raw_emails) == 0:
                filtered_emails = raw_emails
            else:
                try:
                    filtered_emails = mistral_service.batch_classify_emails(raw_emails, filter_type=filter_type)
                    logger.info(f"AI filtered to {len(filtered_emails)} emails")
                except Exception as e:
                    logger.warning(f"AI classification failed, returning all: {e}")
                    filtered_emails = raw_emails
            
            total_raw = len(raw_emails)
            
            # Cache the results (both in-memory and database)
            _cache_emails(cache_key, filtered_emails, total_raw)
            
            # Also save to database cache
            db_path = get_user_db_path(user_id)
            db_cache_key = f"{user_id}:emails:{filter_type}"
            Cache.set(db_cache_key, {
                'emails': filtered_emails,
                'total': total_raw,
                'filter': filter_type,
                'timestamp': datetime.now().isoformat()
            }, ttl=300, db_path=db_path)  # 5 minute TTL
            
            cache_hit = False
        
        # Calculate pagination
        total_emails = len(filtered_emails)
        total_pages = (total_emails + max_results - 1) // max_results
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        
        # Get page emails
        offset = (page - 1) * max_results
        page_emails = filtered_emails[offset:offset + max_results]
        
        return jsonify({
            'success': True,
            'filter': filter_type,
            'emails': page_emails,
            'total_filtered': total_raw,
            'matched_count': total_emails,
            'cache_hit': cache_hit,
            'debug': {
                'raw_email_count': total_raw,
                'filtered_email_count': total_emails,
                'current_page_items': len(page_emails)
            },
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'per_page': max_results,
                'total_items': total_emails
            }
        })
    except Exception as e:
        logger.error(f"Error in get_unread_emails: {str(e)}", exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500


@email_bp.route('/get-email-body/<email_id>', methods=['GET'])
def get_email_body(email_id):
    """Get full email body on-demand (lazy loading for performance)"""
    user_id = get_current_user_id(request, session=session)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    try:
        email_data = service.get_email_details(email_id, lazy=False)
        if email_data:
            return jsonify({
                'success': True,
                'body': email_data.get('body', '')
            })
        return jsonify({'error': 'Email not found'}), 404
    except Exception as e:
        logger.error(f"Error getting email body: {str(e)}")
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
            _clear_all_cache(user_id)
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
            _clear_all_cache(user_id)
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
        return jsonify({'error': str(e)}), 500


@email_bp.route('/auth-status', methods=['GET'])
def gmail_auth_status():
    """Return whether Gmail is currently authenticated."""
    user_id = get_current_user_id(request, session=session)
    token_file = get_user_token_file(user_id)
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
        'authenticated': os.path.exists(token_file)
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

        _clear_oauth_state(user_id)
        return jsonify({'success': True, 'message': 'Đã đăng xuất Gmail'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@email_bp.route('/summarize-by-date', methods=['POST'])
def summarize_emails_by_date():
    """Summarize emails received on a specific date and return tabular report."""
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
        try:
            from models.cache import Cache
            cached = Cache.get(f"email_report::{user_id}::{date_str}", db_path=db_path)
            if cached:
                rows = cached
            else:
                rows = ai_service.summarize_email_report(emails, report_date=date_str, user_id=user_id)
        except Exception:
            rows = ai_service.summarize_email_report(emails, report_date=date_str, user_id=user_id)

        History.create(
            f"Báo cáo tóm tắt email theo ngày {date_str}",
            f"Tổng {len(rows)} email đã được tóm tắt",
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
        return jsonify({'error': str(e)}), 500


# OAuth flow endpoints


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
        # Clear in-memory cache
        _clear_all_cache(user_id)
        # Clear database cache for email caches and AI caches
        Cache.clear_pattern(f"{user_id}:*", db_path=db_path)
        # ai cache keys are stored as: ai::{user_id}::{hash}
        Cache.clear_pattern(f"ai::{user_id}:%", db_path=db_path)
        
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
 
