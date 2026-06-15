from flask import Blueprint, request, jsonify, session
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.user import User
from utils.user_context import get_current_user_id

user_bp = Blueprint('user', __name__, url_prefix='/api/user')

USER_MODES = {
    'student', 'worker', 'freelancer', 'mentor', 'teacher',
    'business', 'creator'
}


def _merge_gmail_profile(user):
    """Merge stored user record with Gmail session fields for a complete profile."""
    merged = dict(user or {})

    session_gmail_email = (session.get('gmail_user_email') or '').strip()
    session_gmail_name = (session.get('gmail_user_name') or '').strip()
    session_gmail_picture = (session.get('gmail_user_picture') or '').strip()

    if session_gmail_email:
        merged['gmail_email'] = session_gmail_email
        merged['gmail_connected'] = 1
    if session_gmail_name:
        merged['gmail_name'] = session_gmail_name
    if session_gmail_picture:
        merged['gmail_picture'] = session_gmail_picture

    merged['name'] = merged.get('name') or merged.get('gmail_name') or 'Teacher'
    merged['email'] = merged.get('email') or merged.get('gmail_email') or ''
    merged['avatar_url'] = merged.get('avatar_url') or merged.get('gmail_picture') or ''
    merged['gmail_connected'] = bool(merged.get('gmail_connected')) or bool(session_gmail_email)
    stored_mode = (merged.get('user_mode') or '').strip().lower()
    merged['user_mode'] = stored_mode
    merged['mode_required'] = bool(
        merged['gmail_connected'] and stored_mode not in USER_MODES
    )
    return merged


@user_bp.route('/profile', methods=['GET'])
def get_profile():
    """Get current user profile"""
    user_id = get_current_user_id(request)
    user = User.get(user_id)
    
    if not user:
        user = User.get_or_create(user_id)
    user = _merge_gmail_profile(user)
    
    return jsonify({
        'success': True,
        'user': user
    })


@user_bp.route('/profile', methods=['POST'])
def update_profile():
    """Update user profile"""
    user_id = get_current_user_id(request)
    data = request.get_json() or {}
    User.get_or_create(user_id)
    
    requested_mode = (data.get('user_mode') or '').strip().lower()
    if 'user_mode' in data and requested_mode not in USER_MODES:
        return jsonify({
            'success': False,
            'error': 'Invalid user mode'
        }), 400

    update_data = {
        k: v for k, v in data.items()
        if k in ['name', 'email', 'avatar_url']
    }
    if requested_mode:
        update_data['user_mode'] = requested_mode
        update_data['user_mode_selected_at'] = datetime.now().isoformat()
    
    success = User.update(user_id, **update_data)
    
    user = User.get(user_id)
    unchanged = bool(update_data) and all(user.get(key) == value for key, value in update_data.items())
    if success or unchanged:
        return jsonify({
            'success': True,
            'message': 'Profile updated',
            'user': _merge_gmail_profile(user)
        })
    else:
        return jsonify({
            'success': False,
            'error': 'No changes made'
        }), 400


@user_bp.route('/gmail-connected', methods=['POST'])
def mark_gmail_connected():
    """Mark user Gmail as connected"""
    user_id = get_current_user_id(request)
    User.update(user_id, gmail_connected=1)
    
    user = User.get(user_id)
    return jsonify({
        'success': True,
        'user': user
    })


@user_bp.route('/gmail-disconnected', methods=['POST'])
def mark_gmail_disconnected():
    """Mark user Gmail as disconnected"""
    user_id = get_current_user_id(request)
    User.update(user_id, gmail_connected=0)
    
    user = User.get(user_id)
    return jsonify({
        'success': True,
        'user': user
    })


@user_bp.route('/gmail-info', methods=['GET'])
def get_gmail_info():
    """Get Gmail account info for current user"""
    user_id = get_current_user_id(request)
    user = User.get(user_id)
    
    if not user:
        return jsonify({
            'success': False,
            'error': 'User not found'
        }), 404

    user = _merge_gmail_profile(user)
    
    return jsonify({
        'success': True,
        'gmail_connected': bool(user.get('gmail_connected')),
        'gmail_email': user.get('gmail_email'),
        'gmail_name': user.get('gmail_name'),
        'gmail_picture': user.get('gmail_picture'),
        'gmail_connected_at': user.get('gmail_connected_at')
    })
