"""OAuth login/session flow: state + PKCE storage, the Google Flow builder,
profile/avatar fetch helpers, and every /api/email/{auth,...} route.

Split out of the former monolithic routes/email.py -- see
routes/email/__init__.py for the package-level overview.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
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
from utils.security import authenticated_user_id, issue_mobile_token
from utils.user_context import (
    delete_google_credentials,
    get_current_user_id,
    get_user_db_path,
    get_user_token_file,
    inspect_google_credentials,
    lookup_google_identity_owner,
    persist_google_credentials,
    read_local_credentials,
    upsert_google_identity,
)

from routes.email.shared import email_bp

# Configure module logger
logger = logging.getLogger(__name__)

OAUTH_STATE_TTL_SECONDS = 1800
_oauth_state_lock = Lock()

# Short-lived on purpose: an app that's mid-flow finishes this round trip in
# a few seconds (deep link delivered, immediately POSTed back), so there is
# no legitimate reason for an exchange code to still be valid a couple
# minutes later.
OAUTH_EXCHANGE_TTL_SECONDS = 120
_oauth_exchange_lock = Lock()


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


def _oauth_exchange_file():
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    return os.path.join(Config.DATA_DIR, 'oauth_exchange_codes.json')


def _read_oauth_exchanges():
    path = _oauth_exchange_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_oauth_exchanges(data):
    path = _oauth_exchange_file()
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
        'mobile_code_challenge': None,
        'link_user_id': None,
    }
    if not state:
        return missing
    if pg.enabled():
        with pg.connection() as conn:
            row = conn.execute(
                """
                DELETE FROM oauth_states
                WHERE state = %s AND created_at >= NOW() - (%s * INTERVAL '1 second')
                RETURNING code_verifier, mobile, mobile_code_challenge, link_user_id
                """,
                (state, OAUTH_STATE_TTL_SECONDS),
            ).fetchone()
        if not row:
            return missing
        return {
            'found': True,
            'code_verifier': row['code_verifier'],
            'mobile': bool(row['mobile']),
            'mobile_code_challenge': row['mobile_code_challenge'],
            'link_user_id': row['link_user_id'],
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
        'mobile_code_challenge': record.get('mobile_code_challenge'),
        'link_user_id': record.get('link_user_id'),
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


def _store_oauth_link_user(state, user_id):
    """Record which already-logged-in FlowMate user started this OAuth
    transaction (intent=link), so oauth2callback attaches the resulting
    Google credential to that account instead of resolving/minting one
    from the Google identity itself. Absent entirely means intent=recover.
    """
    if not state or not user_id:
        return
    if pg.enabled():
        with pg.connection() as conn:
            conn.execute(
                """
                INSERT INTO oauth_states (state, link_user_id)
                VALUES (%s, %s)
                ON CONFLICT (state) DO UPDATE SET link_user_id = EXCLUDED.link_user_id
                """,
                (state, user_id),
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
        record['link_user_id'] = user_id
        data[state] = record
        _write_oauth_states(data)


def _store_mobile_code_challenge(state, code_challenge):
    """Record the mobile app's own PKCE challenge for this transaction.

    Only set by app builds updated to protect the backend->app deep-link
    handoff (see oauth_exchange_codes) -- an older, not-yet-updated app
    simply never calls this, and oauth2callback falls back to its previous
    behavior for that state. Merges into the same row _mark_oauth_mobile
    writes, so call this after it, not instead of it.
    """
    if not state or not code_challenge:
        return
    if pg.enabled():
        with pg.connection() as conn:
            conn.execute(
                """
                INSERT INTO oauth_states (state, mobile_code_challenge)
                VALUES (%s, %s)
                ON CONFLICT (state) DO UPDATE SET mobile_code_challenge = EXCLUDED.mobile_code_challenge
                """,
                (state, code_challenge),
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
        record['mobile_code_challenge'] = code_challenge
        data[state] = record
        _write_oauth_states(data)


def _store_oauth_exchange(exchange_code, code_challenge, payload):
    """Stash the real token payload behind a one-time exchange_code, keyed
    separately from oauth_states (which is already consumed by the time this
    is called -- see oauth2callback)."""
    if pg.enabled():
        with pg.connection() as conn:
            conn.execute(
                "DELETE FROM oauth_exchange_codes WHERE created_at < NOW() - (%s * INTERVAL '1 second')",
                (OAUTH_EXCHANGE_TTL_SECONDS,),
            )
            conn.execute(
                """
                INSERT INTO oauth_exchange_codes (exchange_code, code_challenge, payload)
                VALUES (%s, %s, %s)
                """,
                (exchange_code, code_challenge, pg.json_value(payload)),
            )
        return

    now = datetime.utcnow().timestamp()
    with _oauth_exchange_lock:
        data = _read_oauth_exchanges()
        data = {
            key: value for key, value in data.items()
            if isinstance(value, dict)
            and now - float(value.get('created_at') or 0) <= OAUTH_EXCHANGE_TTL_SECONDS
        }
        data[exchange_code] = {
            'code_challenge': code_challenge,
            'payload': payload,
            'created_at': now,
        }
        _write_oauth_exchanges(data)


def _consume_oauth_exchange(exchange_code):
    """Atomically consume a one-time OAuth exchange code. Returns None if
    unknown, expired, or already used."""
    if not exchange_code:
        return None
    if pg.enabled():
        with pg.connection() as conn:
            row = conn.execute(
                """
                DELETE FROM oauth_exchange_codes
                WHERE exchange_code = %s AND created_at >= NOW() - (%s * INTERVAL '1 second')
                RETURNING code_challenge, payload
                """,
                (exchange_code, OAUTH_EXCHANGE_TTL_SECONDS),
            ).fetchone()
        if not row:
            return None
        payload = row['payload']
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = {}
        return {'code_challenge': row['code_challenge'], 'payload': payload}

    now = datetime.utcnow().timestamp()
    with _oauth_exchange_lock:
        data = _read_oauth_exchanges()
        record = data.pop(exchange_code, None)
        data = {
            key: value for key, value in data.items()
            if isinstance(value, dict)
            and now - float(value.get('created_at') or 0) <= OAUTH_EXCHANGE_TTL_SECONDS
        }
        _write_oauth_exchanges(data)
    if not isinstance(record, dict):
        return None
    if now - float(record.get('created_at') or 0) > OAUTH_EXCHANGE_TTL_SECONDS:
        return None
    return {
        'code_challenge': record.get('code_challenge'),
        'payload': record.get('payload') or {},
    }


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
    """Clear this browser's Gmail-connection state -- NOT the FlowMate
    login session.

    Google is no longer a login/identity provider (the FlowMate-primary
    account redesign): disconnecting Gmail revokes/discards the linked
    credential and its cached session display fields, same as unlinking
    any other data source. It must never also clear session['user_id']
    or the admin TOTP elevation -- both are tied to the FlowMate account
    itself (admin identity now trusts users.email, not a live Google
    session), which this call never touches. This used to also pop
    those two, back when Google disconnecting really did mean "this
    browser's identity is gone".
    """
    token_file = delete_google_credentials(user_id)
    invalidate_cached_service(token_file)

    session.pop('oauth_state', None)
    session.pop('oauth_code_verifier', None)
    session.pop('oauth_user_id', None)
    session.pop('gmail_user_email', None)
    session.pop('gmail_user_name', None)
    session.pop('gmail_user_picture', None)
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
    """Link a Gmail account from Android using Server Auth Code.

    Not called by any currently-shipped client (superseded by the
    /auth_url + PKCE + /oauth-token-exchange flow) -- gated here as
    defense-in-depth only, not because anything depends on it. Google can
    no longer establish a FlowMate session on its own, so this always
    requires an existing login and attaches to that account (no
    'recover' variant needed for a native-only, already-dead endpoint).
    """
    link_user_id = authenticated_user_id()
    if not link_user_id:
        return jsonify({'success': False, 'error': 'login_required'}), 401

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

        # Attach to the already-logged-in FlowMate user (see the
        # login_required gate above) -- never mint/resolve an identity
        # from the Google subject the way resolve_google_user_id does.
        subject = userinfo.get('subject')
        existing_owner = lookup_google_identity_owner(subject, gmail_email)
        if existing_owner and existing_owner != link_user_id:
            return jsonify({'success': False, 'error': 'google_account_already_linked_elsewhere'}), 409
        user_id = link_user_id
        upsert_google_identity(subject, gmail_email, user_id)

        # Save token durably for Railway and cache it locally for this worker.
        persist_google_credentials(
            user_id, creds,
            account_email=gmail_email, account_name=gmail_name, account_picture=gmail_picture,
        )

        # Update User in Database. Deliberately does not touch `email` --
        # that's the FlowMate account's own identity (Feature A trusts it
        # for the admin allowlist check), not whichever Gmail got linked.
        db_path = get_user_db_path(user_id)
        user = User.get_or_create(user_id, name=gmail_name, email=gmail_email)
        User.update(
            user_id,
            gmail_email=gmail_email,
            gmail_name=gmail_name,
            gmail_picture=gmail_picture,
            gmail_connected=1,
            gmail_connected_at=datetime.now().isoformat(),
            avatar_url=gmail_picture,
            name=(gmail_name or (user.get('name') if user else gmail_name)),
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
            'access_token': issue_mobile_token(user_id, token_version=(user or {}).get('token_version')),
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


def _resolve_oauth_intent():
    """Shared intent gate for /auth and /auth_url.

    Google OAuth is no longer a login mechanism on its own -- FlowMate
    accounts are email+password only. 'link' attaches a Gmail account to
    whoever is already logged in; 'recover' lets a pre-existing
    Google-only account (no password set yet) regain access, but never
    creates a brand-new account. Returns (intent, user_id_or_None,
    error_response_or_None).
    """
    intent = (request.args.get('intent') or '').strip().lower()
    if intent not in ('link', 'recover'):
        return None, None, (jsonify({
            'error': 'invalid_intent',
            'message': 'intent phải là link hoặc recover.',
        }), 400)
    if intent == 'link':
        user_id = authenticated_user_id()
        if not user_id:
            return None, None, (jsonify({
                'error': 'login_required',
                'message': 'Đăng nhập bằng tài khoản FlowMate trước khi liên kết Gmail.',
            }), 401)
        return intent, user_id, None
    return intent, None, None


@email_bp.route('/auth', methods=['GET'])
def gmail_auth():
    """Initiate OAuth2 flow to link a Gmail account (or recover account
    access) -- never a login on its own, see _resolve_oauth_intent."""
    intent, link_user_id, error_response = _resolve_oauth_intent()
    if error_response:
        return error_response

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
    if intent == 'link':
        _store_oauth_link_user(state, link_user_id)
    return redirect(auth_url)


def _oauth_error_redirect(error_code, is_mobile_flow=False, email=''):
    """Every oauth2callback failure must land the user back on a page they
    recognize, not a raw JSON blob. This endpoint is only ever reached via a
    full top-level browser navigation (Google's own redirect), never a
    fetch()/XHR call a JS error handler could catch -- a bare jsonify()
    response here used to leave the tab (or the mobile system-browser view)
    stuck showing unreadable JSON with no link or button back into the app,
    which looked exactly like the flow had hung at the consent step.

    ``email`` (the Google account that triggered the error, when known) lets
    the client show a specific, actionable message -- e.g. the
    already-linked-elsewhere modal naming exactly which address conflicted.
    """
    params = {'error': error_code}
    if email:
        params['email'] = email
    if is_mobile_flow:
        return redirect(f"{Config.MOBILE_OAUTH_REDIRECT_URL}?{urlencode(params)}")
    return_to = session.pop('oauth_return_to', None) or '/app'
    separator = '&' if '?' in return_to else '?'
    params['gmail_auth'] = 'error'
    return redirect(f"{return_to}{separator}{urlencode(params)}")


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
        # Neither the mobile-ness nor the intended return_to is known yet at
        # this point -- best effort is the web redirect default.
        return _oauth_error_redirect('flow_not_initialized')

    try:
        flow = _build_oauth_flow(state=state)
    except Exception as e:
        logger.error(f"Failed to build OAuth flow: {e}")
        return _oauth_error_redirect('oauth_flow_unavailable')

    # A callback is valid only when its state is backed by the browser session
    # that started it or by a shared state row issued for a mobile/cross-worker
    # flow. Consuming the row atomically rejects unknown and replayed states.
    issued_state = _consume_oauth_state(state)
    session_matches = bool(session_state and session_state == state)
    if not session_matches and not issued_state['found']:
        logger.warning("Rejected unknown or replayed OAuth state")
        return _oauth_error_redirect('invalid_oauth_state', is_mobile_flow=issued_state['mobile'])

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
        return _oauth_error_redirect('token_fetch_failed', is_mobile_flow=is_mobile_flow)

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

        # Attach this Google identity to a FlowMate account WITHOUT ever
        # minting a new one from it -- resolve_google_user_id used to do
        # that unconditionally, which is exactly the "Google is a login
        # method" behavior this change removes.
        subject = userinfo.get('subject')
        link_user_id = issued_state.get('link_user_id')
        existing_owner = lookup_google_identity_owner(subject, gmail_email)
        if link_user_id:
            # intent=link: attach to whoever was already logged in when
            # this flow started.
            if existing_owner and existing_owner != link_user_id:
                logger.warning("Rejected linking a Google account already owned by a different user")
                return _oauth_error_redirect(
                    'google_account_already_linked_elsewhere',
                    is_mobile_flow=is_mobile_flow,
                    email=gmail_email,
                )
            user_id = link_user_id
        else:
            # intent=recover: only ever resolves to an EXISTING account --
            # never creates one (that would silently reintroduce
            # Google-as-signup).
            if not existing_owner:
                return _oauth_error_redirect('no_flowmate_account_for_google_identity', is_mobile_flow=is_mobile_flow)
            user_id = existing_owner
        upsert_google_identity(subject, gmail_email, user_id)
        logger.info(f"Setting session for user: {user_id}")

        # Save token durably for Railway and cache it locally for this worker.
        token_file = persist_google_credentials(
            user_id, creds,
            account_email=gmail_email, account_name=gmail_name, account_picture=gmail_picture,
        )
        logger.info(f"Token saved for user: {token_file}")

        # Save user info to database and initialize per-user DB
        db_path = get_user_db_path(user_id)
        user = User.get_or_create(user_id, name=gmail_name or 'Teacher', email=gmail_email)
        needs_password = not bool((user or {}).get('password_hash'))
        # Update Gmail-specific fields and avatar/name, but deliberately
        # NOT `email` -- that's the FlowMate account's own identity
        # (Feature A trusts it for the admin allowlist check), not
        # whichever Gmail happens to get linked/recovered.
        User.update(
            user_id,
            gmail_email=gmail_email,
            gmail_name=gmail_name,
            gmail_picture=gmail_picture,
            gmail_connected=1,
            gmail_connected_at=datetime.now().isoformat(),
            avatar_url=gmail_picture,
            name=(gmail_name or (user.get('name') if user else gmail_name)),
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
            mobile_code_challenge = issued_state.get('mobile_code_challenge')
            if mobile_code_challenge:
                # Protect the deep-link handoff itself: flowmateai:// is a
                # custom scheme, not domain-verified, so another app could in
                # principle register it too and intercept this redirect. Hand
                # back only a one-time exchange_code instead of the real
                # token; POST /email/oauth-token-exchange only releases the
                # token to whoever also holds the code_verifier that produced
                # this challenge -- i.e. the same app instance that started
                # the flow.
                exchange_code = secrets.token_urlsafe(32)
                _store_oauth_exchange(exchange_code, mobile_code_challenge, {
                    'access_token': issue_mobile_token(user_id, token_version=(user or {}).get('token_version')),
                    'user_id': user_id,
                    'email': gmail_email,
                    'needs_password': needs_password,
                })
                exchange_query = urlencode({'exchange_code': exchange_code})
                return redirect(f"{Config.MOBILE_OAUTH_REDIRECT_URL}?{exchange_query}")

            # Legacy fallback for an app build that hasn't updated to send a
            # code_challenge yet -- keep working exactly as before rather
            # than breaking sign-in for whatever's already installed.
            token_query = urlencode({
                'access_token': issue_mobile_token(user_id, token_version=(user or {}).get('token_version')),
                'user_id': user_id,
                'email': gmail_email,
                'needs_password': '1' if needs_password else '0',
            })
            return redirect(f"{Config.MOBILE_OAUTH_REDIRECT_URL}?{token_query}")

        # Return HTML page that notifies the opener or redirects back to SPA
        return_to = session.pop('oauth_return_to', '/app?gmail_auth=success')
        if needs_password:
            separator = '&' if '?' in return_to else '?'
            return_to = f'{return_to}{separator}needs_password=1'
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
          window.opener.postMessage({type: 'gmail_auth', status: 'success', needsPassword: __NEEDS_PASSWORD__}, window.location.origin);
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
""".replace('__RETURN_TO__', json.dumps(return_to)).replace('__NEEDS_PASSWORD__', json.dumps(bool(needs_password)))
        from flask import Response
        return Response(html, mimetype='text/html')
    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)
        return _oauth_error_redirect('callback_error', is_mobile_flow=is_mobile_flow)


