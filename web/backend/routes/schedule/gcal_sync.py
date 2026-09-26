"""Google Calendar sync engine: auth/token status, the create/update/delete
event helpers, dedup/fingerprint-matching logic used to reconcile local
schedules with Google events, the range-sync engine, and the
sync/unified/week/upcoming routes."""
import os
import time
import threading
from datetime import datetime, timedelta

from flask import request, jsonify

from services.schedule_service import ScheduleService
from services.calendar_service import CalendarService
from models.cache import Cache
from models.calendar_event import CalendarEvent
from models.schedule import Schedule, LOCAL_TZ
from models.sync_job import SyncJob
from models.workspace_sync import WorkspaceSync
from utils.user_context import (
    get_current_user_id,
    get_user_db_path,
    get_user_token_file,
    inspect_google_credentials,
)
from utils.google_service_cache import get_cached_service

from .shared import (
    schedule_bp,
    logger,
    _schedule_cache_key,
    _SCHEDULE_CACHE_TTL_SECONDS,
    _clear_schedule_cache,
    _parse_dt,
    _event_fingerprint,
    _schedule_fingerprint,
)

_week_sync_lock = threading.Lock()
_week_sync_inflight = set()
_week_sync_recent = {}
_WEEK_SYNC_TTL_SECONDS = 90
_FULL_SYNC_DAYS = int(os.getenv('SCHEDULE_FULL_SYNC_DAYS', '90'))
_LOCAL_EDIT_SYNC_GRACE_SECONDS = 180
_GOOGLE_CALENDAR_WRITE_SCOPE = 'https://www.googleapis.com/auth/calendar.events'


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
            logger.warning(f"Error creating CalendarService: {e}")
    return None


def _google_calendar_token_status(user_id):
    """Return token presence and whether it includes Calendar write scope."""
    if not user_id or user_id == 'default':
        return {
            'has_token': False,
            'has_calendar_write_scope': False,
            'scopes': [],
            'error': 'not_authenticated',
        }
    credential_status = inspect_google_credentials(user_id, refresh=True)
    if not credential_status.get('has_token'):
        return {
            'has_token': False,
            'valid': False,
            'has_calendar_write_scope': False,
            'scopes': [],
            'error': 'not_authenticated',
        }
    scopes = credential_status.get('scopes') or []
    return {
        'has_token': True,
        'valid': bool(credential_status.get('valid')),
        'has_calendar_write_scope': _GOOGLE_CALENDAR_WRITE_SCOPE in scopes,
        'scopes': scopes,
        'error': credential_status.get('error'),
        'refreshed': bool(credential_status.get('refreshed')),
    }


def _has_calendar_token(user_id):
    """Fast connectivity check without constructing a Google API client."""
    if not user_id or user_id == 'default':
        return False
    return bool(inspect_google_credentials(user_id, refresh=False).get('valid'))


def _calendar_sync_error_payload(calendar_service=None, fallback='calendar_sync_failed'):
    reason = getattr(calendar_service, 'last_error_reason', None)
    status = getattr(calendar_service, 'last_error_status', None)
    detail = getattr(calendar_service, 'last_error', None)
    error = fallback
    message = 'Không thể đồng bộ Google Calendar.'
    if status in (401, 403) or reason in {'insufficientPermissions', 'authError', 'forbidden'}:
        error = 'calendar_permission_required'
        message = 'Token Google hiện tại thiếu quyền ghi Calendar. Hãy đăng xuất/kết nối lại Gmail & Google Calendar rồi thử đồng bộ.'
    return {
        'error': error,
        'message': message,
        'google_status': status,
        'google_reason': reason,
        'google_error': detail,
    }


