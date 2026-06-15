import os
import sys
import logging
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.schedule_service import ScheduleService
from services.calendar_service import CalendarService
from models.schedule import Schedule
from models.history import History
from utils.user_context import get_current_user_id, get_user_db_path, get_user_token_file

# Configure module logger
logger = logging.getLogger(__name__)

schedule_bp = Blueprint('schedule', __name__, url_prefix='/api/schedule')


def _parse_duration_minutes(raw_value):
    try:
        if raw_value is None or raw_value == '':
            return None
        value = int(raw_value)
        if value <= 0:
            return None
        return value
    except (TypeError, ValueError):
        return None


def _compute_end_time(start_time, end_time, duration_minutes):
    if end_time:
        return end_time
    if not start_time:
        return None
    duration = duration_minutes if duration_minutes else 60
    start_dt = datetime.fromisoformat(start_time)
    return (start_dt + timedelta(minutes=duration)).isoformat()

def _load_calendar_service(user_id):
    """Return CalendarService instance if credentials token exists."""
    if not user_id or user_id == 'default':
        return None
    token_file = get_user_token_file(user_id)
    if os.path.exists(token_file):
        try:
            return CalendarService(token_file=token_file)
        except Exception as e:
            logger.warning(f"Error creating CalendarService: {e}")
    return None


def _normalize_attendees(attendees_value):
    if not attendees_value:
        return []
    if isinstance(attendees_value, list):
        return [item.strip() for item in attendees_value if str(item).strip()]
    if isinstance(attendees_value, str):
        return [item.strip() for item in attendees_value.split(',') if item.strip()]
    return []


def _sync_schedule_to_calendar(user_id, schedule_id, schedule_payload, db_path):
    """Create or update the corresponding Google Calendar event."""
    calendar_service = _load_calendar_service(user_id)
    if not calendar_service:
        return None

    calendar_event_id = schedule_payload.get('calendar_event_id')
    attendees = _normalize_attendees(schedule_payload.get('attendees'))

    try:
        if calendar_event_id:
            success = calendar_service.update_event(
                event_id=calendar_event_id,
                title=schedule_payload.get('title'),
                description=schedule_payload.get('description'),
                start_time=schedule_payload.get('start_time'),
                end_time=schedule_payload.get('end_time'),
                attendees=attendees or None
            )
            if success:
                return calendar_event_id
            logger.warning(f"Calendar update failed for schedule {schedule_id}, will try recreate")

        new_event_id = calendar_service.create_event(
            title=schedule_payload.get('title'),
            description=schedule_payload.get('description', ''),
            start_time=schedule_payload.get('start_time'),
            end_time=schedule_payload.get('end_time'),
            attendees=attendees,
            location=schedule_payload.get('location', '') or ''
        )
        if new_event_id:
            Schedule.update(schedule_id, calendar_event_id=new_event_id, db_path=db_path)
            logger.info(f"Schedule {schedule_id} synced to Google Calendar: {new_event_id}")
            return new_event_id
    except Exception as e:
        logger.warning(f"Failed to sync schedule {schedule_id} to Google Calendar: {e}")

    return None

