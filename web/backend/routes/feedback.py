"""User feedback API: a logged-in user submits free-text feedback. Read-only
admin list lives in routes/admin.py instead of here, matching how the
admin-facing half of other features stays in admin.py rather than each
feature's own route file.
"""

from flask import Blueprint, jsonify, request, session

from models import feedback as feedback_model
from utils.user_context import get_current_user_id

feedback_bp = Blueprint('feedback', __name__, url_prefix='/api/feedback')

MAX_MESSAGE_LENGTH = 2000  # shortcut: arbitrary cap, raise if real feedback gets truncated


@feedback_bp.route('', methods=['POST'])
def submit_feedback():
    user_id = get_current_user_id(request, session=session)
    if not user_id or user_id == 'default':
        return jsonify({'error': 'not_authenticated'}), 401

    message = str((request.get_json(silent=True) or {}).get('message') or '').strip()
    if not message:
        return jsonify({'error': 'empty_message'}), 400
    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify({'error': 'message_too_long'}), 400

    feedback_model.create(user_id, message)
    return jsonify({'success': True})
