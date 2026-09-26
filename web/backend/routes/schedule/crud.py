"""Core schedule CRUD routes: create/list/get/update-status/update/delete.
Sync-on-write (pushing a new/changed schedule to Google Calendar, cleaning
up stale duplicates after a move, retracting a deleted event) delegates to
gcal_sync.py's async helpers."""
from flask import request, jsonify

from services.schedule_service import ScheduleService
from models.schedule import Schedule
from models.calendar_event import CalendarEvent
from models.history import History
from utils.user_context import get_current_user_id, get_user_db_path

from .shared import schedule_bp, _parse_duration_minutes, _compute_end_time, _clear_schedule_cache
from .gcal_sync import (
    _calendar_auth_failure_payload,
    _sync_schedule_to_calendar_async,
    _delete_calendar_event_async,
    _prune_stale_duplicate_after_move_async,
)


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
        calendar_sync_error = _calendar_auth_failure_payload(user_id)
        calendar_sync_pending = _sync_schedule_to_calendar_async(user_id, schedule_id, db_path)

        # Save to history
        attendee_list = ', '.join(attendees) if attendees else 'Không có người tham dự'
        History.create(
            f"Tạo lịch hẹn: {title}",
            f"Lịch hẹn: {title} vào {start_time}\nNguời tham dự: {attendee_list}",
            action_type='schedule_created',
            related_id=schedule_id,
            db_path=db_path
        )
        _clear_schedule_cache(db_path)

        return jsonify({
            'success': True,
            'schedule_id': schedule_id,
            'calendar_event_id': calendar_event_id,
            'synced_to_calendar': bool(calendar_event_id),
            'calendar_sync_pending': calendar_sync_pending,
            'calendar_sync_error': calendar_sync_error,
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


@schedule_bp.route('/<int:schedule_id>', methods=['GET'])
def get_schedule(schedule_id):
    """Get one schedule by ID."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
    if not schedule:
        return jsonify({'error': 'Schedule not found'}), 404
    return jsonify({
        'success': True,
        'schedule': schedule
    })


@schedule_bp.route('/<int:schedule_id>/update-status', methods=['PATCH', 'POST'])
def update_status(schedule_id):
    """Update schedule status"""
    data = request.get_json(silent=True) or {}
    status = str(data.get('status') or '').strip().lower()

    if not status:
        return jsonify({'error': 'Missing status'}), 400
    if status not in {'pending', 'completed', 'cancelled', 'dismissed'}:
        return jsonify({'error': 'Invalid status'}), 400

    try:
        user_id = get_current_user_id(request)
        db_path = get_user_db_path(user_id)
        expected_updated_at = data.get('expected_updated_at')
        changed = Schedule.update_status(
            schedule_id,
            status,
            db_path=db_path,
            expected_updated_at=expected_updated_at,
        )
        if not changed:
            current = Schedule.get_by_id(schedule_id, db_path=db_path)
            if not current:
                return jsonify({'error': 'Schedule not found'}), 404
            return jsonify({
                'error': 'schedule_conflict',
                'message': 'Schedule changed on another device. Reload and try again.',
                'current_schedule': current,
            }), 409
        _clear_schedule_cache(db_path)
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
    if 'location' in data:
        update_data['location'] = data.get('location', '').strip()
    duration_minutes = _parse_duration_minutes(data.get('duration_minutes'))
    if 'attendees' in data:
        attendees = data.get('attendees', [])
        update_data['attendees'] = ','.join(attendees) if isinstance(attendees, list) else attendees

    try:
        if 'start_time' in update_data and ('end_time' not in update_data or not update_data.get('end_time')):
            update_data['end_time'] = _compute_end_time(update_data.get('start_time'), None, duration_minutes)

        changed = Schedule.update(
            schedule_id,
            db_path=db_path,
            expected_updated_at=data.get('expected_updated_at'),
            **update_data,
        )
        if not changed:
            current = Schedule.get_by_id(schedule_id, db_path=db_path)
            if not current:
                return jsonify({'error': 'Schedule not found'}), 404
            return jsonify({
                'error': 'schedule_conflict',
                'message': 'Schedule changed on another device. Reload and try again.',
                'current_schedule': current,
            }), 409
        _clear_schedule_cache(db_path)
        updated = Schedule.get_by_id(schedule_id, db_path=db_path)

        calendar_sync_pending = _sync_schedule_to_calendar_async(user_id, schedule_id, db_path)
        _prune_stale_duplicate_after_move_async(user_id, db_path, schedule_id, schedule, updated)

        History.create(
            f"Chỉnh sửa lịch hẹn: {schedule.get('title', '')}",
            f"Cập nhật: {', '.join(update_data.keys())}",
            action_type='schedule_updated',
            related_id=schedule_id,
            db_path=db_path
        )

        return jsonify({
            'success': True,
            'schedule': updated,
            'calendar_sync_pending': calendar_sync_pending,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@schedule_bp.route('/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    """Delete schedule locally immediately and remove Google Calendar event in the background."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)

    # Get schedule info before deleting
    schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
    if not schedule:
        return jsonify({'error': 'Schedule not found'}), 404

    try:
        calendar_event_id = schedule.get('calendar_event_id')
        Schedule.delete(schedule_id, db_path=db_path)
        if calendar_event_id:
            CalendarEvent.delete_google_event(user_id, calendar_event_id, db_path=db_path)
        _clear_schedule_cache(db_path)
        calendar_delete_pending = _delete_calendar_event_async(user_id, calendar_event_id, db_path)

        History.create(
            f"Xoa lich hen: {schedule.get('title', '')}",
            f"Lich hen da bi xoa" + (f" (Google Calendar event queued for delete: {calendar_event_id})" if calendar_event_id else ""),
            action_type='schedule_deleted',
            related_id=schedule_id,
            db_path=db_path
        )

        return jsonify({
            'success': True,
            'message': f"Da xoa lich hen: {schedule.get('title', '')}",
            'calendar_delete_pending': calendar_delete_pending
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
