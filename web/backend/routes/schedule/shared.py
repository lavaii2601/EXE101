"""Schedule package shared state: the Blueprint object, the draft-parse
orchestrator singleton, generic schedule-cache helpers, and the small
datetime/fingerprint utilities every other schedule submodule depends on."""
import logging
from datetime import datetime, timedelta

from flask import Blueprint

from services.intent_orchestrator import IntentOrchestrator
from models.cache import Cache
from models.schedule import LOCAL_TZ

# Configure module logger
logger = logging.getLogger('routes.schedule')

schedule_bp = Blueprint('schedule', __name__, url_prefix='/api/schedule')
# Stateless (regex-based) -- shared here instead of importing the singleton
# from services.chat_agents, which would create a circular import (that
# module already imports several helpers back from this one).
_draft_orchestrator = IntentOrchestrator()
_SCHEDULE_CACHE_TTL_SECONDS = 15


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
