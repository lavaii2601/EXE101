"""Reply compose/send.

Split out of the former monolithic routes/email.py -- see
routes/email/__init__.py for the package-level overview.
"""
import logging

from flask import jsonify, request, session, url_for

from models.history import History
from utils.user_context import get_current_user_id, get_user_db_path

from routes.email.shared import email_bp
from routes.email.oauth import _load_gmail_service

# Configure module logger
logger = logging.getLogger(__name__)


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
