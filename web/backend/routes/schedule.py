import os
import sys
import logging
import threading
import time
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.schedule_service import ScheduleService
from services.calendar_service import CalendarService
from models.cache import Cache
from models.calendar_event import CalendarEvent
from models.schedule import Schedule, LOCAL_TZ
from models.history import History
from models.sync_job import SyncJob
from utils.user_context import get_current_user_id, get_user_db_path, get_user_token_file
from utils.google_service_cache import get_cached_service

# Configure module logger
logger = logging.getLogger(__name__)

schedule_bp = Blueprint('schedule', __name__, url_prefix='/api/schedule')
_week_sync_lock = threading.Lock()
_week_sync_inflight = set()
_week_sync_recent = {}
_WEEK_SYNC_TTL_SECONDS = 90
_SCHEDULE_CACHE_TTL_SECONDS = 15
_FULL_SYNC_DAYS = int(os.getenv('SCHEDULE_FULL_SYNC_DAYS', '90'))
_LOCAL_EDIT_SYNC_GRACE_SECONDS = 180


def _schedule_cache_key(user_id, name, *parts):
    safe_parts = [str(part).replace('%', '').replace(':', '-') for part in parts if part is not None]
    return 'schedule:' + ':'.join([user_id, name, *safe_parts])


def _clear_schedule_cache(db_path):
    try:
        Cache.clear_pattern('schedule:%', db_path=db_path)
    except Exception:
        logger.debug("Could not clear schedule cache", exc_info=True)


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
    """Return a cached CalendarService instance if credentials token exists."""
    if not user_id or user_id == 'default':
        return None
    token_file = get_user_token_file(user_id)
    if os.path.exists(token_file):
        try:
            return get_cached_service(token_file, lambda: CalendarService(token_file=token_file))
        except Exception as e:
            logger.warning(f"Error creating CalendarService: {e}")
    return None


def _has_calendar_token(user_id):
    """Fast connectivity check without constructing a Google API client."""
    if not user_id or user_id == 'default':
        return False
    return os.path.exists(get_user_token_file(user_id))


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
            _clear_schedule_cache(db_path)
            logger.info(f"Schedule {schedule_id} synced to Google Calendar: {new_event_id}")
            return new_event_id
    except Exception as e:
        logger.warning(f"Failed to sync schedule {schedule_id} to Google Calendar: {e}")

    return None


def _sync_schedule_to_calendar_async(user_id, schedule_id, db_path):
    if not _has_calendar_token(user_id):
        return False

    def _bg():
        try:
            schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
            if schedule:
                _sync_schedule_to_calendar(user_id, schedule_id, schedule, db_path)
        except Exception:
            logger.debug("Background calendar sync failed for schedule %s", schedule_id, exc_info=True)

    threading.Thread(target=_bg, daemon=True).start()
    return True


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

def _parse_dt(value):
    """Parse an ISO datetime/date string into a naive local datetime."""
    if not value:
        return None
    try:
        cleaned = value.replace('Z', '+00:00')
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(LOCAL_TZ).replace(tzinfo=None)
    return dt


def _event_fingerprint(title, start_time):
    """Build a stable fallback key for events that do not share a Google ID."""
    start_dt = _parse_dt(start_time)
    normalized_start = start_dt.isoformat(timespec='minutes') if start_dt else str(start_time or '')
    normalized_title = ' '.join(str(title or '').strip().lower().split())
    return f'{normalized_title}|{normalized_start}'


def _schedule_fingerprint(schedule):
    return _event_fingerprint(schedule.get('title'), schedule.get('start_time'))


def _recently_updated(schedule, seconds=_LOCAL_EDIT_SYNC_GRACE_SECONDS):
    updated_at = _parse_dt((schedule or {}).get('updated_at'))
    if not updated_at:
        return False
    return 0 <= (datetime.now() - updated_at).total_seconds() <= seconds


def _google_sync_would_overwrite_recent_edit(schedule, event_payload):
    if not _recently_updated(schedule):
        return False
    local_start = _parse_dt((schedule or {}).get('start_time'))
    google_start = _parse_dt((event_payload or {}).get('start_time'))
    local_end = _parse_dt((schedule or {}).get('end_time'))
    google_end = _parse_dt((event_payload or {}).get('end_time'))
    if not local_start or not google_start:
        return False
    starts_differ = abs((local_start - google_start).total_seconds()) > 60
    ends_differ = bool(local_end and google_end and abs((local_end - google_end).total_seconds()) > 60)
    return starts_differ or ends_differ


