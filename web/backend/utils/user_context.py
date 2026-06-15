import os
import re
import sys
from flask import session as flask_session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from utils.security import bearer_user_id


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

    mobile_user_id = bearer_user_id()
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
    users_dir = os.path.join(os.path.dirname(Config.GMAIL_TOKEN_FILE), 'users')
    os.makedirs(users_dir, exist_ok=True)
    return os.path.join(users_dir, f'gmail_token_{user_id}.pickle')
