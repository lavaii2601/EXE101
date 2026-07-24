import os
import sys
import logging
import threading
from flask import Blueprint, request, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.calendar_service import CalendarService
from models.cache import Cache
from models.calendar_event import CalendarEvent
from models.history import History
from models.schedule import Schedule
from utils.user_context import get_current_user_id, get_user_db_path, get_user_token_file
from utils.google_service_cache import get_cached_service

# Configure module logger
logger = logging.getLogger(__name__)

# Google Calendar endpoints
calendar_bp = Blueprint('calendar', __name__, url_prefix='/api/calendar')

def _load_calendar_service(user_id):
    """Return a cached CalendarService instance if credentials token exists."""
    if not user_id or user_id == 'default':
        return None
    token_file = get_user_token_file(user_id)
    if os.path.exists(token_file):
        try:
            return get_cached_service(
                token_file,
                lambda: CalendarService(token_file=token_file),
                service_kind='calendar',
            )
        except Exception as e:
            logger.error(f"Error creating CalendarService: {e}")
    return None


def _clear_schedule_cache(db_path):
    try:
        Cache.clear_pattern('schedule:%', db_path=db_path)
    except Exception:
        logger.debug("Could not clear schedule cache", exc_info=True)


def _delete_google_event_async(user_id, event_id, db_path):
    if not event_id:
        return False

    def _bg():
        try:
            service = _load_calendar_service(user_id)
            if service:
                service.delete_event(event_id=event_id)
            CalendarEvent.delete_google_event(user_id, event_id, db_path=db_path)
            _clear_schedule_cache(db_path)
        except Exception:
            logger.debug("Background Google Calendar delete failed for %s", event_id, exc_info=True)

    threading.Thread(target=_bg, daemon=True).start()
    return True


@calendar_bp.route('/events', methods=['GET'])
def get_calendar_events():
    """Get upcoming calendar events"""
    user_id = get_current_user_id(request)
    logger.info(f"get_calendar_events: user_id = {user_id}")
    
    service = _load_calendar_service(user_id)
    if not service:
        logger.warning(f"Calendar service not available for user: {user_id}")
        return jsonify({
            'error': 'not_authenticated',
            'message': 'User not authenticated with Google Calendar'
        }), 401
    
    try:
        max_results = request.args.get('max_results', 10, type=int)
        time_min = request.args.get('time_min', None, type=str)
        time_max = request.args.get('time_max', None, type=str)
        
        events = service.get_events(
            max_results=max_results,
            time_min=time_min,
            time_max=time_max,
            raise_errors=True,
        )
        
        return jsonify({
            'success': True,
            'events': events,
            'count': len(events)
        })
    except Exception as e:
        logger.error(f"Error in get_calendar_events: {str(e)}", exc_info=True)
        google_status = getattr(getattr(e, 'resp', None), 'status', None)
        if google_status in (401, 403):
            return jsonify({
                'error': 'google_reauthentication_required',
                'message': 'Phiên Google đã hết hạn hoặc thiếu quyền Calendar. Vui lòng kết nối lại.',
                'needs_reauth': True,
                'google_status': google_status,
            }), 401
        return jsonify({'error': str(e)}), 500


