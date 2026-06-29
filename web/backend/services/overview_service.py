import logging
import os
import threading
from datetime import date, datetime, time, timedelta

from models.cache import Cache
from models.schedule import LOCAL_TZ, Schedule
from services.ai_service import AIService
from services.gmail_service import get_cached_gmail_service
from utils.user_context import get_user_db_path, get_user_token_file, sanitize_user_id

logger = logging.getLogger(__name__)

OVERVIEW_CACHE_TTL_SECONDS = 36 * 60 * 60
_refresh_lock = threading.Lock()
_refreshing = set()
_ai_service = AIService()


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


def get_or_start_daily_overview(user_id, day=None, max_results=50):
    user_id = sanitize_user_id(user_id)
    day = parse_overview_date(day)
    cached = build_cached_overview(user_id, day)
    if cached:
        # Keep schedules fresh even when the email summary is cached.
        return {
            **cached,
            'schedules': get_day_schedules(user_id, day),
            'cache_hit': True,
            'refreshing': False,
        }

    started = refresh_daily_overview_async(user_id, day, max_results=max_results)
    return {
        **build_overview_payload(user_id, day, rows=[], generated=False),
        'cache_hit': False,
        'refreshing': started,
    }


def invalidate_daily_overview(user_id):
    db_path = get_user_db_path(user_id)
    Cache.clear_pattern(f'overview:daily:{sanitize_user_id(user_id)}:%', db_path=db_path)


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