def _calendar_auth_failure_payload(user_id):
    status = _google_calendar_token_status(user_id)
    if not status.get('has_token'):
        return {
            'success': False,
            'error': 'not_authenticated',
            'message': 'User not authenticated with Google Calendar',
            'calendar_token_status': status,
        }
    if not status.get('valid'):
        return {
            'success': False,
            'error': 'google_reauthentication_required',
            'message': 'Phiên Google đã hết hạn hoặc bị thu hồi. Vui lòng kết nối lại.',
            'calendar_token_status': status,
        }
    if not status.get('has_calendar_write_scope'):
        return {
            'success': False,
            'error': 'calendar_permission_required',
            'message': 'Token Google hiện tại thiếu quyền ghi Calendar. Hãy đăng xuất/kết nối lại Gmail & Google Calendar rồi thử đồng bộ.',
            'calendar_token_status': status,
        }
    return None


def _normalize_attendees(attendees_value):
    if not attendees_value:
        return []
    if isinstance(attendees_value, list):
        return [item.strip() for item in attendees_value if str(item).strip()]
    if isinstance(attendees_value, str):
        return [item.strip() for item in attendees_value.split(',') if item.strip()]
    return []


def _publish_background_calendar_link(user_id, db_path):
    """Notify clients after integration metadata changes outside a request."""
    try:
        WorkspaceSync.bump(
            user_id,
            ('schedule', 'calendar', 'overview'),
            db_path=db_path,
        )
    except Exception:
        logger.debug(
            "Could not publish background calendar-link revision for %s",
            user_id,
            exc_info=True,
        )


def _sync_schedule_to_calendar(
    user_id,
    schedule_id,
    schedule_payload,
    db_path,
    publish_background_revision=False,
):
    """Create or update the corresponding Google Calendar event."""
    auth_failure = _calendar_auth_failure_payload(user_id)
    if auth_failure:
        logger.warning("Skipping Google Calendar sync for schedule %s: %s", schedule_id, auth_failure.get('error'))
        return None

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
                attendees=attendees,
                location=schedule_payload.get('location', '') or ''
            )
            if success:
                return calendar_event_id
            logger.warning(
                "Calendar update failed for schedule %s with existing event %s; keeping local edit without recreating",
                schedule_id,
                calendar_event_id,
            )
            return None

        new_event_id = calendar_service.create_event(
            title=schedule_payload.get('title'),
            description=schedule_payload.get('description', ''),
            start_time=schedule_payload.get('start_time'),
            end_time=schedule_payload.get('end_time'),
            attendees=attendees,
            location=schedule_payload.get('location', '') or ''
        )
        if new_event_id:
            attached = Schedule.attach_calendar_event_id(
                schedule_id,
                new_event_id,
                db_path=db_path,
            )
            if attached:
                _clear_schedule_cache(db_path)
                if publish_background_revision:
                    _publish_background_calendar_link(user_id, db_path)
                logger.info(f"Schedule {schedule_id} synced to Google Calendar: {new_event_id}")
                return new_event_id

            # Another worker may have linked this schedule while the Google
            # request was in flight. Never report the losing event ID as the
            # one stored locally.
            current = Schedule.get_by_id(schedule_id, db_path=db_path)
            current_event_id = (current or {}).get('calendar_event_id')
            logger.info(
                "Schedule %s Google link was already resolved to %s",
                schedule_id,
                current_event_id or 'no local schedule',
            )
            return current_event_id
        logger.warning(
            "Failed to sync schedule %s to Google Calendar: %s",
            schedule_id,
            _calendar_sync_error_payload(calendar_service),
        )
    except Exception as e:
        logger.warning(f"Failed to sync schedule {schedule_id} to Google Calendar: {e}")

    return None


def _sync_schedule_to_calendar_async(user_id, schedule_id, db_path):
    if _calendar_auth_failure_payload(user_id):
        return False

    def _bg():
        try:
            schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
            if schedule:
                _sync_schedule_to_calendar(
                    user_id,
                    schedule_id,
                    schedule,
                    db_path,
                    publish_background_revision=True,
                )
        except Exception:
            logger.debug("Background calendar sync failed for schedule %s", schedule_id, exc_info=True)

    threading.Thread(target=_bg, daemon=True).start()
    return True