@calendar_bp.route('/create', methods=['POST'])
def create_calendar_event():
    """Create a new calendar event"""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    logger.info(f"create_calendar_event: user_id = {user_id}")
    
    service = _load_calendar_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401
    
    try:
        data = request.get_json()
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        start_time = data.get('start_time', '').strip()
        end_time = data.get('end_time', '').strip()
        attendees = data.get('attendees', [])
        location = data.get('location', '').strip()
        
        if not all([title, start_time]):
            return jsonify({'error': 'Missing required fields: title, start_time'}), 400
        
        event_id = service.create_event(
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            location=location
        )
        
        if not event_id:
            return jsonify({'error': 'Failed to create calendar event'}), 500

        if not Schedule.get_by_calendar_event_id(event_id, db_path=db_path):
            Schedule.create(
                title=title,
                description=description,
                start_time=start_time,
                end_time=end_time,
                attendees=','.join(attendees) if isinstance(attendees, list) else attendees,
                email_body='',
                location=location,
                calendar_event_id=event_id,
                db_path=db_path
            )
            _clear_schedule_cache(db_path)
        
        # Save to history
        attendee_list = ', '.join(attendees) if attendees else 'Không có người tham dự'
        History.create(
            f"Tạo sự kiện Google Calendar: {title}",
            f"Sự kiện: {title}\nThời gian: {start_time}\nNguời tham dự: {attendee_list}",
            action_type='calendar_event_created',
            related_id=event_id,
            db_path=db_path
        )
        
        return jsonify({
            'success': True,
            'event_id': event_id,
            'message': f'Calendar event "{title}" created successfully'
        }), 201
    except Exception as e:
        logger.error(f"Error in create_calendar_event: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@calendar_bp.route('/update/<event_id>', methods=['PUT'])
def update_calendar_event(event_id):
    """Update a calendar event"""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    logger.info(f"update_calendar_event: event_id = {event_id}, user_id = {user_id}")
    
    service = _load_calendar_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401
    
    try:
        data = request.get_json()
        title = data.get('title')
        description = data.get('description')
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        attendees = data.get('attendees')
        
        success = service.update_event(
            event_id=event_id,
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees
        )
        
        if not success:
            return jsonify({'error': 'Failed to update calendar event'}), 500
        
        # Save to history
        History.create(
            f"Cập nhật sự kiện Google Calendar: {title or event_id}",
            f"Sự kiện ID: {event_id}",
            action_type='calendar_event_updated',
            related_id=event_id,
            db_path=db_path
        )
        
        return jsonify({
            'success': True,
            'message': f'Calendar event "{event_id}" updated successfully'
        })
    except Exception as e:
        logger.error(f"Error in update_calendar_event: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@calendar_bp.route('/delete/<event_id>', methods=['DELETE'])
def delete_calendar_event(event_id):
    """Delete a calendar event locally immediately and remove it from Google in the background."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    logger.info(f"delete_calendar_event: event_id = {event_id}, user_id = {user_id}")

    try:
        local_schedule = Schedule.get_by_calendar_event_id(event_id, db_path=db_path)
        if local_schedule:
            Schedule.delete(local_schedule.get('id'), db_path=db_path)
        CalendarEvent.delete_google_event(user_id, event_id, db_path=db_path)
        _clear_schedule_cache(db_path)
        calendar_delete_pending = _delete_google_event_async(user_id, event_id, db_path)

        History.create(
            f"Xoa su kien Google Calendar: {event_id}",
            f"Su kien ID queued for delete: {event_id}",
            action_type='calendar_event_deleted',
            related_id=event_id,
            db_path=db_path
        )

        return jsonify({
            'success': True,
            'message': f'Calendar event "{event_id}" delete queued',
            'calendar_delete_pending': calendar_delete_pending
        })

        success = service.delete_event(event_id=event_id)
        
        if not success:
            return jsonify({'error': 'Failed to delete calendar event'}), 500

        local_schedule = Schedule.get_by_calendar_event_id(event_id, db_path=db_path)
        if local_schedule:
            Schedule.delete(local_schedule.get('id'), db_path=db_path)
        _clear_schedule_cache(db_path)
        
        # Save to history
        History.create(
            f"Xóa sự kiện Google Calendar: {event_id}",
            f"Sự kiện ID: {event_id}",
            action_type='calendar_event_deleted',
            related_id=event_id,
            db_path=db_path
        )
        
        return jsonify({
            'success': True,
            'message': f'Calendar event "{event_id}" deleted successfully'
        })
    except Exception as e:
        logger.error(f"Error in delete_calendar_event: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500
