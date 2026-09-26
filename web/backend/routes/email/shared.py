"""Shared state for the email routes package: the `email_bp` Blueprint every
submodule registers its routes against, cache-key builders, TTL constants,
and the small text/date utilities used by both Smart Inbox classification
(smart_inbox.py) and meeting-suggestion extraction (meeting.py).

Split out of the former monolithic routes/email.py (2368 lines) -- see
routes/email/__init__.py for the package-level overview.
"""
import logging
import re
import unicodedata
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from flask import Blueprint

from models.cache import Cache
from models import postgres_db as pg
from services.ai_service import AIService
from utils.user_context import get_user_db_path

# Configure module logger
logger = logging.getLogger(__name__)

# Email-related endpoints including OAuth login and Gmail access
email_bp = Blueprint('email', __name__, url_prefix='/api/email')

# Initialize services
ai_service = AIService()

# Local-development email list cache. PostgreSQL deployments can run several
# workers/replicas, so a process-local list cache would serve stale data after
# another worker (or the APK) mutates the mailbox.
_email_cache = {}
EMAIL_SCAN_DEFAULT = 25
EMAIL_SCAN_MAX = 150
EMAIL_LIST_CACHE_TTL = 1800
EMAIL_BODY_CACHE_TTL = 86400
EMAIL_SUMMARY_CACHE_TTL = 86400


def _get_cache_key(user_id, filter_type, include_read=False, scan_limit=EMAIL_SCAN_DEFAULT, search=''):
    """Generate one shared inbox cache key for every client-side filter.

    Older versions included ``filter_type`` in this key and stored only the
    matching rows. Switching filters therefore caused another Gmail scan,
    which was both slow and capable of exhausting Railway's request window.
    Filtering now happens after the common metadata cache is loaded.
    ``filter_type`` stays in the signature for backwards compatibility.

    ``search`` is deliberately its own cache namespace, not folded into the
    plain inbox one above: a search re-queries Gmail directly (see
    get_unread_emails), so its result set has entirely different scope/
    semantics than "the most recent N unread/inbox messages" and must never
    be served from, or overwrite, that cache entry.
    """
    read_scope = 'with_read' if include_read else 'unread'
    if search:
        search_key = _normalize_search_text(search)[:200]
        return f"{user_id}:emails:list:v3:search:{read_scope}:{scan_limit}:{search_key}"
    return f"{user_id}:emails:list:v3:inbox:{read_scope}:{scan_limit}"


def _email_body_cache_key(user_id, email_id):
    return f"{user_id}:email:body:{email_id}"


def _email_summary_cache_key(user_id, email_id):
    return f"{user_id}:email:summary:{email_id}"


def _gmail_query_for_email_list(search):
    """Gmail API `q=` for the inbox-list scan.

    A `search` term routes through Gmail's own server-side search -- which
    spans the whole mailbox, not just this request's scan_limit-sized
    recent-messages window -- instead of only being applied as a local
    re-filter afterward (the previous behavior: a keyword only "worked" when
    the matching email happened to already be among the most recent ~25
    fetched messages). Always widens to the whole inbox (not just unread)
    while searching -- a user looking for a specific email wants it found
    regardless of read state.
    """
    if search:
        return f'in:inbox {search}'
    return 'is:unread'


def _compact_preview(text, max_chars=220):
    value = re.sub(r'\s+', ' ', (text or '').strip())
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + '...'


def _normalize_search_text(value):
    text = unicodedata.normalize('NFKD', str(value or '').lower())
    return ''.join(char for char in text if not unicodedata.combining(char))


def _parse_email_base_date(email):
    raw_date = (email or {}).get('date') or (email or {}).get('email_date') or ''
    try:
        parsed = parsedate_to_datetime(str(raw_date))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed.date()
    except (TypeError, ValueError, IndexError, OverflowError):
        return datetime.now().date()