def _push_unsynced_local_schedules_to_calendar(user_id, db_path, start_time, end_time, google_events=None):
    """Retry FlowMate-created future schedules that do not yet have a Google ID."""
    auth_failure = _calendar_auth_failure_payload(user_id)
    if auth_failure:
        return {
            'pushed_count': 0,
            'push_failed_count': 0,
            'push_skipped_count': 0,
            'calendar_sync_error': auth_failure,
        }

    live_fingerprints = {
        _event_fingerprint(event.get('title'), event.get('start'))
        for event in (google_events or [])
        if event.get('title') and event.get('start')
    }
    pushed_count = 0
    failed_count = 0
    skipped_count = 0

    for schedule in Schedule.get_between(start_time, end_time, limit=1000, db_path=db_path):
        if schedule.get('calendar_event_id'):
            continue
        if _recently_updated(schedule, seconds=4):
            skipped_count += 1
            continue
        if str(schedule.get('status') or '').lower() in ('cancelled', 'dismissed'):
            skipped_count += 1
            continue
        fingerprint = _schedule_fingerprint(schedule)
        if fingerprint in live_fingerprints:
            skipped_count += 1
            continue

        event_id = _sync_schedule_to_calendar(user_id, schedule.get('id'), schedule, db_path)
        if event_id:
            live_fingerprints.add(fingerprint)
            pushed_count += 1
        else:
            failed_count += 1

    return {
        'pushed_count': pushed_count,
        'push_failed_count': failed_count,
        'push_skipped_count': skipped_count,
    }


def _delete_calendar_event_async(user_id, calendar_event_id, db_path):
    if not calendar_event_id or _calendar_auth_failure_payload(user_id):
        return False

    def _bg():
        try:
            calendar_service = _load_calendar_service(user_id)
            if calendar_service:
                calendar_service.delete_event(event_id=calendar_event_id)
            CalendarEvent.delete_google_event(user_id, calendar_event_id, db_path=db_path)
            _clear_schedule_cache(db_path)
        except Exception:
            logger.debug("Background calendar event delete failed for %s", calendar_event_id, exc_info=True)

    threading.Thread(target=_bg, daemon=True).start()
    return True


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


def _prune_stale_duplicate_after_move(user_id, db_path, schedule_id, previous_schedule, updated_schedule):
    previous_fingerprint = _schedule_fingerprint(previous_schedule or {})
    updated_fingerprint = _schedule_fingerprint(updated_schedule or {})
    if not previous_fingerprint or previous_fingerprint == updated_fingerprint:
        return 0

    previous_google_id = (previous_schedule or {}).get('calendar_event_id') or ''
    current_google_id = (updated_schedule or {}).get('calendar_event_id') or previous_google_id
    if not current_google_id:
        return 0

    deleted = 0
    calendar_service = None
    for candidate in Schedule.get_all(limit=1000, db_path=db_path):
        candidate_id = candidate.get('id')
        candidate_google_id = candidate.get('calendar_event_id') or ''
        if str(candidate_id) == str(schedule_id):
            continue
        if not candidate_google_id or candidate_google_id == current_google_id:
            continue
        if _schedule_fingerprint(candidate) != previous_fingerprint:
            continue

        if Schedule.delete(candidate_id, db_path=db_path):
            deleted += 1
            CalendarEvent.delete_google_event(user_id, candidate_google_id, db_path=db_path)
            try:
                calendar_service = calendar_service or _load_calendar_service(user_id)
                if calendar_service:
                    calendar_service.delete_event(candidate_google_id)
            except Exception:
                logger.debug(
                    "Could not delete stale duplicate Google event %s after schedule move",
                    candidate_google_id,
                    exc_info=True,
                )

    if deleted:
        _clear_schedule_cache(db_path)
        logger.info("Pruned %s stale duplicate schedules after moving schedule %s", deleted, schedule_id)
    return deleted