@schedule_bp.route('/create', methods=['POST'])
def create_schedule():
    """Create new schedule and sync to Google Calendar"""
    data = request.get_json()
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    start_time = data.get('start_time', '').strip()
    end_time = data.get('end_time', '').strip() if data.get('end_time') else None
    duration_minutes = _parse_duration_minutes(data.get('duration_minutes'))
    location = data.get('location', '').strip() if data.get('location') else None
    attendees = data.get('attendees', [])
    
    if not all([title, start_time]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        end_time = _compute_end_time(start_time, end_time, duration_minutes)

        # Create schedule in local database
        schedule_id = ScheduleService.create_schedule(
            title,
            description,
            start_time,
            attendees,
            end_time=end_time,
            location=location,
            duration_minutes=duration_minutes,
            db_path=db_path
        )

        created_schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
        event_start = created_schedule.get('start_time') if created_schedule else start_time
        event_end = created_schedule.get('end_time') if created_schedule else end_time
        calendar_event_id = created_schedule.get('calendar_event_id') if created_schedule else None
        
        # Trigger background sync to Google Calendar (non-blocking)
        try:
            # Spawn a background worker via internal endpoint
            from threading import Thread
            def _bg():
                try:
                    token_file = get_user_token_file(user_id)
                    if os.path.exists(token_file):
                        # call internal sync function directly to avoid HTTP
                        from services.calendar_service import CalendarService
                        schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
                        cal = CalendarService(token_file=token_file)
                        if cal and getattr(cal, 'service', None):
                            if schedule.get('calendar_event_id'):
                                cal.update_event(
                                    event_id=schedule.get('calendar_event_id'),
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
            Thread(target=_bg, daemon=True).start()
        except Exception:
            pass
        
        # Save to history
        attendee_list = ', '.join(attendees) if attendees else 'Không có người tham dự'
        History.create(
            f"Tạo lịch hẹn: {title}",
            f"Lịch hẹn: {title} vào {start_time}\nNguời tham dự: {attendee_list}",
            action_type='schedule_created',
            related_id=schedule_id,
            db_path=db_path
        )
        
        return jsonify({
            'success': True,
            'schedule_id': schedule_id,
            'calendar_event_id': calendar_event_id,
            'synced_to_calendar': bool(calendar_event_id),
            'start_time': event_start,
            'end_time': event_end,
            'message': 'Lịch hẹn đã được tạo' + (' và đồng bộ với Google Calendar' if calendar_event_id else '')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@schedule_bp.route('/list', methods=['GET'])
def list_schedules():
    """Get all schedules"""
    try:
        user_id = get_current_user_id(request)
        db_path = get_user_db_path(user_id)
        schedules = Schedule.get_all(db_path=db_path)
        return jsonify({
            'success': True,
            'schedules': schedules
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@schedule_bp.route('/upcoming', methods=['GET'])
def get_upcoming():
    """Get upcoming schedules"""
    try:
        user_id = get_current_user_id(request)
        db_path = get_user_db_path(user_id)
        upcoming = ScheduleService.get_upcoming_schedules(db_path=db_path)
        return jsonify({
            'success': True,
            'schedules': upcoming
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@schedule_bp.route('/<int:schedule_id>/update-status', methods=['PATCH'])
def update_status(schedule_id):
    """Update schedule status"""
    data = request.get_json()
    status = data.get('status', '').strip()
    
    if not status:
        return jsonify({'error': 'Missing status'}), 400
    
    try:
        user_id = get_current_user_id(request)
        db_path = get_user_db_path(user_id)
        Schedule.update_status(schedule_id, status, db_path=db_path)
        History.create(
            f"Cập nhật trạng thái lịch hẹn",
            f"Trạng thái: {status}",
            action_type='schedule_updated',
            related_id=schedule_id,
            db_path=db_path
        )
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@schedule_bp.route('/<int:schedule_id>', methods=['PUT'])
def update_schedule(schedule_id):
    """Update schedule information and Google Calendar event"""
    data = request.get_json() or {}
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    
    # Get current schedule
    schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
    if not schedule:
        return jsonify({'error': 'Schedule not found'}), 404
    
    # Prepare update data
    update_data = {}
    if 'title' in data:
        update_data['title'] = data.get('title', '').strip()
    if 'description' in data:
        update_data['description'] = data.get('description', '').strip()
    if 'start_time' in data:
        update_data['start_time'] = data.get('start_time', '').strip()
    if 'end_time' in data:
        update_data['end_time'] = data.get('end_time', '').strip() or None
    duration_minutes = _parse_duration_minutes(data.get('duration_minutes'))
    if 'attendees' in data:
        attendees = data.get('attendees', [])
        update_data['attendees'] = ','.join(attendees) if isinstance(attendees, list) else attendees
    
    try:
        if 'start_time' in update_data and ('end_time' not in update_data or not update_data.get('end_time')):
            update_data['end_time'] = _compute_end_time(update_data.get('start_time'), None, duration_minutes)

        Schedule.update(schedule_id, db_path=db_path, **update_data)
        
        # Try to update Google Calendar event, or create one if it does not exist yet.
        updated_schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
        _sync_schedule_to_calendar(user_id, schedule_id, updated_schedule or {**schedule, **update_data}, db_path)
        
        History.create(
            f"Chỉnh sửa lịch hẹn: {schedule.get('title', '')}",
            f"Cập nhật: {', '.join(update_data.keys())}",
            action_type='schedule_updated',
            related_id=schedule_id,
            db_path=db_path
        )
        
        updated = Schedule.get_by_id(schedule_id, db_path=db_path)
        return jsonify({
            'success': True,
            'schedule': updated
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@schedule_bp.route('/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    """Delete schedule and Google Calendar event"""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    
    # Get schedule info before deleting
    schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
    if not schedule:
        return jsonify({'error': 'Schedule not found'}), 404
    
    try:
        # Delete from Google Calendar if event exists
        calendar_event_id = schedule.get('calendar_event_id')
        if calendar_event_id:
            calendar_service = _load_calendar_service(user_id)
            if calendar_service:
                try:
                    calendar_service.delete_event(event_id=calendar_event_id)
                    logger.info(f"Calendar event deleted: {calendar_event_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete Google Calendar event: {e}")
        
        # Delete from local database
        Schedule.delete(schedule_id, db_path=db_path)
        
        History.create(
            f"Xóa lịch hẹn: {schedule.get('title', '')}",
            f"Lịch hẹn đã bị xóa" + (f" (Google Calendar event: {calendar_event_id})" if calendar_event_id else ""),
            action_type='schedule_deleted',
            related_id=schedule_id,
            db_path=db_path
        )
        
        return jsonify({
            'success': True,
            'message': f"Đã xóa lịch hẹn: {schedule.get('title', '')}"
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
