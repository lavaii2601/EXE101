import logging
import os
import re
import threading
from datetime import date, datetime, time, timedelta
from time import monotonic

from models.cache import Cache
from models.schedule import LOCAL_TZ, Schedule
from services.ai_service import AIService
from services.gmail_service import get_cached_gmail_service
from utils.user_context import get_user_db_path, get_user_token_file, sanitize_user_id

logger = logging.getLogger(__name__)

OVERVIEW_CACHE_TTL_SECONDS = 90 * 24 * 60 * 60
OVERVIEW_REVALIDATE_INTERVAL_SECONDS = 60
_refresh_lock = threading.Lock()
_refreshing = set()
_revalidate_lock = threading.Lock()
_revalidating = set()
_last_revalidated = {}
_ai_service = AIService()

# Keep in sync with the deadline heuristic in web/frontend/js/app.js (getOverviewPriority).
_DEADLINE_PATTERN = re.compile(r'(deadline|h[aạ]n|n[ộo]p|due|submit|b[àa]n giao)', re.IGNORECASE)


def parse_overview_date(value=None):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    raw = str(value or '').strip()
    if not raw:
        return datetime.now(LOCAL_TZ).date()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return datetime.now(LOCAL_TZ).date()


def format_report_date(day):
    return f'{day.day:02d}/{day.month:02d}/{day.year}'


def overview_cache_key(user_id, day):
    return f'overview:daily:{sanitize_user_id(user_id)}:{day.isoformat()}'


def overview_refresh_lock_key(user_id, day):
    return f'{sanitize_user_id(user_id)}:{day.isoformat()}'


def build_email_signature(message_ids):
    """Order-independent fingerprint of a day's Gmail message IDs.

    Lets us tell whether new mail arrived since the cached summary was
    generated without re-running the (expensive) AI summarization.
    """
    ids = sorted(str(mid) for mid in (message_ids or []) if mid)
    return '|'.join(ids)


