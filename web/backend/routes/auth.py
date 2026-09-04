import hashlib
import logging
import re
import sys
import os
from datetime import datetime

from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.user import User
from utils.security import issue_mobile_token

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')
logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
GENERIC_LOGIN_ERROR = 'Email hoặc mật khẩu không đúng.'


def _local_user_id(email):
    """Deterministic, collision-resistant id for password-based accounts.

    Mirrors the shape of the Google-identity ids in utils/user_context.py
    (`<provider>_<sha256 prefix>`) but stays self-contained here so this new
    auth path can never accidentally perturb the Google OAuth id resolution
    it must not touch.
    """
    digest = hashlib.sha256(f'local:{email}'.encode('utf-8')).hexdigest()
    return f'local_{digest[:40]}'


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    name = str(data.get('name') or '').strip()[:100]
    email = str(data.get('email') or '').strip().lower()[:254]
    password = str(data.get('password') or '')

    if not name:
        return jsonify({'success': False, 'error': 'missing_name', 'message': 'Vui lòng nhập họ tên.'}), 400
    if not email or not EMAIL_RE.match(email):
        return jsonify({'success': False, 'error': 'invalid_email', 'message': 'Email không hợp lệ.'}), 400
    if len(password) < MIN_PASSWORD_LENGTH or len(password) > MAX_PASSWORD_LENGTH:
        return jsonify({
            'success': False,
            'error': 'weak_password',
            'message': f'Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự.',
        }), 400

    existing = User.get_by_email(email)
    if existing:
        # Never attach a password to an account that isn't already a
        # password account -- silently doing so on a Google-only account
        # would let anyone "claim" someone else's Gmail-linked workspace
        # just by knowing their address.
        if existing.get('gmail_connected') or existing.get('gmail_email'):
            return jsonify({
                'success': False,
                'error': 'email_registered_via_google',
                'message': 'Email này đã đăng ký qua Google. Vui lòng đăng nhập bằng Google.',
            }), 409
        return jsonify({
            'success': False,
            'error': 'email_already_registered',
            'message': 'Email này đã được đăng ký. Vui lòng đăng nhập.',
        }), 409

    user_id = _local_user_id(email)
    User.get_or_create(user_id, name=name, email=email)
    User.update(user_id, password_hash=generate_password_hash(password))

    session['user_id'] = user_id
    session.modified = True

    logger.info('Password account registered: %s', user_id)
    return jsonify({
        'success': True,
        'user_id': user_id,
        'email': email,
        'access_token': issue_mobile_token(user_id),
        'message': 'Tạo tài khoản thành công',
    })


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get('email') or '').strip().lower()[:254]
    password = str(data.get('password') or '')

    if not email or not password:
        return jsonify({'success': False, 'error': 'invalid_credentials', 'message': GENERIC_LOGIN_ERROR}), 401

    user = User.get_by_email(email)
    password_hash = (user or {}).get('password_hash')
    if not user or not password_hash or not check_password_hash(password_hash, password):
        return jsonify({'success': False, 'error': 'invalid_credentials', 'message': GENERIC_LOGIN_ERROR}), 401

    user_id = user['user_id']
    session['user_id'] = user_id
    session.modified = True

    logger.info('Password account logged in: %s', user_id)
    return jsonify({
        'success': True,
        'user_id': user_id,
        'email': user.get('email') or email,
        'access_token': issue_mobile_token(user_id),
        'message': 'Đăng nhập thành công',
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """End the browser app session without revoking Google integration.

    Native clients keep app authentication in their local Bearer token and
    clear it on-device. The browser equivalent is the signed session cookie.
    """
    session.clear()
    return jsonify({'success': True, 'message': 'Đăng xuất thành công'})