@email_bp.route('/auth_url', methods=['GET'])
def gmail_auth_url():
    """Return the OAuth authorization URL (JSON) so frontend can redirect.
    Never a login on its own -- see _resolve_oauth_intent."""
    intent, link_user_id, error_response = _resolve_oauth_intent()
    if error_response:
        return error_response

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
    if intent == 'link':
        _store_oauth_link_user(state, link_user_id)
    # The mobile app's fetch() never shares cookies with the system browser
    # that completes this flow, so oauth2callback needs to know to hand the
    # result back via a deep link instead of the cookie/postMessage page.
    # Call this AFTER _store_oauth_code_verifier (it merges into the same
    # record rather than overwriting it).
    if (request.args.get('platform') or '').strip().lower() == 'mobile':
        _mark_oauth_mobile(state)
        # Optional: an app build updated to protect the deep-link handoff
        # (see oauth_exchange_codes) sends its own PKCE challenge here. An
        # older app that hasn't updated simply omits it, and oauth2callback
        # falls back to handing the token straight back in the deep link,
        # exactly as before -- this stays backward compatible with whatever
        # APK/IPA build is already installed on a user's device.
        code_challenge = (request.args.get('code_challenge') or '').strip()
        if 20 <= len(code_challenge) <= 256:
            _store_mobile_code_challenge(state, code_challenge)
    return jsonify({'auth_url': auth_url})