def get_day_schedules(user_id, day, limit=500):
    db_path = get_user_db_path(user_id)
    start = datetime.combine(day, time.min, tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    return Schedule.get_between(start, end, limit=limit, db_path=db_path)


def build_cached_overview(user_id, day):
    db_path = get_user_db_path(user_id)
    cached = Cache.get(overview_cache_key(user_id, day), db_path=db_path)
    if isinstance(cached, dict):
        return cached
    return None


def build_overview_payload(user_id, day, rows=None, generated=False):
    schedules = get_day_schedules(user_id, day)
    rows = rows if isinstance(rows, list) else []
    return {
        'success': True,
        'date': day.isoformat(),
        'report_date': format_report_date(day),
        'schedules': schedules,
        'emails': rows,
        'email_rows': rows,
        'generated': bool(generated),
        'generated_at': datetime.now(LOCAL_TZ).isoformat(),
    }


def store_overview_payload(user_id, day, payload):
    db_path = get_user_db_path(user_id)
    Cache.set(
        overview_cache_key(user_id, day),
        payload,
        ttl=OVERVIEW_CACHE_TTL_SECONDS,
        db_path=db_path,
    )


def refresh_daily_overview(user_id, day=None, max_results=50, force=False):
    user_id = sanitize_user_id(user_id)
    day = parse_overview_date(day)
    db_path = get_user_db_path(user_id)
    cached = None if force else build_cached_overview(user_id, day)
    if cached:
        return cached

    rows = []
    email_signature = None
    token_file = get_user_token_file(user_id)
    if os.path.exists(token_file):
        try:
            service = get_cached_gmail_service(token_file)
            emails = service.get_emails_by_date(format_report_date(day), max_results=max_results)
            email_signature = build_email_signature(e.get('id') for e in emails)
            if emails:
                rows = _ai_service.summarize_email_report(
                    emails,
                    report_date=format_report_date(day),
                    user_id=user_id,
                )
        except Exception:
            logger.warning("Could not refresh overview email summary for %s", user_id, exc_info=True)

    payload = build_overview_payload(user_id, day, rows=rows, generated=True)
    payload['email_signature'] = email_signature
    store_overview_payload(user_id, day, payload)
    return payload


def refresh_daily_overview_async(user_id, day=None, max_results=50, force=False):
    user_id = sanitize_user_id(user_id)
    day = parse_overview_date(day)
    key = overview_refresh_lock_key(user_id, day)
    with _refresh_lock:
        if key in _refreshing:
            return False
        _refreshing.add(key)

    def _worker():
        try:
            refresh_daily_overview(user_id, day, max_results=max_results, force=force)
        finally:
            with _refresh_lock:
                _refreshing.discard(key)

    threading.Thread(target=_worker, daemon=True).start()
    return True


def is_daily_overview_refreshing(user_id, day=None):
    key = overview_refresh_lock_key(sanitize_user_id(user_id), parse_overview_date(day))
    with _refresh_lock:
        return key in _refreshing


def revalidate_daily_overview_async(user_id, day=None, max_results=50):
    """Check the Gmail fingerprint in the background without delaying reads.

    Revalidation is throttled per user/day. It only starts an AI refresh when
    the set of Gmail message IDs changed, so opening or polling Overview does
    not repeatedly consume AI resources.
    """
    user_id = sanitize_user_id(user_id)
    day = parse_overview_date(day)
    if not build_cached_overview(user_id, day):
        return False

    key = overview_refresh_lock_key(user_id, day)
    now = monotonic()
    with _revalidate_lock:
        if key in _revalidating:
            return False
        if now - _last_revalidated.get(key, 0.0) < OVERVIEW_REVALIDATE_INTERVAL_SECONDS:
            return False
        _revalidating.add(key)
        _last_revalidated[key] = now

    def _worker():
        try:
            check_and_refresh_if_new(user_id, day=day, max_results=max_results)
        finally:
            with _revalidate_lock:
                _revalidating.discard(key)

    threading.Thread(target=_worker, daemon=True).start()
    return True


def get_or_start_daily_overview(user_id, day=None, max_results=50):
    user_id = sanitize_user_id(user_id)
    day = parse_overview_date(day)
    cached = build_cached_overview(user_id, day)
    if cached:
        generating = is_daily_overview_refreshing(user_id, day)
        checking = False if generating else revalidate_daily_overview_async(
            user_id,
            day,
            max_results=max_results,
        )
        # Keep schedules fresh even when the email summary is cached.
        return {
            **cached,
            'schedules': get_day_schedules(user_id, day),
            'cache_hit': True,
            'refreshing': generating or checking,
            'refresh_state': 'generating' if generating else ('checking' if checking else 'ready'),
        }

    started = refresh_daily_overview_async(user_id, day, max_results=max_results)
    return {
        **build_overview_payload(user_id, day, rows=[], generated=False),
        'cache_hit': False,
        'refreshing': started,
        'refresh_state': 'generating' if started else 'ready',
    }


def has_new_emails(user_id, day, max_results=50):
    """Cheap check for whether mail arrived since the cached summary's signature.

    Returns False (nothing to do) if the user has no overview cached yet for
    `day` -- the first summary is still generated lazily when they open the
    Overview tab, this only keeps an existing one fresh.
    """
    user_id = sanitize_user_id(user_id)
    cached = build_cached_overview(user_id, day)
    if not cached:
        return False

    token_file = get_user_token_file(user_id)
    if not os.path.exists(token_file):
        return False

    try:
        service = get_cached_gmail_service(token_file)
        message_ids = service.list_message_ids_by_date(format_report_date(day), max_results=max_results)
    except Exception:
        logger.warning("Could not check for new mail for %s", user_id, exc_info=True)
        return False

    return build_email_signature(message_ids) != cached.get('email_signature')


def check_and_refresh_if_new(user_id, day=None, max_results=50):
    """Background-safe top-up: only pays for AI re-summarization when new mail showed up."""
    user_id = sanitize_user_id(user_id)
    day = parse_overview_date(day)
    if not has_new_emails(user_id, day, max_results=max_results):
        return False
    return refresh_daily_overview_async(user_id, day, max_results=max_results, force=True)


def _is_deadline(schedule):
    text = f"{schedule.get('title') or ''} {schedule.get('description') or ''}"
    return bool(_DEADLINE_PATTERN.search(text))


DEADLINE_LOOKAHEAD_DAYS = 30


def get_upcoming_deadlines(user_id, today=None, limit=None):
    """Deadline-flagged schedules (see _is_deadline) from now through
    DEADLINE_LOOKAHEAD_DAYS ahead, nearest first. Pure data lookup, no
    entitlement awareness -- callers (routes/overview.py) decide how many
    of these a free vs premium Student sees via `limit`."""
    user_id = sanitize_user_id(user_id)
    today = today or datetime.now(LOCAL_TZ).date()
    now = datetime.now(LOCAL_TZ)
    db_path = get_user_db_path(user_id)
    start = datetime.combine(today, time.min, tzinfo=LOCAL_TZ)
    end = start + timedelta(days=DEADLINE_LOOKAHEAD_DAYS)
    schedules = Schedule.get_between(start, end, limit=500, db_path=db_path)

    deadlines = []
    for schedule in schedules:
        if not _is_deadline(schedule):
            continue
        start_time_raw = schedule.get('start_time')
        if not start_time_raw:
            continue
        try:
            event_time = datetime.fromisoformat(str(start_time_raw))
        except ValueError:
            continue
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=LOCAL_TZ)
        if event_time < now:
            continue
        deadlines.append({
            'id': schedule.get('id'),
            'title': schedule.get('title'),
            'start_time': start_time_raw,
            'days_until': (event_time.date() - today).days,
        })

    deadlines.sort(key=lambda item: item['start_time'])
    return deadlines[:limit] if limit else deadlines