def _prune_stale_duplicate_after_move_async(user_id, db_path, schedule_id, previous_schedule, updated_schedule):
    def _bg():
        try:
            _prune_stale_duplicate_after_move(user_id, db_path, schedule_id, previous_schedule, updated_schedule)
        except Exception:
            logger.debug("Background duplicate cleanup failed for schedule %s", schedule_id, exc_info=True)

    threading.Thread(target=_bg, daemon=True).start()


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
            'calendar_sync_error': {
                'error': 'google_reauthentication_required',
                'message': 'Không thể khởi tạo Google Calendar. Vui lòng kết nối lại tài khoản Google.',
                'google_status': None,
                'google_reason': None,
                'google_error': None,
            },
        }

    time_min = start_time.replace(tzinfo=LOCAL_TZ).isoformat()
    time_max = end_time.replace(tzinfo=LOCAL_TZ).isoformat()
    gcal_events = calendar_service.get_events(
        max_results=max_results,
        time_min=time_min,
        time_max=time_max,
        raise_errors=True,
    )
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

    push_result = _push_unsynced_local_schedules_to_calendar(
        user_id,
        db_path,
        start_time,
        end_time,
        google_events=gcal_events,
    )
    pushed_count = push_result.get('pushed_count', 0)
    push_failed_count = push_result.get('push_failed_count', 0)
    push_skipped_count = push_result.get('push_skipped_count', 0)
    calendar_sync_error = push_result.get('calendar_sync_error')

    pruned_count = _prune_expired_google_backed_schedules(db_path)
    duplicate_deleted_count = _prune_local_duplicates_for_google_events(db_path)
    changed_count = created_count + updated_count + deleted_count + pushed_count + pruned_count + duplicate_deleted_count
    if changed_count:
        _clear_schedule_cache(db_path)
    return {
        'created_count': created_count,
        'updated_count': updated_count,
        'deleted_count': deleted_count + pruned_count + duplicate_deleted_count,
        'unchanged_count': unchanged_count,
        'pushed_count': pushed_count,
        'push_failed_count': push_failed_count,
        'push_skipped_count': push_skipped_count,
        'calendar_sync_error': calendar_sync_error,
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
    """Scan Google Calendar into the local schedule summary on demand.

    Reading events from Google only needs a valid token -- it does not need
    the calendar.events *write* scope. Gating the whole sync on write access
    meant any account whose token was missing that scope (e.g. partial OAuth
    consent) silently got zero events pulled in, even though the read call
    would have worked fine. Only require the token to exist here; a missing
    write scope still lets events flow in, and just downgrades the "push
    locally-created schedules to Google" step to a soft warning (handled
    inside _sync_google_events_range / _push_unsynced_local_schedules_to_calendar).
    """
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)

    token_status = _google_calendar_token_status(user_id)
    if not token_status.get('has_token') or not token_status.get('valid'):
        return jsonify({
            'success': False,
            'error': token_status.get('error') or 'not_authenticated',
            'message': 'Phiên Google chưa sẵn sàng. Vui lòng kết nối lại Gmail và Calendar.',
            'calendar_token_status': token_status,
            'needs_reauth': bool(token_status.get('has_token')),
        }), 401

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
        if not token_status.get('has_calendar_write_scope') and not sync_result.get('calendar_sync_error'):
            sync_result['calendar_sync_error'] = {
                'error': 'calendar_permission_required',
                'message': (
                    'Đã đọc được sự kiện từ Google Calendar, nhưng token hiện thiếu quyền ghi '
                    'nên FlowMate chưa thể đẩy lịch tạo trong app lên Google. Hãy đăng xuất/kết nối '
                    'lại Gmail & Google Calendar để cấp đủ quyền.'
                ),
                'google_status': None,
                'google_reason': None,
                'google_error': None,
            }
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
        google_status = getattr(getattr(e, 'resp', None), 'status', None)
        if google_status in (401, 403):
            return jsonify({
                'error': 'google_reauthentication_required',
                'message': 'Phiên Google đã hết hạn hoặc thiếu quyền Calendar. Vui lòng kết nối lại.',
                'needs_reauth': True,
                'google_status': google_status,
            }), 401
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
        'calendar_connected': _has_calendar_token(user_id),
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