def _normalize_compare_text(value):
    return str(value or '').strip()


def _normalize_compare_attendees(value):
    if isinstance(value, list):
        attendees = value
    else:
        attendees = str(value or '').split(',')
    return sorted({str(item or '').strip().lower() for item in attendees if str(item or '').strip()})


def _datetimes_equal(left, right, tolerance_seconds=60):
    left_dt = _parse_dt(left)
    right_dt = _parse_dt(right)
    if not left_dt and not right_dt:
        return True
    if not left_dt or not right_dt:
        return False
    return abs((left_dt - right_dt).total_seconds()) <= tolerance_seconds


def _schedule_matches_google_payload(schedule, event_payload):
    if not schedule:
        return False
    text_fields = ('title', 'description', 'location')
    for field in text_fields:
        if _normalize_compare_text(schedule.get(field)) != _normalize_compare_text(event_payload.get(field)):
            return False
    if not _datetimes_equal(schedule.get('start_time'), event_payload.get('start_time')):
        return False
    if not _datetimes_equal(schedule.get('end_time'), event_payload.get('end_time')):
        return False
    return _normalize_compare_attendees(schedule.get('attendees')) == _normalize_compare_attendees(event_payload.get('attendees'))


def _dedupe_schedule_items(schedules):
    """Return one display item for duplicate local/Google-backed copies."""
    by_google_id = {}
    by_fingerprint = {}
    result = []

    def priority(item):
        if item.get('calendar_event_id') or item.get('google_event_id'):
            return 2
        if item.get('source') == 'google':
            return 1
        return 0

    for item in schedules:
        google_id = item.get('calendar_event_id') or item.get('google_event_id') or ''
        fingerprint = _schedule_fingerprint(item)
        existing = by_google_id.get(google_id) if google_id else None
        if not existing:
            existing = by_fingerprint.get(fingerprint)
        if not existing:
            result.append(item)
            if google_id:
                by_google_id[google_id] = item
            by_fingerprint[fingerprint] = item
            continue

        if priority(item) > priority(existing):
            index = result.index(existing)
            result[index] = item
            if google_id:
                by_google_id[google_id] = item
            by_fingerprint[fingerprint] = item

    return result


def _prune_expired_google_backed_schedules(db_path):
    """Keep DB schedule summaries lean; Google remains the source of history."""
    try:
        deleted = Schedule.delete_expired_google_backed(datetime.now(), db_path=db_path)
        if deleted:
            _clear_schedule_cache(db_path)
            logger.info("Pruned %s expired Google-backed schedules", deleted)
        return deleted
    except Exception:
        logger.debug("Could not prune expired schedules", exc_info=True)
        return 0


def _prune_local_duplicates_for_google_events(db_path):
    """Remove stale local copies once an equivalent Google-backed schedule exists."""
    try:
        schedules = Schedule.get_all(limit=1000, db_path=db_path)
        google_backed_fingerprints = {
            _schedule_fingerprint(schedule)
            for schedule in schedules
            if schedule.get('calendar_event_id')
        }
        deleted = 0
        for schedule in schedules:
            if schedule.get('calendar_event_id'):
                continue
            if _schedule_fingerprint(schedule) in google_backed_fingerprints:
                if Schedule.delete(schedule.get('id'), db_path=db_path):
                    deleted += 1
        if deleted:
            _clear_schedule_cache(db_path)
            logger.info("Pruned %s duplicate local schedules after Google sync", deleted)
        return deleted
    except Exception:
        logger.debug("Could not prune duplicate local schedules", exc_info=True)
        return 0


def _unified_schedule_item(schedule):
    google_event_id = schedule.get('calendar_event_id') or ''
    return {
        **schedule,
        'local_id': schedule.get('id'),
        'google_event_id': google_event_id,
        'source': 'synced' if google_event_id else 'local',
    }


