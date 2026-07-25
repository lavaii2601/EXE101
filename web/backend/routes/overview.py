import os
import sys

from flask import Blueprint, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import subscription as subscription_model
from models import entitlements
from services.overview_service import (
    build_weekly_analytics,
    get_or_start_daily_overview,
    get_upcoming_deadlines,
    parse_overview_date,
    refresh_daily_overview_async,
)
from utils.user_context import get_current_user_id

overview_bp = Blueprint('overview', __name__, url_prefix='/api/overview')


def _attach_student_deadlines(payload, user_id, day):
    """Student-mode-only: nearest deadline for Free, full look-ahead list
    for Premium (see entitlements.STUDENT_*_LIMITS['deadline_countdown_full_list'])."""
    is_student, is_premium = entitlements.student_context(user_id)
    if not is_student:
        return payload
    limits = entitlements.student_limits_for(is_premium)
    limit = None if limits['deadline_countdown_full_list'] else 1
    payload['upcoming_deadlines'] = get_upcoming_deadlines(user_id, today=day, limit=limit)
    return payload


@overview_bp.route('/daily', methods=['GET'])
def daily_overview():
    user_id = get_current_user_id(request)
    day = parse_overview_date(request.args.get('date'))
    max_results = min(max(request.args.get('max_results', 50, type=int), 1), 100)
    force = request.args.get('force', '0') == '1'

    if force:
        started = refresh_daily_overview_async(user_id, day, max_results=max_results, force=True)
        payload = get_or_start_daily_overview(user_id, day, max_results=max_results)
        payload['refreshing'] = started or payload.get('refreshing', False)
        payload['cache_hit'] = False
        return jsonify(_attach_student_deadlines(payload, user_id, day))

    payload = get_or_start_daily_overview(user_id, day, max_results=max_results)
    return jsonify(_attach_student_deadlines(payload, user_id, day))


@overview_bp.route('/analytics', methods=['GET'])
def weekly_analytics():
    user_id = get_current_user_id(request)
    if not subscription_model.is_premium(user_id):
        return jsonify({'error': 'premium_required', 'feature': 'analytics'}), 403
    end_day = parse_overview_date(request.args.get('end_date'))
    days = min(max(request.args.get('days', 7, type=int), 1), 30)
    return jsonify(build_weekly_analytics(user_id, end_day, days=days))
