"""OAuth login/session flow: state + PKCE storage, the Google Flow builder,
profile/avatar fetch helpers, and every /api/email/{auth,...} route.

Split out of the former monolithic routes/email.py -- see
routes/email/__init__.py for the package-level overview.
"""
import base64
import json
import logging
import os
from threading import Lock
from urllib.parse import urlencode

import requests
from flask import jsonify, redirect, request, session
from datetime import datetime

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from config import Config
from config import GMAIL_CLIENT_ID_KEYS, GMAIL_CLIENT_SECRET_KEYS, GMAIL_CREDENTIALS_JSON_KEYS
from models import postgres_db as pg
from models.cache import Cache
from models.history import History
from models.schedule import Schedule
from models.user import User
from routes.admin import is_current_user_admin
from services.gmail_service import GmailService, get_cached_gmail_service
from utils.google_service_cache import invalidate_cached_service
from utils.security import issue_mobile_token
from utils.user_context import (
    delete_google_credentials,
    get_current_user_id,
    get_user_db_path,
    get_user_token_file,
    inspect_google_credentials,
    persist_google_credentials,
    read_local_credentials,
    resolve_google_user_id,
)

from routes.email.shared import email_bp

# Configure module logger
logger = logging.getLogger(__name__)

OAUTH_STATE_TTL_SECONDS = 1800
_oauth_state_lock = Lock()


def _oauth_state_file():
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    return os.path.join(Config.DATA_DIR, 'oauth_states.json')


def _read_oauth_states():
    path = _oauth_state_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_oauth_states(data):
    path = _oauth_state_file()
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(data, handle)


def _store_oauth_code_verifier(state, code_verifier):
    if not state or not code_verifier:
        return
    if pg.enabled():
        with pg.connection() as conn:
            conn.execute(
                "DELETE FROM oauth_states WHERE created_at < NOW() - (%s * INTERVAL '1 second')",
                (OAUTH_STATE_TTL_SECONDS,),
            )
            conn.execute(
                """
                INSERT INTO oauth_states (state, code_verifier)
                VALUES (%s, %s)
                ON CONFLICT (state) DO UPDATE SET code_verifier = EXCLUDED.code_verifier
                """,
                (state, code_verifier),
            )
        return

    now = datetime.utcnow().timestamp()
    with _oauth_state_lock:
        data = _read_oauth_states()
        data = {
            key: value for key, value in data.items()
            if isinstance(value, dict)
            and now - float(value.get('created_at') or 0) <= OAUTH_STATE_TTL_SECONDS
        }
        data[state] = {
            'code_verifier': code_verifier,
            'created_at': now,
        }
        _write_oauth_states(data)


def _consume_oauth_state(state):
    """Atomically consume a server-issued OAuth transaction."""
    missing = {
        'found': False,
        'code_verifier': None,
        'mobile': False,
    }
    if not state:
        return missing
    if pg.enabled():
        with pg.connection() as conn:
            row = conn.execute(
                """
                DELETE FROM oauth_states
                WHERE state = %s AND created_at >= NOW() - (%s * INTERVAL '1 second')
                RETURNING code_verifier, mobile
                """,
                (state, OAUTH_STATE_TTL_SECONDS),
            ).fetchone()
        if not row:
            return missing
        return {
            'found': True,
            'code_verifier': row['code_verifier'],
            'mobile': bool(row['mobile']),
        }

    now = datetime.utcnow().timestamp()
    with _oauth_state_lock:
        data = _read_oauth_states()
        record = data.pop(state, None)
        data = {
            key: value for key, value in data.items()
            if isinstance(value, dict)
            and now - float(value.get('created_at') or 0) <= OAUTH_STATE_TTL_SECONDS
        }
        _write_oauth_states(data)
    if not isinstance(record, dict):
        return missing
    if now - float(record.get('created_at') or 0) > OAUTH_STATE_TTL_SECONDS:
        return missing
    return {
        'found': True,
        'code_verifier': record.get('code_verifier'),
        'mobile': bool(record.get('mobile')),
    }