def _extract_weekday_date(normalized_text, base_date):
    if re.search(r'\b(?:ngay kia|ngay mot|day after tomorrow)\b', normalized_text):
        return base_date + timedelta(days=2)
    if re.search(r'\b(?:ngay mai|tomorrow)\b', normalized_text):
        return base_date + timedelta(days=1)
    if re.search(r'\b(?:hom nay|today)\b', normalized_text):
        return base_date
    weekday_patterns = [
        (0, r'\bthu\s*(?:2|hai)\b'),
        (1, r'\bthu\s*(?:3|ba)\b'),
        (2, r'\bthu\s*(?:4|tu)\b'),
        (3, r'\bthu\s*(?:5|nam)\b'),
        (4, r'\bthu\s*(?:6|sau)\b'),
        (5, r'\bthu\s*(?:7|bay)\b'),
        (6, r'\b(?:chu\s*nhat|cn)\b'),
    ]
    next_week = bool(re.search(r'\b(?:tuan sau|tuan toi|tuan ke tiep|next week)\b', normalized_text))
    for weekday, pattern in weekday_patterns:
        if re.search(pattern, normalized_text):
            days_ahead = (weekday - base_date.weekday()) % 7
            if next_week:
                days_ahead += 7
            return base_date + timedelta(days=days_ahead)
    return None


def _extract_times(normalized_text):
    times = []
    seen_spans = []

    def add_time(hour, minute, span=None, meridiem=''):
        try:
            hour = int(hour)
            minute = int(minute or 0)
        except (TypeError, ValueError):
            return
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return
        if meridiem in {'chieu', 'toi'} and 1 <= hour <= 11:
            hour += 12
        elif meridiem == 'sang' and hour == 12:
            hour = 0
        if span:
            seen_spans.append(span)
        times.append((hour, minute))

    for match in re.finditer(r'(?<!\d)((?:[01]?\d|2[0-3]))(?::(\d{2}))?\s*(am|pm)(?![a-z])', normalized_text):
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3)
        if meridiem == 'pm' and 1 <= hour <= 11:
            hour += 12
        elif meridiem == 'am' and hour == 12:
            hour = 0
        add_time(hour, minute, match.span())

    for match in re.finditer(r'(?<!\d)((?:[01]?\d|2[0-3]))[:h](\d{2})(?!\d)', normalized_text):
        if any(match.start() >= start and match.end() <= end for start, end in seen_spans):
            continue
        add_time(match.group(1), match.group(2), match.span())

    for match in re.finditer(
        r'(?<!\d)((?:[01]?\d|2[0-3]))\s*(?:gio|g|h)\s*(?:(\d{1,2})\s*(?:phut|p)?)?\s*(sang|chieu|toi)?(?!\d)',
        normalized_text
    ):
        if any(match.start() >= start and match.end() <= end for start, end in seen_spans):
            continue
        add_time(match.group(1), match.group(2) or 0, match.span(), match.group(3) or '')

    return times


def _are_emails_cached(cache_key):
    """Check if cache is still valid (10 minute TTL for better performance)"""
    if pg.enabled():
        return False
    if cache_key not in _email_cache:
        return False
    cached_time, _, _ = _email_cache[cache_key]
    return datetime.now() - cached_time < timedelta(minutes=10)

def _get_cached_emails(cache_key):
    """Get cached emails if valid"""
    if _are_emails_cached(cache_key):
        _, cached_emails, cached_total = _email_cache[cache_key]
        return cached_emails, cached_total
    return None, None

def _cache_emails(cache_key, emails, total):
    """Cache emails with timestamp"""
    if pg.enabled():
        return
    _email_cache[cache_key] = (datetime.now(), emails, total)

def _clear_all_cache(user_id):
    """Clear all cached emails for a user"""
    keys_to_delete = [k for k in _email_cache.keys() if k.startswith(f"{user_id}:")]
    for key in keys_to_delete:
        del _email_cache[key]
    logger.info(f"Cleared {len(keys_to_delete)} cache entries for user {user_id}")


def _clear_email_list_cache(user_id):
    """Invalidate list caches while preserving full bodies and AI summaries."""
    _clear_all_cache(user_id)
    try:
        db_path = get_user_db_path(user_id)
        Cache.clear_pattern(f"{user_id}:emails:list:%", db_path=db_path)
    except Exception as e:
        logger.warning(f"Failed to clear DB email list cache for {user_id}: {e}")
