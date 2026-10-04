"""Per-admin TOTP secret storage.

Replaces a single ``ADMIN_TOTP_SECRET`` shared by every admin with one
secret per admin email, so revoking or rotating one person's access no
longer requires resetting everyone else's authenticator app. An admin
without a row here still falls back to the legacy shared secret -- see
``routes/admin.py``'s ``_resolve_admin_totp_secret`` -- so nothing breaks
until an operator explicitly provisions a personal secret via
``scripts/manage_admin_totp.py``.
"""
import json
import logging
import os
import threading

from config import Config
from models import postgres_db as pg

logger = logging.getLogger(__name__)

_file_lock = threading.Lock()


def _secrets_file():
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    return os.path.join(Config.DATA_DIR, 'admin_totp_secrets.json')


def _read_file():
    path = _secrets_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_file(data):
    with open(_secrets_file(), 'w', encoding='utf-8') as handle:
        json.dump(data, handle)


def get_secret(email):
    """Return this admin's personal TOTP secret, or None if unprovisioned.

    Any Postgres error is treated the same as "no personal secret" (never
    raised) so a transient DB hiccup degrades to the legacy shared-secret
    fallback in routes/admin.py instead of locking every admin out.
    """
    email = str(email or '').strip().lower()
    if not email:
        return None
    if pg.enabled():
        try:
            with pg.connection() as conn:
                row = conn.execute(
                    'SELECT secret_base32 FROM admin_totp_secrets WHERE email = %s',
                    (email,),
                ).fetchone()
            return row['secret_base32'] if row else None
        except Exception:
            logger.warning('Could not read admin_totp_secrets for %s', email, exc_info=True)
            return None
    with _file_lock:
        return (_read_file().get(email) or {}).get('secret_base32')


def set_secret(email, secret_base32):
    email = str(email or '').strip().lower()
    if not email or not secret_base32:
        raise ValueError('email and secret_base32 are required')
    if pg.enabled():
        with pg.connection() as conn:
            conn.execute(
                """
                INSERT INTO admin_totp_secrets (email, secret_base32)
                VALUES (%s, %s)
                ON CONFLICT (email) DO UPDATE
                SET secret_base32 = EXCLUDED.secret_base32, updated_at = NOW()
                """,
                (email, secret_base32),
            )
        return
    with _file_lock:
        data = _read_file()
        data[email] = {'secret_base32': secret_base32}
        _write_file(data)


def remove_secret(email):
    email = str(email or '').strip().lower()
    if not email:
        return
    if pg.enabled():
        with pg.connection() as conn:
            conn.execute('DELETE FROM admin_totp_secrets WHERE email = %s', (email,))
        return
    with _file_lock:
        data = _read_file()
        data.pop(email, None)
        _write_file(data)


def list_emails():
    if pg.enabled():
        with pg.connection() as conn:
            rows = conn.execute('SELECT email FROM admin_totp_secrets ORDER BY email').fetchall()
        return [row['email'] for row in rows]
    with _file_lock:
        return sorted(_read_file().keys())
