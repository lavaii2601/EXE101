from flask import Blueprint, request, jsonify
import threading
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.user_context import get_current_user_id, get_user_db_path
from services.calendar_service import CalendarService
from models.schedule import Schedule

bg_bp = Blueprint('_background', __name__, url_prefix='/api/_background')


def _sync_to_calendar_async(user_id, schedule_id):
    try:
        db_path = get_user_db_path(user_id)
        schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
        if not schedule:
            return
        token_file = os.path.join(os.path.dirname(db_path), 'users', f'gmail_token_{user_id}.pickle')
        if not os.path.exists(token_file):
            return
        cal = CalendarService(token_file=token_file)
        if not cal or not cal.service:
            return
        # Create or update
        if schedule.get('calendar_event_id'):
            cal.update_event(
                schedule.get('calendar_event_id'),
                title=schedule.get('title'),
                description=schedule.get('description'),
                start_time=schedule.get('start_time'),
                end_time=schedule.get('end_time'),
                attendees=[a.strip() for a in (schedule.get('attendees') or '').split(',') if a.strip()]
            )
        else:
            event_id = cal.create_event(
                title=schedule.get('title'),
                description=schedule.get('description'),
                start_time=schedule.get('start_time'),
                end_time=schedule.get('end_time'),
                attendees=[a.strip() for a in (schedule.get('attendees') or '').split(',') if a.strip()]
            )
            if event_id:
                Schedule.update(schedule_id, calendar_event_id=event_id, db_path=db_path)
    except Exception:
        pass


@bg_bp.route('/sync-schedule', methods=['POST'])
def sync_schedule():
    data = request.get_json() or {}
    schedule_id = data.get('schedule_id')
    user_id = get_current_user_id(request)
    if not schedule_id:
        return jsonify({'error': 'missing schedule_id'}), 400

    # Fire-and-forget
    t = threading.Thread(target=_sync_to_calendar_async, args=(user_id, schedule_id), daemon=True)
    t.start()
    return jsonify({'accepted': True}), 202
