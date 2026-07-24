import json
import hashlib
import os
import pickle
import re
import sys
import tempfile
import threading
from flask import session as flask_session
from google.auth.transport.requests import Request as GoogleAuthRequest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import postgres_db as pg
from utils.security import bearer_user_id, header_user_id


class IdentityConflictError(RuntimeError):
    """Raised when a legacy account cannot be migrated without ambiguity."""


class CredentialStoreError(RuntimeError):
    """Raised when PostgreSQL credential authority cannot be synchronized."""


_credential_lock = threading.RLock()
_credential_versions = {}
_credential_file_locks = {}


def _credential_file_lock(token_file):
    normalized_path = os.path.abspath(os.fspath(token_file))
    with _credential_lock:
        return _credential_file_locks.setdefault(normalized_path, threading.RLock())


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


def _stable_principal(provider, subject):
    """Return a collision-resistant, path-safe internal principal.

    Email addresses are mutable and the former punctuation-to-underscore
    sanitizer was lossy (for example ``a.b`` and ``a_b`` collided).  New
    identities therefore derive their storage key from the immutable Google
    subject when available, with a normalized email hash as a safe fallback.
    """
    provider = re.sub(r'[^a-z0-9_-]+', '_', str(provider or 'external').lower())
    subject = str(subject or '').strip()
    digest = hashlib.sha256(f'{provider}:{subject}'.encode('utf-8')).hexdigest()
    return f'{provider}_{digest[:40]}'


