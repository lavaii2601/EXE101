"""In-app notifications API (Phase 6, design doc section 9.9).

Written by services/subscription_lifecycle_scheduler.py; read here. Plain
per-user resource -- no workspace membership/role resolution needed the way
Work Hub routes require, since recipient_user_id already IS the ownership
check.
"""

from flask import Blueprint, jsonify, request, session

from models import notification as notification_model
from utils.user_context import get_current_user_id

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')


@notifications_bp.route('', methods=['GET'])
def list_notifications():
    user_id = get_current_user_id(request, session=session)
    if not user_id or user_id == 'default':
        return jsonify({'error': 'not_authenticated'}), 401

    try:
        limit = min(max(int(request.args.get('limit', 30)), 1), 100)
    except (TypeError, ValueError):
        limit = 30
    unread_only = (request.args.get('unread_only') or '').strip().lower() in {'1', 'true', 'yes'}

    notifications = notification_model.list_for_user(user_id, limit=limit, unread_only=unread_only)
    return jsonify({
        'success': True,
        'notifications': notifications,
        'unread_count': notification_model.count_unread(user_id),
    })


@notifications_bp.route('/<notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    user_id = get_current_user_id(request, session=session)
    if not user_id or user_id == 'default':
        return jsonify({'error': 'not_authenticated'}), 401

    updated = notification_model.mark_read(user_id, notification_id)
    if not updated:
        # Same response whether the id doesn't exist or belongs to someone
        # else -- never confirm/deny another user's notification exists.
        return jsonify({'error': 'notification_not_found'}), 404
    return jsonify({'success': True, 'unread_count': notification_model.count_unread(user_id)})