def _sync_google_events_range(user_id, db_path, start_time, end_time, max_results=250):
    calendar_service = _load_calendar_service(user_id)
    if not calendar_service:
        return {
            'created_count': 0,
            'updated_count': 0,
            'deleted_count': 0,
            'unchanged_count': 0,
            'changed_count': 0,
        }

    time_min = start_time.replace(tzinfo=LOCAL_TZ).isoformat()
    time_max = end_time.replace(tzinfo=LOCAL_TZ).isoformat()
    gcal_events = calendar_service.get_events(max_results=max_results, time_min=time_min, time_max=time_max)
    live_google_ids = {event.get('id') for event in gcal_events if event.get('id')}
    local_schedules = Schedule.get_all(limit=1000, db_path=db_path)
    schedules_by_google_id = {
        schedule.get('calendar_event_id'): schedule
        for schedule in local_schedules
        if schedule.get('calendar_event_id')
    }
    local_by_fingerprint = {
        _schedule_fingerprint(schedule): schedule
        for schedule in local_schedules
        if not schedule.get('calendar_event_id')
    }
    created_count = 0
    updated_count = 0
    deleted_count = 0
    unchanged_count = 0

    for event in gcal_events:
        event_id = event.get('id')
        if not event_id:
            continue
        existing_schedule = schedules_by_google_id.get(event_id)
        if existing_schedule and CalendarEvent.google_event_unchanged(user_id, event, db_path=db_path):
            unchanged_count += 1
            continue
        event_payload = {
            'title': event.get('title') or 'Untitled',
            'description': event.get('description') or '',
            'start_time': event.get('start'),
            'end_time': event.get('end'),
            'attendees': ','.join(event.get('attendees') or []),
            'location': event.get('location') or '',
        }
        if existing_schedule:
            if _google_sync_would_overwrite_recent_edit(existing_schedule, event_payload):
                logger.info(
                    "Skipped stale Google Calendar overwrite for recently edited schedule %s",
                    existing_schedule.get('id')
                )
                unchanged_count += 1
                continue
            if _schedule_matches_google_payload(existing_schedule, event_payload):
                CalendarEvent.upsert_google_event(user_id, event, schedule_id=existing_schedule.get('id'), db_path=db_path)
                unchanged_count += 1
                continue
            Schedule.update(
                existing_schedule.get('id'),
                **event_payload,
                db_path=db_path
            )
            CalendarEvent.upsert_google_event(user_id, event, schedule_id=existing_schedule.get('id'), db_path=db_path)
            updated_count += 1
            continue

        event_fingerprint = _event_fingerprint(event_payload['title'], event_payload['start_time'])
        matching_local = local_by_fingerprint.get(event_fingerprint)
        if matching_local:
            Schedule.update(
                matching_local.get('id'),
                **event_payload,
                calendar_event_id=event_id,
                db_path=db_path
            )
            schedules_by_google_id[event_id] = {**matching_local, **event_payload, 'calendar_event_id': event_id}
            CalendarEvent.upsert_google_event(user_id, event, schedule_id=matching_local.get('id'), db_path=db_path)
            updated_count += 1
            continue

        schedule_id = Schedule.create(
            title=event_payload['title'],
            description=event_payload['description'],
            start_time=event_payload['start_time'],
            end_time=event_payload['end_time'],
            attendees=event_payload['attendees'],
            email_body='',
            location=event_payload['location'],
            calendar_event_id=event_id,
            db_path=db_path
        )
        CalendarEvent.upsert_google_event(user_id, event, schedule_id=schedule_id, db_path=db_path)
        created_count += 1

    for schedule in local_schedules:
        calendar_event_id = schedule.get('calendar_event_id')
        if not calendar_event_id or calendar_event_id in live_google_ids:
            continue

        start_dt = _parse_dt(schedule.get('start_time'))
        if not start_dt or not (start_time <= start_dt < end_time):
            continue

        exists = calendar_service.event_exists(calendar_event_id)
        if exists is False:
            Schedule.delete(schedule.get('id'), db_path=db_path)
            CalendarEvent.delete_google_event(user_id, calendar_event_id, db_path=db_path)
            deleted_count += 1
            logger.info(f"Removed local schedule for deleted Google event: {calendar_event_id}")

    pruned_count = _prune_expired_google_backed_schedules(db_path)
    duplicate_deleted_count = _prune_local_duplicates_for_google_events(db_path)
    changed_count = created_count + updated_count + deleted_count + pruned_count + duplicate_deleted_count
    if changed_count:
        _clear_schedule_cache(db_path)
    return {
        'created_count': created_count,
        'updated_count': updated_count,
        'deleted_count': deleted_count + pruned_count + duplicate_deleted_count,
        'unchanged_count': unchanged_count,
        'changed_count': changed_count,
    }


def _sync_google_week_events(user_id, db_path, monday, week_end):
    return _sync_google_events_range(user_id, db_path, monday, week_end, max_results=250)