def build_weekly_analytics(user_id, end_day=None, days=7):
    """Aggregate task/email activity for the `days` ending on `end_day`.

    Task stats always come straight from the schedules table (accurate for
    any day). Email stats are best-effort: they only cover days whose daily
    overview was already generated/cached, since emails aren't stored
    long-term -- fetching every day live from Gmail would be too slow/costly
    for a dashboard read. `has_email_data` on each day tells the caller
    whether that day's email numbers are real or simply "not visited yet".
    """
    user_id = sanitize_user_id(user_id)
    end_day = parse_overview_date(end_day)
    days = min(max(int(days or 7), 1), 30)
    start_day = end_day - timedelta(days=days - 1)

    daily = []
    tasks_total = 0
    tasks_completed = 0
    deadlines_total = 0
    emails_total = 0
    meeting_emails_total = 0
    days_with_email_data = 0
    busiest_date = None
    busiest_count = -1

    for offset in range(days):
        day = start_day + timedelta(days=offset)
        schedules = get_day_schedules(user_id, day)
        day_tasks_total = len(schedules)
        day_tasks_completed = sum(1 for s in schedules if s.get('status') == 'completed')
        day_deadlines = sum(1 for s in schedules if _is_deadline(s))

        cached = build_cached_overview(user_id, day)
        has_email_data = cached is not None
        rows = (cached.get('email_rows') or cached.get('emails') or []) if cached else []
        day_emails_total = len(rows)
        day_meeting_emails = sum(1 for r in rows if isinstance(r, dict) and r.get('is_meeting'))

        tasks_total += day_tasks_total
        tasks_completed += day_tasks_completed
        deadlines_total += day_deadlines
        emails_total += day_emails_total
        meeting_emails_total += day_meeting_emails
        if has_email_data:
            days_with_email_data += 1

        day_activity = day_tasks_total + day_emails_total
        if day_activity > busiest_count:
            busiest_count = day_activity
            busiest_date = day.isoformat()

        daily.append({
            'date': day.isoformat(),
            'weekday': day.weekday(),  # Monday=0 .. Sunday=6
            'tasks_total': day_tasks_total,
            'tasks_completed': day_tasks_completed,
            'deadlines': day_deadlines,
            'emails_total': day_emails_total,
            'meeting_emails': day_meeting_emails,
            'has_email_data': has_email_data,
        })

    completion_rate = round((tasks_completed / tasks_total * 100), 1) if tasks_total else 0.0

    return {
        'success': True,
        'range': {'start': start_day.isoformat(), 'end': end_day.isoformat(), 'days': days},
        'daily': daily,
        'totals': {
            'tasks_total': tasks_total,
            'tasks_completed': tasks_completed,
            'completion_rate': completion_rate,
            'deadlines_total': deadlines_total,
            'emails_total': emails_total,
            'meeting_emails_total': meeting_emails_total,
            'days_with_email_data': days_with_email_data,
            'busiest_date': busiest_date if busiest_count > 0 else None,
            'busiest_count': max(busiest_count, 0),
        },
    }