def resolve_google_user_id(subject, account_email):
    """Resolve Google OAuth identity to one canonical FlowMate user id.

    Existing production accounts keep their current user id when their stored
    Gmail email matches exactly.  A new immutable Google subject is then linked
    through ``user_identities``.  A punctuation-colliding legacy id is never
    reused for a different email.
    """
    email = str(account_email or '').strip().lower()
    external_subject = str(subject or '').strip() or (f'email:{email}' if email else '')
    if not external_subject:
        raise IdentityConflictError('Google identity is missing both subject and email')

    candidate = _stable_principal('google', external_subject)
    if not pg.enabled():
        return candidate

    with pg.connection() as conn:
        identity = conn.execute(
            """
            SELECT user_id
            FROM user_identities
            WHERE provider = 'google' AND subject = %s
            """,
            (external_subject,),
        ).fetchone()
        if identity:
            return identity['user_id']

        exact_rows = []
        if email:
            exact_rows = conn.execute(
                """
                SELECT user_id
                FROM users
                WHERE LOWER(COALESCE(gmail_email, '')) = %s
                   OR LOWER(COALESCE(email, '')) = %s
                ORDER BY created_at ASC
                """,
                (email, email),
            ).fetchall()

        exact_ids = list(dict.fromkeys(
            row['user_id'] for row in exact_rows if row.get('user_id')
        ))
        if len(exact_ids) > 1:
            raise IdentityConflictError(
                'Multiple legacy users match this Google email; manual resolution is required'
            )

        canonical_user_id = exact_ids[0] if exact_ids else candidate
        if not exact_ids and email:
            legacy_user_id = sanitize_user_id(email)
            legacy = conn.execute(
                """
                SELECT user_id, gmail_email, email
                FROM users
                WHERE user_id = %s
                """,
                (legacy_user_id,),
            ).fetchone()
            if legacy:
                legacy_email = str(
                    legacy.get('gmail_email') or legacy.get('email') or ''
                ).strip().lower()
                if legacy_email == email:
                    canonical_user_id = legacy['user_id']

        conn.execute(
            """
            INSERT INTO users (user_id, email, gmail_email)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (canonical_user_id, email or None, email or None),
        )
        conn.execute(
            """
            INSERT INTO user_identities (
                provider, subject, user_id, account_email
            )
            VALUES ('google', %s, %s, %s)
            ON CONFLICT (provider, subject) DO NOTHING
            """,
            (external_subject, canonical_user_id, email or None),
        )
        identity = conn.execute(
            """
            SELECT user_id
            FROM user_identities
            WHERE provider = 'google' AND subject = %s
            """,
            (external_subject,),
        ).fetchone()
        if not identity:
            raise IdentityConflictError('Could not persist Google identity mapping')
        return identity['user_id']


def get_current_user_id(request, session=None):
    """Resolve current user id from session (Flask session used by default).

    If `session` is not provided, the function reads/writes the Flask `session`.
    Ensures `session['user_id']` is set to the sanitized value for downstream
    code that relies on a consistent user identifier.
    """
    if session is None:
        session = flask_session

    bearer_id = bearer_user_id()
    session_user_id = session.get('user_id')
    header_id = header_user_id()
    mobile_user_id = bearer_id or header_id
    user_id = (
        bearer_id
        or session_user_id
        or session.get('gmail_user_email')
        or header_id
    )
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


def _row_value(row, key, default=None):
    if row is None:
        return default
    try:
        return row.get(key, default)
    except AttributeError:
        try:
            return row[key]
        except (KeyError, TypeError):
            return default


def _credential_revision(row):
    """Return a content-aware version for one PostgreSQL credential row."""
    token_info = _row_value(row, 'token_json') or {}
    scopes = _row_value(row, 'scopes') or []
    payload = {
        'updated_at': _row_value(row, 'updated_at'),
        'revoked_at': _row_value(row, 'revoked_at'),
        'token_json': token_info,
        'scopes': list(scopes),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(',', ':'),
        default=str,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _local_token_digest(token_file):
    try:
        with open(token_file, 'rb') as token:
            return hashlib.sha256(token.read()).hexdigest()
    except OSError:
        return None


def _invalidate_google_service_cache(token_file):
    # Keep this import local: Google service constructors import user_context
    # to persist a refreshed credential.
    from utils.google_service_cache import invalidate_cached_service

    invalidate_cached_service(token_file)


def _write_local_credentials(token_file, creds):
    """Atomically replace the process-local credential cache."""
    os.makedirs(os.path.dirname(token_file), exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='wb',
            prefix=f'{os.path.basename(token_file)}.',
            suffix='.tmp',
            dir=os.path.dirname(token_file),
            delete=False,
        ) as temporary:
            temporary_path = temporary.name
            pickle.dump(creds, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, token_file)
        temporary_path = None
    finally:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass


def _discard_local_credentials(token_file):
    """Make a local token unusable and evict every cached Google service."""
    normalized_path = os.path.abspath(os.fspath(token_file))
    with _credential_file_lock(token_file):
        _credential_versions.pop(normalized_path, None)
        try:
            os.remove(token_file)
        except FileNotFoundError:
            pass
        except OSError as exc:
            # If unlinking is temporarily unavailable (for example, a Windows
            # file handle is still open), truncate the pickle so no caller can
            # continue using a credential PostgreSQL considers revoked.
            try:
                with open(token_file, 'wb'):
                    pass
            except OSError as truncate_exc:
                _invalidate_google_service_cache(token_file)
                raise CredentialStoreError(
                    'Could not invalidate the local Google credential'
                ) from truncate_exc
        _invalidate_google_service_cache(token_file)


def get_user_token_file(user_id):
    user_id = sanitize_user_id(user_id)
    token_file = _user_token_path(user_id)
    if pg.enabled():
        # PostgreSQL is the credential authority on Railway. Query it on every
        # acquisition so a worker cannot keep serving a token refreshed or
        # revoked by another worker.
        with _credential_file_lock(token_file):
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
    if not pg.enabled():
        with _credential_file_lock(token_file):
            _write_local_credentials(token_file, creds)
            _invalidate_google_service_cache(token_file)
        return token_file

    try:
        pg.ensure_user(user_id, email=account_email or '')
        token_info = json.loads(creds.to_json())
        if not isinstance(token_info, dict):
            raise ValueError('Google credential serialization must be a JSON object')
        scopes = list(getattr(creds, 'scopes', None) or token_info.get('scopes') or [])
        expires_at = getattr(creds, 'expiry', None)

        with pg.connection() as conn:
            row = conn.execute(
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
                RETURNING token_json, scopes, updated_at, revoked_at
                """,
                (user_id, account_email or None, pg.json_value(token_info), scopes, expires_at),
            ).fetchone()

        if not row:
            raise CredentialStoreError('PostgreSQL did not return the persisted Google credential')

        normalized_path = os.path.abspath(os.fspath(token_file))
        with _credential_file_lock(token_file):
            _write_local_credentials(token_file, creds)
            _credential_versions[normalized_path] = (
                _credential_revision(row),
                _local_token_digest(token_file),
            )
            _invalidate_google_service_cache(token_file)
    except Exception as exc:
        # In production, a local pickle is only a cache. If the durable write
        # cannot be confirmed, fail closed instead of leaving a token that
        # another request could mistake for authoritative state.
        _discard_local_credentials(token_file)
        if isinstance(exc, CredentialStoreError):
            raise
        raise CredentialStoreError(
            'Could not persist Google credentials to PostgreSQL'
        ) from exc

    return token_file