def _mark_oauth_mobile(state):
    """Flag an OAuth state as started by the mobile app, so oauth2callback
    knows to hand the result back via a deep link (access_token in the URL)
    instead of the cookie/postMessage page built for the web app -- the
    mobile app's fetch() never shares cookies with the system browser that
    completes this flow. Stored in the shared DB (not a local file): the
    request that starts the flow and the request Google redirects back to
    can land on different backend instances behind the load balancer.
    """
    if not state:
        return
    if pg.enabled():
        with pg.connection() as conn:
            conn.execute(
                """
                INSERT INTO oauth_states (state, mobile)
                VALUES (%s, TRUE)
                ON CONFLICT (state) DO UPDATE SET mobile = TRUE
                """,
                (state,),
            )
        return

    now = datetime.utcnow().timestamp()
    with _oauth_state_lock:
        data = _read_oauth_states()
        data = {
            key: value for key, value in data.items()
            if isinstance(value, dict)
            and now - float(value.get('created_at') or 0) <= OAUTH_STATE_TTL_SECONDS
        }
        record = data.get(state) if isinstance(data.get(state), dict) else {'created_at': now}
        record['mobile'] = True
        data[state] = record
        _write_oauth_states(data)


def _is_oauth_mobile(state):
    if not state:
        return False
    if pg.enabled():
        with pg.connection() as conn:
            row = conn.execute(
                """
                SELECT mobile FROM oauth_states
                WHERE state = %s AND created_at >= NOW() - (%s * INTERVAL '1 second')
                """,
                (state, OAUTH_STATE_TTL_SECONDS),
            ).fetchone()
        return bool(row and row['mobile'])

    data = _read_oauth_states()
    record = data.get(state)
    return bool(isinstance(record, dict) and record.get('mobile'))


def _get_flow_code_verifier(flow):
    code_verifier = getattr(flow, 'code_verifier', None)
    if not code_verifier and hasattr(flow, '_client'):
        code_verifier = getattr(flow._client, 'code_verifier', None)
    return code_verifier


def _set_flow_code_verifier(flow, code_verifier):
    if not code_verifier:
        return
    try:
        setattr(flow, 'code_verifier', code_verifier)
    except Exception:
        pass
    if hasattr(flow, '_client'):
        try:
            setattr(flow._client, 'code_verifier', code_verifier)
        except Exception:
            pass


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
            'picture': data.get('picture', ''),
            'subject': data.get('sub') or data.get('id') or '',
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
    """Return a cached GmailService instance if credentials token exists."""
    if not user_id or user_id == 'default':
        return None
    token_file = get_user_token_file(user_id)
    if os.path.exists(token_file):
        try:
            return get_cached_gmail_service(token_file)
        except Exception as e:
            logger.warning(f"Error creating GmailService for {user_id}: {e}")
    return None


def _clear_oauth_state(user_id):
    """Clear OAuth token/session so another user can sign in."""
    token_file = delete_google_credentials(user_id)
    invalidate_cached_service(token_file)

    # Clear oauth session keys
    session.pop('oauth_state', None)
    session.pop('oauth_code_verifier', None)
    session.pop('oauth_user_id', None)
    session.pop('gmail_user_email', None)
    session.pop('gmail_user_name', None)
    session.pop('gmail_user_picture', None)
    session.pop('user_id', None)
    # A Gmail logout/account switch must also invalidate any elevated admin
    # TOTP session.  Otherwise the same browser could retain the admin gate
    # until its timeout after the Google identity was disconnected.
    session.pop('admin_totp_user', None)
    session.pop('admin_totp_verified_at', None)
    session.modified = True


def _get_redirect_uri():
    """Return the redirect URI registered in Google Console for this client."""
    configured_uri = (Config.GMAIL_REDIRECT_URI or '').strip()
    deployed = bool(
        os.getenv('VERCEL')
        or os.getenv('RAILWAY_ENVIRONMENT')
        or os.getenv('RAILWAY_PROJECT_ID')
    )
    if configured_uri:
        configured_lower = configured_uri.lower()
        is_local_uri = (
            configured_lower.startswith('http://127.0.0.1')
            or configured_lower.startswith('http://localhost')
        )
        if not (deployed and is_local_uri):
            return configured_uri

    forwarded_proto = request.headers.get('x-forwarded-proto', '').split(',')[0].strip()
    forwarded_host = request.headers.get('x-forwarded-host', '').split(',')[0].strip()
    scheme = forwarded_proto or request.scheme
    host = forwarded_host or request.host

    if deployed:
        scheme = 'https'
        host = host or os.getenv('VERCEL_URL', '') or os.getenv('RAILWAY_PUBLIC_DOMAIN', '')

    if scheme and host:
        return f"{scheme}://{host}/api/email/oauth2callback"

    return "http://127.0.0.1:5000/api/email/oauth2callback"