def _start_week_sync(user_id, db_path, monday, week_end, force=False):
    if not _has_calendar_token(user_id):
        return False

    key = (user_id, monday.date().isoformat())
    now = time.monotonic()
    with _week_sync_lock:
        last_sync = _week_sync_recent.get(key, 0)
        if key in _week_sync_inflight or (not force and now - last_sync < _WEEK_SYNC_TTL_SECONDS):
            return False
        _week_sync_inflight.add(key)

    def _worker():
        try:
            _sync_google_week_events(user_id, db_path, monday, week_end)
            with _week_sync_lock:
                _week_sync_recent[key] = time.monotonic()
        except Exception as e:
            logger.warning(f"Failed to sync Google Calendar events for week: {e}")
        finally:
            with _week_sync_lock:
                _week_sync_inflight.discard(key)

    threading.Thread(target=_worker, daemon=True).start()
    return True


@schedule_bp.route('/sync', methods=['POST'])
def sync_schedules():
    """Scan Google Calendar into the local schedule summary on demand."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)

    if not _has_calendar_token(user_id):
        return jsonify({
            'success': False,
            'error': 'not_authenticated',
            'message': 'User not authenticated with Google Calendar'
        })

    try:
        now = datetime.now()
        sync_days = min(max(request.args.get('days', _FULL_SYNC_DAYS, type=int), 1), 365)
        sync_end = now + timedelta(days=sync_days)
        max_results = min(max(request.args.get('max_results', sync_days * 8, type=int), 50), 2500)
        job_id = SyncJob.start(user_id, 'google_calendar_sync', {
            'sync_days': sync_days,
            'max_results': max_results,
            'sync_start': now.isoformat(),
            'sync_end': sync_end.isoformat(),
        }, db_path=db_path)
        sync_result = _sync_google_events_range(
            user_id,
            db_path,
            now.replace(hour=0, minute=0, second=0, microsecond=0),
            sync_end,
            max_results=max_results
        )
        SyncJob.finish(job_id, 'success', sync_result)
        return jsonify({
            'success': True,
            **sync_result,
            'sync_start': now.isoformat(),
            'sync_end': sync_end.isoformat(),
            'sync_days': sync_days,
        })
    except Exception as e:
        logger.error(f"Error syncing schedules: {e}", exc_info=True)
        try:
            SyncJob.finish(locals().get('job_id'), 'failed', error_message=str(e))
        except Exception:
            logger.debug("Could not mark sync job as failed", exc_info=True)
        return jsonify({'error': str(e)}), 500


@schedule_bp.route('/unified', methods=['GET'])
def get_unified_schedules():
    """Merge upcoming local schedules and Google Calendar events into one timeline."""
    try:
        user_id = get_current_user_id(request)
        db_path = get_user_db_path(user_id)
        _prune_expired_google_backed_schedules(db_path)
        now = datetime.now()
        max_results = min(max(request.args.get('max_results', 50, type=int), 1), 200)
        live_google = request.args.get('live', '0') == '1'
        cache_key = _schedule_cache_key(user_id, 'unified', max_results, int(live_google))
        cached = Cache.get(cache_key, db_path=db_path)
        if cached:
            return jsonify(cached)

        local_schedules = []
        for schedule in Schedule.get_all(limit=200, db_path=db_path):
            start_dt = _parse_dt(schedule.get('start_time'))
            if start_dt and start_dt >= now:
                local_schedules.append(_unified_schedule_item(schedule))

        by_google_id = {
            item['google_event_id']: item
            for item in local_schedules
            if item.get('google_event_id')
        }
        by_fingerprint = {
            _event_fingerprint(item.get('title'), item.get('start_time')): item
            for item in local_schedules
        }

        calendar_connected = _has_calendar_token(user_id)
        if calendar_connected and live_google:
            try:
                calendar_service = _load_calendar_service(user_id)
                if not calendar_service:
                    raise RuntimeError("Google Calendar service is not available")
                time_max = (datetime.utcnow() + timedelta(days=90)).isoformat() + 'Z'
                for event in calendar_service.get_events(
                    max_results=max_results,
                    time_max=time_max
                ):
                    event_id = event.get('id') or ''
                    fingerprint = _event_fingerprint(event.get('title'), event.get('start'))
                    existing = by_google_id.get(event_id) or by_fingerprint.get(fingerprint)
                    if existing:
                        existing['source'] = 'synced'
                        existing['google_event_id'] = event_id or existing.get('google_event_id', '')
                        continue

                    item = {
                        'id': f'google:{event_id}',
                        'local_id': None,
                        'google_event_id': event_id,
                        'source': 'google',
                        'title': event.get('title') or 'Untitled',
                        'description': event.get('description') or '',
                        'start_time': event.get('start'),
                        'end_time': event.get('end'),
                        'attendees': ','.join(event.get('attendees') or []),
                        'location': event.get('location') or '',
                        'status': event.get('status') or 'confirmed',
                    }
                    local_schedules.append(item)
                    if event_id:
                        by_google_id[event_id] = item
                    by_fingerprint[fingerprint] = item
            except Exception as e:
                logger.warning(f"Failed to merge Google Calendar events: {e}")

        local_schedules = _dedupe_schedule_items(local_schedules)
        local_schedules.sort(
            key=lambda item: _parse_dt(item.get('start_time')) or datetime.max
        )
        payload = {
            'success': True,
            'items': local_schedules,
            'count': len(local_schedules),
            'calendar_connected': calendar_connected,
            'live_google': live_google,
        }
        Cache.set(cache_key, payload, ttl=_SCHEDULE_CACHE_TTL_SECONDS, db_path=db_path)
        return jsonify(payload)
    except Exception as e:
        logger.error(f"Error building unified schedule: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@schedule_bp.route('/week', methods=['GET'])
def get_week_schedules():
    """Get schedules for a Mon-Sun week and refresh Google Calendar in the background."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    _prune_expired_google_backed_schedules(db_path)

    start_param = request.args.get('start')
    ref_date = _parse_dt(start_param) if start_param else None
    if not ref_date:
        ref_date = datetime.now()

    monday = (ref_date - timedelta(days=ref_date.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = monday + timedelta(days=7)

    sync_requested = request.args.get('sync', '0') == '1'
    force_sync = request.args.get('force', '0') == '1'
    cache_key = _schedule_cache_key(user_id, 'week', monday.date().isoformat(), int(sync_requested), int(force_sync))
    cached = Cache.get(cache_key, db_path=db_path)
    if cached:
        if sync_requested:
            _start_week_sync(user_id, db_path, monday, week_end, force=force_sync)
        return jsonify(cached)

    sync_started = _start_week_sync(user_id, db_path, monday, week_end, force=force_sync) if sync_requested else False

    # Build the Mon-Sun grid from local schedules
    all_schedules = Schedule.get_all(limit=200, db_path=db_path)
    days = [[] for _ in range(7)]
    for schedule in all_schedules:
        start_dt = _parse_dt(schedule.get('start_time'))
        if not start_dt:
            continue
        day_index = (start_dt - monday).days
        if 0 <= day_index < 7:
            days[day_index].append(schedule)

    days = [_dedupe_schedule_items(day_schedules) for day_schedules in days]
    for day_schedules in days:
        day_schedules.sort(key=lambda s: s.get('start_time') or '')

    payload = {
        'success': True,
        'week_start': monday.date().isoformat(),
        'week_end': (monday + timedelta(days=6)).date().isoformat(),
        'days': days,
        'calendar_sync_pending': sync_started
    }
    Cache.set(cache_key, payload, ttl=_SCHEDULE_CACHE_TTL_SECONDS, db_path=db_path)
    return jsonify(payload)


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
    data = request.get_json()
    status = data.get('status', '').strip()
    
    if not status:
        return jsonify({'error': 'Missing status'}), 400
    
    try:
        user_id = get_current_user_id(request)
        db_path = get_user_db_path(user_id)
        Schedule.update_status(schedule_id, status, db_path=db_path)
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

        Schedule.update(schedule_id, db_path=db_path, **update_data)
        _clear_schedule_cache(db_path)
        
        calendar_sync_pending = _sync_schedule_to_calendar_async(user_id, schedule_id, db_path)
        
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
            'schedule': updated,
            'calendar_sync_pending': calendar_sync_pending,
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
                    deleted_from_calendar = calendar_service.delete_event(event_id=calendar_event_id)
                    if not deleted_from_calendar:
                        return jsonify({
                            'error': 'Không thể xóa sự kiện trên Google Calendar. Vui lòng thử lại sau.'
                        }), 502
                    logger.info(f"Calendar event deleted: {calendar_event_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete Google Calendar event: {e}")
                    return jsonify({
                        'error': 'Không thể xóa sự kiện trên Google Calendar. Vui lòng thử lại sau.'
                    }), 502
        
        # Delete from local database
        Schedule.delete(schedule_id, db_path=db_path)
        _clear_schedule_cache(db_path)
        
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