def _pkce_s256_challenge(code_verifier):
    """RFC 7636 S256: base64url(SHA256(code_verifier)), no padding."""
    digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')


@email_bp.route('/oauth-token-exchange', methods=['POST'])
def oauth_token_exchange():
    """Redeem a one-time exchange_code (handed to the mobile app via the
    flowmateai:// deep link instead of the real access token -- see
    oauth2callback) for the actual mobile session payload.

    Requires the code_verifier the app generated before starting the flow.
    Only whoever holds it can pass this check, which is the whole point:
    the deep link itself carries nothing but an opaque, single-use code.
    """
    data = request.get_json(silent=True) or {}
    exchange_code = str(data.get('exchange_code') or '').strip()
    code_verifier = str(data.get('code_verifier') or '').strip()
    if not exchange_code or not code_verifier:
        return jsonify({'error': 'invalid_request', 'message': 'Missing exchange_code or code_verifier'}), 400

    record = _consume_oauth_exchange(exchange_code)
    if not record:
        return jsonify({'error': 'invalid_or_expired_exchange_code'}), 400

    expected_challenge = str(record.get('code_challenge') or '')
    computed_challenge = _pkce_s256_challenge(code_verifier)
    if not expected_challenge or not hmac.compare_digest(computed_challenge, expected_challenge):
        return jsonify({'error': 'code_verifier_mismatch'}), 400

    payload = record.get('payload') or {}
    return jsonify({
        'success': True,
        'access_token': payload.get('access_token'),
        'user_id': payload.get('user_id'),
        'email': payload.get('email'),
        'needs_password': bool(payload.get('needs_password')),
    })