def inspect_google_credentials(user_id, refresh=False):
    """Return a truthful status for the persisted Google credential.

    Token-file presence alone is not authentication: a revoked credential or
    an expired access token without a refresh token must be surfaced to the
    client so it can ask the user to reconnect instead of showing empty data.
    """
    user_id = sanitize_user_id(user_id)
    token_file = _user_token_path(user_id)
    status = {
        'has_token': False,
        'valid': False,
        'expired': False,
        'refreshable': False,
        'refreshed': False,
        'scopes': [],
        'error': None,
        'token_file': token_file,
    }
    try:
        token_file = get_user_token_file(user_id)
    except CredentialStoreError as exc:
        status['error'] = 'credential_store_unavailable'
        status['error_detail'] = str(exc)
        return status

    status['has_token'] = os.path.exists(token_file)
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
    if not pg.enabled():
        _discard_local_credentials(token_file)
        return token_file

    try:
        with pg.connection() as conn:
            conn.execute(
                """
                UPDATE oauth_tokens
                SET revoked_at = NOW()
                WHERE user_id = %s AND provider = 'google'
                """,
                (user_id,),
            )
    except Exception as exc:
        _discard_local_credentials(token_file)
        raise CredentialStoreError(
            'Could not revoke Google credentials in PostgreSQL'
        ) from exc

    _discard_local_credentials(token_file)
    return token_file


def _restore_google_credentials_from_db(user_id, token_file):
    """Synchronize the local pickle with PostgreSQL, failing closed on errors."""
    try:
        from google.oauth2.credentials import Credentials

        with pg.connection() as conn:
            row = conn.execute(
                """
                SELECT token_json, scopes, updated_at, revoked_at
                FROM oauth_tokens
                WHERE user_id = %s
                  AND provider = 'google'
                """,
                (user_id,),
            ).fetchone()
    except Exception as exc:
        _discard_local_credentials(token_file)
        raise CredentialStoreError(
            'Could not read Google credentials from PostgreSQL'
        ) from exc

    if not row or _row_value(row, 'revoked_at') is not None:
        _discard_local_credentials(token_file)
        return False

    token_info = _row_value(row, 'token_json') or {}
    if isinstance(token_info, str):
        try:
            token_info = json.loads(token_info)
        except ValueError as exc:
            _discard_local_credentials(token_file)
            raise CredentialStoreError(
                'PostgreSQL contains an invalid Google credential'
            ) from exc
    if not isinstance(token_info, dict):
        _discard_local_credentials(token_file)
        raise CredentialStoreError(
            'PostgreSQL contains an invalid Google credential'
        )

    revision = _credential_revision(row)
    normalized_path = os.path.abspath(os.fspath(token_file))
    with _credential_file_lock(token_file):
        local_version = (
            revision,
            _local_token_digest(token_file),
        )
        if (
            _credential_versions.get(normalized_path) == local_version
            and local_version[1] is not None
        ):
            return True

        try:
            scopes = _row_value(row, 'scopes') or token_info.get('scopes') or None
            creds = Credentials.from_authorized_user_info(token_info, scopes=scopes)
            _write_local_credentials(token_file, creds)
        except Exception as exc:
            _discard_local_credentials(token_file)
            raise CredentialStoreError(
                'Could not materialize Google credentials from PostgreSQL'
            ) from exc

        _credential_versions[normalized_path] = (
            revision,
            _local_token_digest(token_file),
        )
        _invalidate_google_service_cache(token_file)
        return True