def _is_local_oauth_request():
    configured_uri = (Config.GMAIL_REDIRECT_URI or '').strip().lower()
    host = (request.host or '').split(':')[0].lower()
    return (
        Config.DEBUG
        or configured_uri.startswith('http://127.0.0.1')
        or configured_uri.startswith('http://localhost')
        or host in {'127.0.0.1', 'localhost'}
    )


def _allow_insecure_oauth_for_local_request():
    if _is_local_oauth_request():
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


def _build_oauth_flow(state=None, native=False):
    """Create OAuth flow from env vars (preferred) or credentials file."""
    if not native:
        _allow_insecure_oauth_for_local_request()
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
        'hoặc GMAIL_CREDENTIALS_JSON trong biến môi trường của nơi deploy.'
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
            'railway': bool(os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RAILWAY_PROJECT_ID')),
            'railway_environment': os.getenv('RAILWAY_ENVIRONMENT', ''),
            'railway_public_domain': os.getenv('RAILWAY_PUBLIC_DOMAIN', ''),
            'host_header': request.headers.get('host', ''),
            'forwarded_host': request.headers.get('x-forwarded-host', '')
        },
        'env_presence': {
            'client_id_keys': id_env_presence,
            'client_secret_keys': secret_env_presence,
            'credentials_json_keys': json_env_presence
        }
    })


@email_bp.route('/auth-status', methods=['GET'])
def gmail_auth_status():
    """Return whether Gmail is currently authenticated."""
    user_id = get_current_user_id(request, session=session)
    credential_status = inspect_google_credentials(user_id, refresh=True)
    token_file = credential_status['token_file']
    authenticated = user_id != 'default' and credential_status['valid']
    connected_at = None
    google_scopes = credential_status['scopes']
    calendar_write_connected = (
        'https://www.googleapis.com/auth/calendar.events' in google_scopes
    )
    if os.path.exists(token_file):
        try:
            connected_at = os.path.getmtime(token_file)
        except Exception:
            connected_at = None

    user = User.get(user_id) or {}

    return jsonify({
        'success': True,
        'user_id': user_id,
        'gmail_email': session.get('gmail_user_email') or user.get('gmail_email') or user.get('email'),
        'gmail_name': session.get('gmail_user_name') or user.get('gmail_name') or user.get('name'),
        'gmail_picture': session.get('gmail_user_picture') or user.get('gmail_picture') or user.get('avatar_url'),
        'connected_at': connected_at,
        'authenticated': authenticated,
        'needs_reauth': credential_status['has_token'] and not credential_status['valid'],
        'credential_error': credential_status['error'],
        'token_refreshed': credential_status['refreshed'],
        'google_scopes': google_scopes,
        'calendar_write_connected': calendar_write_connected,
        'is_admin': bool(authenticated and is_current_user_admin())
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
                creds = read_local_credentials(token_file)
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

        # Resolve the immutable Google subject to the same canonical workspace
        # id used by both browser sessions and APK Bearer tokens.
        user_id = resolve_google_user_id(
            userinfo.get('subject'),
            gmail_email,
        )

        # Save token durably for Railway and cache it locally for this worker.
        persist_google_credentials(user_id, creds, account_email=gmail_email)

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
    return_to = (request.args.get('next') or '').strip()
    if return_to in {'/admin', '/admin/login'}:
        session['oauth_return_to'] = return_to
    try:
        flow = _build_oauth_flow()
    except Exception as e:
        return jsonify({'error': str(e)}), 503

    auth_url, state = flow.authorization_url(
        access_type='offline',
        prompt='select_account consent',
        include_granted_scopes='true'
    )
    # store the state and PKCE code_verifier in session; do not pickle the flow object
    session['oauth_state'] = state
    # try to capture code_verifier used for PKCE (name may differ by implementation)
    try:
        code_verifier = _get_flow_code_verifier(flow)
        if code_verifier:
            session['oauth_code_verifier'] = code_verifier
            _store_oauth_code_verifier(state, code_verifier)
        session.modified = True
    except Exception:
        pass
    return redirect(auth_url)


@email_bp.route('/oauth2callback', methods=['GET'])
def oauth2callback():
    """Handle redirect from Google and store credentials."""
    logger.info("OAuth2 callback invoked")

    # Google's callback state identifies the exact flow. A browser can start
    # another web login while an APK system-browser flow is still open; in
    # that case the cookie's latest state belongs to a different transaction.
    request_state = (request.args.get('state') or '').strip()
    session_state = str(session.get('oauth_state') or '').strip()
    state = request_state or session_state
    if not state:
        logger.error("OAuth state not found in session")
        return jsonify({'error': 'flow_not_initialized', 'message': 'OAuth state expired or missing'}), 400

    try:
        flow = _build_oauth_flow(state=state)
    except Exception as e:
        logger.error(f"Failed to build OAuth flow: {e}")
        return jsonify({'error': str(e)}), 503

    # A callback is valid only when its state is backed by the browser session
    # that started it or by a shared state row issued for a mobile/cross-worker
    # flow. Consuming the row atomically rejects unknown and replayed states.
    issued_state = _consume_oauth_state(state)
    session_matches = bool(session_state and session_state == state)
    if not session_matches and not issued_state['found']:
        logger.warning("Rejected unknown or replayed OAuth state")
        return jsonify({
            'error': 'invalid_oauth_state',
            'message': 'OAuth state is invalid, expired, or already used',
        }), 400

    is_mobile_flow = issued_state['mobile']
    session_code_verifier = (
        session.get('oauth_code_verifier')
        if session_matches
        else None
    )
    code_verifier = issued_state['code_verifier'] or session_code_verifier
    try:
        _set_flow_code_verifier(flow, code_verifier)
    except Exception:
        pass

    try:
        fetch_kwargs = {'authorization_response': request.url}
        if code_verifier:
            fetch_kwargs['code_verifier'] = code_verifier
        flow.fetch_token(**fetch_kwargs)
        creds = flow.credentials
    except Exception as e:
        logger.error(f"Failed to fetch token: {e}")
        return jsonify({'error': 'token_fetch_failed', 'message': str(e)}), 400

    # Clear transient OAuth state only after a successful token exchange.
    if session_state == state:
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

        # Resolve the immutable Google subject to the same canonical workspace
        # id used by both browser sessions and APK Bearer tokens.
        user_id = resolve_google_user_id(
            userinfo.get('subject'),
            gmail_email,
        )
        logger.info(f"Setting session for user: {user_id}")

        # Save token durably for Railway and cache it locally for this worker.
        token_file = persist_google_credentials(user_id, creds, account_email=gmail_email)
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

        # The mobile app started this flow in a system browser that doesn't
        # share cookies with its own fetch() calls, so it can't pick up the
        # session set above. Hand it a signed mobile access token via a deep
        # link instead -- WebBrowser.openAuthSessionAsync on the app side
        # captures this redirect and reads the token straight from the URL.
        if is_mobile_flow:
            token_query = urlencode({
                'access_token': issue_mobile_token(user_id),
                'user_id': user_id,
                'email': gmail_email,
            })
            return redirect(f"{Config.MOBILE_OAUTH_REDIRECT_URL}?{token_query}")

        # Return HTML page that notifies the opener or redirects back to SPA
        return_to = session.pop('oauth_return_to', '/app?gmail_auth=success')
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
          window.location.replace(__RETURN_TO__);
        }
      } catch (e) {
        window.location.replace(__RETURN_TO__);
      }
    </script>
    <p>Đang chuyển hướng...</p>
  </body>
