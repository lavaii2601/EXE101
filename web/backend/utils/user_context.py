import json
import os
import pickle
import re
import sys
from flask import session as flask_session
from google.auth.transport.requests import Request as GoogleAuthRequest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from utils.security import bearer_user_id, header_user_id


def _user_token_path(user_id):
    user_id = sanitize_user_id(user_id)
    users_dir = os.path.join(os.path.dirname(Config.GMAIL_TOKEN_FILE), 'users')
    os.makedirs(users_dir, exist_ok=True)
    return os.path.join(users_dir, f'gmail_token_{user_id}.pickle')


def user_id_from_token_file(token_file):
    name = os.path.splitext(os.path.basename(str(token_file or '')))[0]
    prefix = 'gmail_token_'
    if name.startswith(prefix):
        return sanitize_user_id(name[len(prefix):])
    return sanitize_user_id(name or 'default')


def sanitize_user_id(user_id):
    """Sanitize user identifier for safe file paths."""
    if not user_id:
        return 'default'

    user_id = str(user_id).strip().lower()
    user_id = re.sub(r'[^a-z0-9_-]+', '_', user_id)
    user_id = user_id.strip('_')
    return user_id or 'default'


def get_current_user_id(request, session=None):
    """Resolve current user id from session (Flask session used by default).

    If `session` is not provided, the function reads/writes the Flask `session`.
    Ensures `session['user_id']` is set to the sanitized value for downstream
    code that relies on a consistent user identifier.
    """
    if session is None:
        session = flask_session

    mobile_user_id = bearer_user_id() or header_user_id()
    user_id = mobile_user_id or session.get('gmail_user_email') or session.get('user_id')
    user_id = sanitize_user_id(user_id)
    # Browser sessions keep a normalized id. Native Bearer identities remain
    # stateless and must never be copied into a browser cookie session.
    if not mobile_user_id:
        try:
            session['user_id'] = user_id
        except Exception:
            pass

    return user_id


def get_user_db_path(user_id):
    user_id = sanitize_user_id(user_id)
    users_dir = os.path.join(os.path.dirname(Config.DATABASE_PATH), 'users')
    os.makedirs(users_dir, exist_ok=True)
    return os.path.join(users_dir, f'{user_id}.db')


def get_user_token_file(user_id):
    user_id = sanitize_user_id(user_id)
    token_file = _user_token_path(user_id)
    if not os.path.exists(token_file):
        _restore_google_credentials_from_db(user_id, token_file)
    return token_file


def persist_google_credentials(user_id, creds, account_email=''):
    """Persist Google OAuth credentials to the local token cache and Postgres.

    Railway's filesystem is ephemeral, so the database copy is the durable
    source. The pickle file remains a local cache for the existing Gmail and
    Calendar service constructors.
    """
    user_id = sanitize_user_id(user_id)
    token_file = _user_token_path(user_id)
    with open(token_file, 'wb') as token:
        pickle.dump(creds, token)

    try:
        from models import postgres_db as pg

        if not pg.enabled():
            return token_file

        pg.ensure_user(user_id, email=account_email or '')
        token_info = json.loads(creds.to_json())
        scopes = list(getattr(creds, 'scopes', None) or token_info.get('scopes') or [])
        expires_at = getattr(creds, 'expiry', None)

        with pg.connection() as conn:
            conn.execute(
                """
                INSERT INTO oauth_tokens (
                    user_id, provider, account_email, token_json, scopes, expires_at, revoked_at
                )
                VALUES (%s, 'google', %s, %s, %s, %s, NULL)
                ON CONFLICT (user_id, provider) DO UPDATE
                SET account_email = COALESCE(EXCLUDED.account_email, oauth_tokens.account_email),
                    token_json = EXCLUDED.token_json,
                    scopes = EXCLUDED.scopes,
                    expires_at = EXCLUDED.expires_at,
                    revoked_at = NULL
                """,
                (user_id, account_email or None, pg.json_value(token_info), scopes, expires_at),
            )
    except Exception:
        # Local file persistence is still enough for development. Production
        # callers log authentication failures at the service boundary.
        pass

    return token_file


def inspect_google_credentials(user_id, refresh=False):
    """Return a truthful status for the persisted Google credential.

    Token-file presence alone is not authentication: a revoked credential or
    an expired access token without a refresh token must be surfaced to the
    client so it can ask the user to reconnect instead of showing empty data.
    """
    user_id = sanitize_user_id(user_id)
    token_file = get_user_token_file(user_id)
    status = {
        'has_token': os.path.exists(token_file),
        'valid': False,
        'expired': False,
        'refreshable': False,
        'refreshed': False,
        'scopes': [],
        'error': None,
        'token_file': token_file,
    }
    if not status['has_token']:
        status['error'] = 'not_authenticated'
        return status

    try:
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
        status['expired'] = bool(getattr(creds, 'expired', False))
        status['refreshable'] = bool(getattr(creds, 'refresh_token', None))
        status['scopes'] = list(
            getattr(creds, 'scopes', None)
            or getattr(creds, 'granted_scopes', None)
            or []
        )
        if refresh and status['expired'] and status['refreshable']:
            creds.refresh(GoogleAuthRequest())
            persist_google_credentials(user_id, creds)
            status['refreshed'] = True
            status['expired'] = bool(getattr(creds, 'expired', False))
            status['scopes'] = list(
                getattr(creds, 'scopes', None)
                or getattr(creds, 'granted_scopes', None)
                or status['scopes']
            )
        status['valid'] = bool(getattr(creds, 'valid', False))
        if not status['valid']:
            status['error'] = 'google_reauthentication_required'
    except Exception as exc:
        status['error'] = 'google_reauthentication_required'
        status['error_detail'] = str(exc)
    return status


def delete_google_credentials(user_id):
    user_id = sanitize_user_id(user_id)
    token_file = _user_token_path(user_id)
    if os.path.exists(token_file):
        try:
            os.remove(token_file)
        except Exception:
            pass

    try:
        from models import postgres_db as pg

        if pg.enabled():
            with pg.connection() as conn:
                conn.execute(
                    """
                    UPDATE oauth_tokens
                    SET revoked_at = NOW()
                    WHERE user_id = %s AND provider = 'google'
                    """,
                    (user_id,),
                )
    except Exception:
        pass

    return token_file


def _restore_google_credentials_from_db(user_id, token_file):
    try:
        from google.oauth2.credentials import Credentials
        from models import postgres_db as pg

        if not pg.enabled():
            return False

        with pg.connection() as conn:
            row = conn.execute(
                """
                SELECT token_json, scopes
                FROM oauth_tokens
                WHERE user_id = %s
                  AND provider = 'google'
                  AND revoked_at IS NULL
                """,
                (user_id,),
            ).fetchone()

        if not row:
            return False

        token_info = row.get('token_json') or {}
        if not isinstance(token_info, dict):
            return False

        scopes = row.get('scopes') or token_info.get('scopes') or None
        creds = Credentials.from_authorized_user_info(token_info, scopes=scopes)
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
        return True
    except Exception:
        return False
