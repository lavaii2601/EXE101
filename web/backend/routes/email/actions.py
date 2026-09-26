"""Mailbox actions: mark read/unread, archive, trash.

Split out of the former monolithic routes/email.py -- see
routes/email/__init__.py for the package-level overview.
"""
import logging

from flask import jsonify, request, session

from models.history import History
from utils.user_context import get_current_user_id, get_user_db_path

from routes.email.shared import email_bp, _clear_email_list_cache
from routes.email.oauth import _load_gmail_service

# Configure module logger
logger = logging.getLogger(__name__)


@email_bp.route('/mark-as-read/<email_id>', methods=['POST'])
def mark_email_as_read(email_id):
    """Mark an email as read"""
    user_id = get_current_user_id(request, session=session)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    try:
        success = service.mark_as_read(email_id)
        if success:
            # Clear cache to force refresh
            _clear_email_list_cache(user_id)
            History.create(
                "Đánh dấu email đã đọc", "", action_type='chat',
                db_path=get_user_db_path(user_id),
            )
            return jsonify({'success': True, 'message': 'Đã đánh dấu đã đọc'})
        return jsonify({'error': 'Failed to mark as read'}), 500
    except Exception as e:
        logger.error(f"Error marking as read: {str(e)}")
        return jsonify({'error': str(e)}), 500


@email_bp.route('/mark-as-unread/<email_id>', methods=['POST'])
def mark_email_as_unread(email_id):
    """Mark an email as unread"""
    user_id = get_current_user_id(request, session=session)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    try:
        success = service.mark_as_unread(email_id)
        if success:
            # Clear cache to force refresh
            _clear_email_list_cache(user_id)
            History.create(
                "Đánh dấu email chưa đọc", "", action_type='chat',
                db_path=get_user_db_path(user_id),
            )
            return jsonify({'success': True, 'message': 'Đã đánh dấu chưa đọc'})
        return jsonify({'error': 'Failed to mark as unread'}), 500
    except Exception as e:
        logger.error(f"Error marking as unread: {str(e)}")
        return jsonify({'error': str(e)}), 500


@email_bp.route('/archive/<email_id>', methods=['POST'])
def archive_email(email_id):
    """Archive an email (remove from inbox, keep in All Mail)"""
    user_id = get_current_user_id(request, session=session)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    try:
        success = service.archive_email(email_id)
        if success:
            _clear_email_list_cache(user_id)
            History.create(
                "Lưu trữ email", "", action_type='chat',
                db_path=get_user_db_path(user_id),
            )
            return jsonify({'success': True, 'message': 'Đã lưu trữ email'})
        return jsonify({'error': 'Failed to archive email'}), 500
    except Exception as e:
        logger.error(f"Error archiving email: {str(e)}")
        return jsonify({'error': str(e)}), 500


@email_bp.route('/trash/<email_id>', methods=['POST'])
def trash_email(email_id):
    """Move an email to trash (reversible)"""
    user_id = get_current_user_id(request, session=session)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    try:
        success = service.trash_email(email_id)
        if success:
            _clear_email_list_cache(user_id)
            History.create(
                "Xóa email (thùng rác)", "", action_type='chat',
                db_path=get_user_db_path(user_id),
            )
            return jsonify({'success': True, 'message': 'Đã chuyển email vào thùng rác'})
        return jsonify({'error': 'Failed to trash email'}), 500
    except Exception as e:
        logger.error(f"Error trashing email: {str(e)}")
        return jsonify({'error': str(e)}), 500