</html>
""".replace('__RETURN_TO__', json.dumps(return_to))
        from flask import Response
        return Response(html, mimetype='text/html')
    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)
        return jsonify({'error': 'callback_error', 'message': str(e)}), 500


@email_bp.route('/auth_url', methods=['GET'])
def gmail_auth_url():
    """Return the OAuth authorization URL (JSON) so frontend can redirect."""
    return_to = (request.args.get('next') or '').strip()
    if return_to in {'/admin', '/admin/login'}:
        session['oauth_return_to'] = return_to
    try:
        flow = _build_oauth_flow()
    except Exception as e:
        return jsonify({'error': str(e)}), 503

    auth_url, state = flow.authorization_url(
        access_type='offline',
        prompt='select_account consent',
        include_granted_scopes='true'
    )
    session['oauth_state'] = state
    # store PKCE verifier as well so callback can exchange token
    try:
        code_verifier = _get_flow_code_verifier(flow)
        if code_verifier:
            session['oauth_code_verifier'] = code_verifier
            _store_oauth_code_verifier(state, code_verifier)
        session.modified = True
    except Exception:
        pass
    # The mobile app's fetch() never shares cookies with the system browser
    # that completes this flow, so oauth2callback needs to know to hand the
    # result back via a deep link instead of the cookie/postMessage page.
    # Call this AFTER _store_oauth_code_verifier (it merges into the same
    # record rather than overwriting it).
    if (request.args.get('platform') or '').strip().lower() == 'mobile':
        _mark_oauth_mobile(state)
    return jsonify({'auth_url': auth_url})
