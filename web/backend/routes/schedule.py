import os
import sys
import logging
import re
import threading
import time
import uuid
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta, time as dt_time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.schedule_service import ScheduleService
from services.calendar_service import CalendarService
from models.cache import Cache
from models.calendar_event import CalendarEvent
from models.schedule import Schedule, LOCAL_TZ
from models.history import History
from models.sync_job import SyncJob
from services.intent_orchestrator import IntentOrchestrator
from utils.user_context import (
    get_current_user_id,
    get_user_db_path,
    get_user_token_file,
    inspect_google_credentials,
)
from utils.google_service_cache import get_cached_service

# Configure module logger
logger = logging.getLogger(__name__)

schedule_bp = Blueprint('schedule', __name__, url_prefix='/api/schedule')
# Stateless (regex-based) -- shared here instead of importing the singleton
# from services.chat_agents, which would create a circular import (that
# module already imports several helpers back from this one).
_draft_orchestrator = IntentOrchestrator()
_week_sync_lock = threading.Lock()
_week_sync_inflight = set()
_week_sync_recent = {}
_WEEK_SYNC_TTL_SECONDS = 90
_SCHEDULE_CACHE_TTL_SECONDS = 15
_FULL_SYNC_DAYS = int(os.getenv('SCHEDULE_FULL_SYNC_DAYS', '90'))
_LOCAL_EDIT_SYNC_GRACE_SECONDS = 180
_CHECKLIST_CACHE_TTL_SECONDS = 365 * 24 * 60 * 60
_GOOGLE_CALENDAR_WRITE_SCOPE = 'https://www.googleapis.com/auth/calendar.events'

_DATE_WORDS = {
    'today': 0,
    'hom nay': 0,
    'hôm nay': 0,
    'toi nay': 0,
    'tối nay': 0,
    'chieu nay': 0,
    'chiều nay': 0,
    'sang nay': 0,
    'sáng nay': 0,
    'tomorrow': 1,
    'ngay mai': 1,
    'ngày mai': 1,
    'mai': 1,
}

_WEEKDAY_WORDS = {
    'thu 2': 0, 'thứ 2': 0, 'thu hai': 0, 'thứ hai': 0, 'monday': 0,
    'thu 3': 1, 'thứ 3': 1, 'thu ba': 1, 'thứ ba': 1, 'tuesday': 1,
    'thu 4': 2, 'thứ 4': 2, 'thu tu': 2, 'thứ tư': 2, 'wednesday': 2,
    'thu 5': 3, 'thứ 5': 3, 'thu nam': 3, 'thứ năm': 3, 'thursday': 3,
    'thu 6': 4, 'thứ 6': 4, 'thu sau': 4, 'thứ sáu': 4, 'friday': 4,
    'thu 7': 5, 'thứ 7': 5, 'thu bay': 5, 'thứ bảy': 5, 'saturday': 5,
    'chu nhat': 6, 'chủ nhật': 6, 'cn': 6, 'sunday': 6,
}

_ACTIVITY_KEYWORDS = (
    'họp', 'hop', 'meeting', 'call', 'gặp', 'gap', 'cafe', 'cà phê',
    'gym', 'tập', 'tap', 'chạy', 'chay', 'học', 'hoc', 'đi ', 'di ',
    'khám', 'kham', 'ăn', 'an ', 'workout', 'appointment', 'lịch', 'lich'
)


def _schedule_cache_key(user_id, name, *parts):
    safe_parts = [str(part).replace('%', '').replace(':', '-') for part in parts if part is not None]
    return 'schedule:' + ':'.join([user_id, name, *safe_parts])


def _checklist_cache_key(user_id, date_value):
    safe_date = str(date_value or '').strip().replace('%', '').replace(':', '-')
    return f"overview:checklist:{user_id}:{safe_date}"


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


def _parse_quick_base_date(value):
    raw = str(value or '').strip()
    if raw:
        try:
            return datetime.strptime(raw[:10], '%Y-%m-%d').date()
        except ValueError:
            pass
    return datetime.now(LOCAL_TZ).date()


def _parse_explicit_date(text, base_date):
    normalized = str(text or '').lower()

    date_match = re.search(r'(?<!\d)(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?(?!\d)', normalized)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = date_match.group(3)
        year = int(year) if year else base_date.year
        if year < 100:
            year += 2000
        try:
            parsed = datetime(year, month, day).date()
            if not date_match.group(3) and parsed < base_date:
                parsed = parsed.replace(year=parsed.year + 1)
            return parsed
        except ValueError:
            pass

    for token, offset in _DATE_WORDS.items():
        if re.search(rf'(?<!\w){re.escape(token)}(?!\w)', normalized):
            return base_date + timedelta(days=offset)

    for token, weekday in _WEEKDAY_WORDS.items():
        if re.search(rf'(?<!\w){re.escape(token)}(?!\w)', normalized):
            delta = (weekday - base_date.weekday()) % 7
            if delta == 0:
                delta = 7
            return base_date + timedelta(days=delta)

    return None


def _infer_period(text):
    normalized = str(text or '').lower()
    if any(word in normalized for word in ('tối', 'toi', 'đêm', 'dem', 'pm')):
        return 'evening'
    if any(word in normalized for word in ('chiều', 'chieu')):
        return 'afternoon'
    if any(word in normalized for word in ('sáng', 'sang', 'am')):
        return 'morning'
    return ''


def _extract_quick_time(text):
    normalized = str(text or '').lower()
    period = _infer_period(normalized)
    patterns = [
        r'(?<!\d)(\d{1,2})\s*[:h]\s*(\d{1,2})?\s*(sáng|sang|chiều|chieu|tối|toi|đêm|dem|am|pm)?(?!\d)',
        r'(?<!\d)(\d{1,2})\s*giờ\s*(\d{1,2})?\s*(sáng|sang|chiều|chieu|tối|toi|đêm|dem|am|pm)?(?!\d)',
        # Bare English 12-hour format with no colon/"h"/"gio" separator
        # ("3pm", "10 am") -- the most common way English speakers write a time.
        r'(?<!\d)(\d{1,2})()\s*(am|pm)(?!\d)',
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        local_period = match.group(3) or period
        if hour > 23 or minute > 59:
            continue
        if local_period in ('pm', 'chiều', 'chieu', 'tối', 'toi', 'đêm', 'dem', 'evening', 'afternoon') and 1 <= hour < 12:
            hour += 12
        if local_period in ('am', 'sáng', 'sang', 'morning') and hour == 12:
            hour = 0
        return dt_time(hour=hour, minute=minute), True

    if period:
        defaults = {
            'morning': dt_time(hour=8),
            'afternoon': dt_time(hour=14),
            'evening': dt_time(hour=19),
        }
        return defaults.get(period), False
    return None, False


def _extract_duration_minutes_from_text(text):
    normalized = str(text or '').lower()
    match = re.search(r'(?:trong|khoảng|khoang)\s*(\d+(?:[,.]\d+)?)\s*(tiếng|gio|giờ|hour|hours)', normalized)
    if match:
        value = float(match.group(1).replace(',', '.'))
        return max(15, int(value * 60))
    match = re.search(r'(\d+)\s*(phút|phut|minute|minutes)', normalized)
    if match:
        return max(15, int(match.group(1)))
    match = re.search(r'(\d+(?:[,.]\d+)?)\s*(tiếng|hour|hours)', normalized)
    if match:
        value = float(match.group(1).replace(',', '.'))
        return max(15, int(value * 60))
    return 60


def _has_duration_signal(text):
    normalized = str(text or '').lower()
    return bool(re.search(r'\d+(?:[,.]\d+)?\s*(tiếng|gio|giờ|hour|hours|phút|phut|minute|minutes)', normalized))


def _clean_quick_title(text):
    title = str(text or '').strip()
    replacements = [
        r'\b(hôm nay|hom nay|ngày mai|ngay mai|mai|today|tomorrow|tối nay|toi nay|chiều nay|chieu nay|sáng nay|sang nay)\b',
        r'(?<!\d)\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?(?!\d)',
        r'(?<!\d)\d{1,2}\s*[:h]\s*\d{0,2}\s*(?:sáng|sang|chiều|chieu|tối|toi|đêm|dem|am|pm)?(?!\d)',
        r'(?<!\d)\d{1,2}\s*giờ\s*\d{0,2}\s*(?:sáng|sang|chiều|chieu|tối|toi|đêm|dem|am|pm)?(?!\d)',
        r'\b(?:trong|khoảng|khoang)\s*\d+(?:[,.]\d+)?\s*(?:tiếng|gio|giờ|hour|hours|phút|phut|minute|minutes)\b',
        r'(?<!\w)\d+(?:[,.]\d+)?\s*(?:tiếng|gio|giờ|hour|hours|phút|phut|minute|minutes)(?!\w)',
        r'\b(lúc|luc|vào|vao|at)\b',
    ]
    for pattern in replacements:
        title = re.sub(pattern, ' ', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title).strip(' -–—,.;:')
    return title or str(text or '').strip()


def _task_priority_for_due(base_date, due_date):
    if not due_date:
        return 40, 'Chưa có hạn rõ ràng, đặt ở nhóm có thể làm sau.'
    delta = (due_date - base_date).days
    if delta <= 0:
        return 95, 'Ưu tiên cao vì hạn là hôm nay hoặc đã đến hạn.'
    if delta == 1:
        return 82, 'Ưu tiên cao vì hạn là ngày mai.'
    if delta <= 3:
        return 68, 'Ưu tiên vừa vì hạn trong vài ngày tới.'
    return 52, 'Có hạn rõ ràng nhưng chưa quá gấp.'


def _custom_item_sort_key(item):
    completed = bool(item.get('completed'))
    pinned_rank = 0 if item.get('pinned') else 1
    due_value = item.get('due_at') or item.get('due_date') or '9999-12-31'
    priority = -int(item.get('priority_score') or 0)
    created = item.get('created_at') or ''
    return (completed, pinned_rank, due_value, priority, created)


def _sort_custom_items(items):
    return sorted(items or [], key=_custom_item_sort_key)


def _split_day_plan_entries(text):
    raw = str(text or '').strip()
    if not raw:
        return []

    # Only strip a colon that introduces a list ("các việc sau: A, B").
    # Never split on the first arbitrary colon: in "gym lúc 7:30 sáng" that
    # colon belongs to the clock and stripping it turns the item into
    # "30 sáng".
    list_intro = re.match(
        r'^.{0,100}?\b(?:gồm|gom|như|nhu|sau|các việc|cac viec|những việc|nhung viec|'
        r'các hoạt động|cac hoat dong|activities|tasks|checklist)\s*:\s*',
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if list_intro:
        raw = raw[list_intro.end():]
    # Remove an explicit planning command from the beginning so it is not
    # accidentally kept as part of the first activity title.
    raw = re.sub(
        r'^\s*(?:hãy\s+)?(?:xếp\s+lịch|sắp\s+xếp(?:\s+lịch)?|xep\s+lich|sap\s+xep(?:\s+lich)?|'
        r'plan\s+(?:my\s+)?day(?:\s+(?:with|for))?|organize|arrange)\s*',
        '',
        raw,
        flags=re.IGNORECASE,
    )
    # Drop a trailing instruction clause ("Hay sap xep giup minh...",
    # "Please organize this for me") that often follows the activity list
    # after a period in a chat-style message -- it isn't an activity, but
    # its own commas would otherwise get split into bogus entries and glue
    # onto the last real item's title.
    raw = re.sub(
        r'\.\s*(?:hãy|hay|giúp (?:tôi|mình)|giup (?:toi|minh)|dùm|giùm|'
        r'please|can you|could you|sắp xếp|sap xep|gợi ý|goi y|organize|arrange)\b.*$',
        '.',
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    raw = re.sub(r'\.{2,}', ',', raw)
    raw = re.sub(r'\b(và|va|and)\b', ',', raw, flags=re.IGNORECASE)
    raw = re.sub(
        r'\b(ngày mai|ngay mai|hôm nay|hom nay|today|tomorrow|tôi có|toi co|các hoạt động sau|cac hoat dong sau|hoạt động sau|activities)\b',
        ' ',
        raw,
        flags=re.IGNORECASE,
    )
    parts = re.split(r'[,;\n]+', raw)
    entries = []
    for part in parts:
        original = str(part or '').strip()
        title = _clean_quick_title(part)
        title = re.sub(r'^\s*(?:-|•|\d+[.)])\s*', '', title).strip()
        if len(title) >= 2:
            entries.append({'raw': original, 'title': title[:180]})
    return entries[:50]


def _split_day_plan_items(text):
    return [entry['title'] for entry in _split_day_plan_entries(text)]


def _looks_like_day_plan(text, items):
    normalized = str(text or '').lower()
    has_list_signal = any(token in normalized for token in (
        'các hoạt động', 'cac hoat dong', 'hoạt động sau', 'activities',
        'những việc', 'nhung viec', 'các việc', 'cac viec'
    ))
    has_planning_signal = any(token in normalized for token in (
        'xếp lịch', 'xep lich', 'sắp xếp', 'sap xep',
        'gợi ý lịch', 'goi y lich', 'plan my day', 'plan the day',
        'organize my day', 'arrange my day',
    ))
    has_separator = ',' in normalized or ';' in normalized or '\n' in normalized
    has_date_signal = any(
        re.search(rf'(?<!\w){re.escape(token)}(?!\w)', normalized)
        for token in (*_DATE_WORDS.keys(), *_WEEKDAY_WORDS.keys())
    )
    return len(items) >= 2 and (
        has_list_signal or has_planning_signal or (has_separator and has_date_signal)
    )


def _activity_profile(title):
    normalized = str(title or '').lower()
    if any(token in normalized for token in ('yoga', 'gym', 'workout', 'tập', 'tap', 'chạy', 'chay')):
        return dt_time(7, 0), 45, 'Hoạt động thể chất nhẹ, phù hợp để bắt đầu ngày.'
    if any(token in normalized for token in ('mèo', 'meo', 'cưng', 'cung', 'thú cưng', 'thu cung', 'pet')):
        return dt_time(8, 0), 20, 'Việc chăm sóc ngắn, nên đặt gần đầu ngày để không quên.'
    if any(token in normalized for token in ('dọn', 'don', 'nhà', 'nha', 'clean')):
        return dt_time(19, 30), 60, 'Việc nhà thường hợp lý vào buổi tối khi các việc chính đã xong.'
    if any(token in normalized for token in ('học', 'hoc', 'đọc', 'doc', 'viết', 'viet', 'báo cáo', 'bao cao', 'focus')):
        return dt_time(9, 0), 90, 'Việc cần tập trung nên đặt vào khung giờ tỉnh táo.'
    if any(token in normalized for token in ('mua', 'đi ', 'di ', 'khám', 'kham', 'cafe', 'cà phê')):
        return dt_time(15, 0), 60, 'Hoạt động di chuyển/gặp gỡ được đặt vào khung chiều để linh hoạt hơn.'
    return dt_time(10, 0), 45, 'FlowMate đặt vào khung trống gần nhất trong ngày.'


def _datetime_from_local_iso(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(LOCAL_TZ).replace(tzinfo=None)
    return parsed


def _busy_ranges_for_day(db_path, target_date):
    start = datetime.combine(target_date, dt_time.min)
    end = start + timedelta(days=1)
    ranges = []
    for schedule in Schedule.get_between(start, end, limit=500, db_path=db_path):
        start_dt = _datetime_from_local_iso(schedule.get('start_time'))
        end_dt = _datetime_from_local_iso(schedule.get('end_time')) or (
            start_dt + timedelta(minutes=60) if start_dt else None
        )
        if start_dt and end_dt:
            ranges.append((start_dt, end_dt))
    return ranges


def _slot_conflicts(start_dt, end_dt, busy_ranges, buffer_minutes=10):
    buffered_start = start_dt - timedelta(minutes=buffer_minutes)
    buffered_end = end_dt + timedelta(minutes=buffer_minutes)
    return any(buffered_start < busy_end and buffered_end > busy_start for busy_start, busy_end in busy_ranges)


def _find_available_slot(target_date, preferred_clock, duration_minutes, busy_ranges):
    day_start = datetime.combine(target_date, dt_time(6, 30))
    day_end = datetime.combine(target_date, dt_time(22, 30))
    preferred = datetime.combine(target_date, preferred_clock)
    candidates = [preferred]

    for offset in range(30, 16 * 60, 30):
        candidates.append(preferred + timedelta(minutes=offset))
        candidates.append(preferred - timedelta(minutes=offset))

    for candidate in candidates:
        start_dt = candidate
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        if start_dt < day_start or end_dt > day_end:
            continue
        if not _slot_conflicts(start_dt, end_dt, busy_ranges):
            busy_ranges.append((start_dt, end_dt))
            busy_ranges.sort(key=lambda item: item[0])
            return start_dt, end_dt

    fallback = max(day_start, preferred)
    while fallback + timedelta(minutes=duration_minutes) <= day_end:
        end_dt = fallback + timedelta(minutes=duration_minutes)
        if not _slot_conflicts(fallback, end_dt, busy_ranges):
            busy_ranges.append((fallback, end_dt))
            busy_ranges.sort(key=lambda item: item[0])
            return fallback, end_dt
        fallback += timedelta(minutes=30)

    end_dt = preferred + timedelta(minutes=duration_minutes)
    busy_ranges.append((preferred, end_dt))
    return preferred, end_dt


def _build_suggested_day_plan(user_id, db_path, text, selected_date):
    base_date = _parse_quick_base_date(selected_date)
    target_date = _parse_explicit_date(text, base_date) or base_date
    entries = _split_day_plan_entries(text)
    titles = [entry['title'] for entry in entries]
    if not _looks_like_day_plan(text, titles):
        return None

    busy_ranges = _busy_ranges_for_day(db_path, target_date)
    items = []
    for entry in entries:
        title = entry['title']
        raw_item = entry.get('raw') or title
        preferred_clock, duration_minutes, reason = _activity_profile(title)
        item_clock, explicit_time = _extract_quick_time(raw_item)
        item_duration = _extract_duration_minutes_from_text(raw_item)
        if explicit_time and item_clock:
            preferred_clock = item_clock
            reason = 'Giữ giờ người dùng đã nhập cho hoạt động này.'
        if _has_duration_signal(raw_item):
            duration_minutes = item_duration
        start_dt, end_dt = _find_available_slot(target_date, preferred_clock, duration_minutes, busy_ranges)
        items.append({
            'title': title,
            'description': f'Tạo từ kế hoạch ngày: {text.strip()}',
            'start_time': start_dt.isoformat(),
            'end_time': end_dt.isoformat(),
            'duration_minutes': duration_minutes,
            'reason': reason,
        })

    return {
        'kind': 'suggested_plan',
        'date': target_date.isoformat(),
        'items': items,
        'message': 'FlowMate đã gợi ý khung giờ. Xác nhận để tạo lịch.',
    }


def _classify_quick_plan(text, selected_date):
    base_date = _parse_quick_base_date(selected_date)
    due_date = _parse_explicit_date(text, base_date)
    start_clock, explicit_time = _extract_quick_time(text)
    normalized = str(text or '').lower()
    has_activity_keyword = any(keyword in normalized for keyword in _ACTIVITY_KEYWORDS)
    title = _clean_quick_title(text)

    if start_clock and (explicit_time or has_activity_keyword):
        activity_date = due_date or base_date
        start_dt = datetime.combine(activity_date, start_clock)
        duration_minutes = _extract_duration_minutes_from_text(text)
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        return {
            'kind': 'activity',
            'title': title[:180],
            'description': f'Tạo nhanh từ Overview: {text.strip()}',
            'start_time': start_dt.isoformat(),
            'end_time': end_dt.isoformat(),
            'duration_minutes': duration_minutes,
            'target_date': activity_date.isoformat(),
            'ai_reason': 'FlowMate xếp vào Lịch vì câu nhập có thời gian cụ thể.',
            'confidence': 0.84 if explicit_time else 0.68,
        }

    priority_score, reason = _task_priority_for_due(base_date, due_date)
    due_iso = due_date.isoformat() if due_date else ''
    return {
        'kind': 'task',
        'title': title[:180],
        'due_date': due_iso,
        'target_date': (due_date or base_date).isoformat(),
        'priority_score': priority_score,
        'ai_reason': reason,
        'confidence': 0.78 if due_date else 0.58,
    }


def _normalize_checklist_payload(data):
    data = data or {}
    completed = data.get('completed') if isinstance(data.get('completed'), dict) else {}
    custom_items = data.get('custom_items') if isinstance(data.get('custom_items'), list) else []
    normalized_custom = []
    for item in custom_items[:100]:
        if not isinstance(item, dict):
            continue
        title = str(item.get('title') or '').strip()
        item_id = str(item.get('id') or '').strip()
        if not title or not item_id:
            continue
        normalized_custom.append({
            'id': item_id[:120],
            'title': title[:240],
            'completed': bool(item.get('completed')),
            'created_at': str(item.get('created_at') or datetime.utcnow().isoformat())[:40],
            'source': str(item.get('source') or 'manual')[:40],
            'item_type': str(item.get('item_type') or 'task')[:40],
            'due_date': str(item.get('due_date') or '')[:20],
            'due_at': str(item.get('due_at') or '')[:40],
            'ai_reason': str(item.get('ai_reason') or '')[:260],
            'priority_score': int(item.get('priority_score') or 0),
            'pinned': bool(item.get('pinned')),
        })
    return {
        'completed': {str(key)[:180]: bool(value) for key, value in completed.items()},
        'custom_items': _sort_custom_items(normalized_custom),
    }


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
            Schedule.update(schedule_id, calendar_event_id=new_event_id, db_path=db_path)
            _clear_schedule_cache(db_path)
            logger.info(f"Schedule {schedule_id} synced to Google Calendar: {new_event_id}")
            return new_event_id
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
                _sync_schedule_to_calendar(user_id, schedule_id, schedule, db_path)
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


@schedule_bp.route('/checklist', methods=['GET'])
def get_overview_checklist():
    """Return per-day overview checklist state for the current user."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    date_value = (request.args.get('date') or datetime.now(LOCAL_TZ).date().isoformat()).strip()
    cached = Cache.get(_checklist_cache_key(user_id, date_value), db_path=db_path)
    payload = _normalize_checklist_payload(cached)
    return jsonify({
        'success': True,
        'date': date_value,
        **payload,
    })


@schedule_bp.route('/checklist', methods=['PUT', 'POST'])
def save_overview_checklist():
    """Persist per-day overview checklist state for the current user."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    data = request.get_json() or {}
    date_value = (data.get('date') or request.args.get('date') or datetime.now(LOCAL_TZ).date().isoformat()).strip()
    payload = _normalize_checklist_payload(data)
    Cache.set(
        _checklist_cache_key(user_id, date_value),
        payload,
        ttl=_CHECKLIST_CACHE_TTL_SECONDS,
        db_path=db_path,
    )
    return jsonify({
        'success': True,
        'date': date_value,
        **payload,
    })


def _create_schedule_from_plan_item(user_id, db_path, item):
    title = str(item.get('title') or '').strip()
    start_time = str(item.get('start_time') or '').strip()
    end_time = str(item.get('end_time') or '').strip() or None
    description = str(item.get('description') or item.get('reason') or '').strip()
    duration_minutes = _parse_duration_minutes(item.get('duration_minutes'))
    if not title or not start_time:
        raise ValueError('Missing title or start_time')

    start_dt = _datetime_from_local_iso(start_time)
    end_dt = _datetime_from_local_iso(end_time)
    if start_dt and end_dt and end_dt <= start_dt:
        end_time = None
    end_time = _compute_end_time(start_time, end_time, duration_minutes)
    schedule_id = ScheduleService.create_schedule(
        title,
        description,
        start_time,
        [],
        end_time=end_time,
        duration_minutes=duration_minutes,
        db_path=db_path,
    )
    created_schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
    calendar_sync_pending = _sync_schedule_to_calendar_async(user_id, schedule_id, db_path)
    History.create(
        f"Tạo lịch từ gợi ý: {title}",
        f"Lịch đề xuất: {title} vào {start_time}",
        action_type='schedule_created',
        related_id=schedule_id,
        db_path=db_path,
    )
    return {
        'schedule_id': schedule_id,
        'schedule': created_schedule,
        'calendar_sync_pending': calendar_sync_pending,
    }


@schedule_bp.route('/plan-day', methods=['POST'])
def suggest_day_plan():
    """Suggest calendar slots for a natural-language list of day activities."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    data = request.get_json() or {}
    text = str(data.get('text') or '').strip()
    date_value = (data.get('date') or datetime.now(LOCAL_TZ).date().isoformat()).strip()
    if not text:
        return jsonify({'success': False, 'error': 'Missing text'}), 400

    plan = _build_suggested_day_plan(user_id, db_path, text, date_value)
    if not plan:
        return jsonify({
            'success': False,
            'error': 'not_a_day_plan',
            'message': 'Không phát hiện danh sách hoạt động để xếp lịch.',
        }), 400
    return jsonify({'success': True, **plan})


@schedule_bp.route('/plan-day/apply', methods=['POST'])
def apply_day_plan():
    """Create schedules from a previously suggested day plan."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    data = request.get_json() or {}
    items = data.get('items') if isinstance(data.get('items'), list) else []
    if not items:
        return jsonify({'success': False, 'error': 'Missing items'}), 400

    created = []
    try:
        for item in items[:50]:
            if not isinstance(item, dict):
                continue
            created.append(_create_schedule_from_plan_item(user_id, db_path, item))
        if not created:
            return jsonify({'success': False, 'error': 'No valid items'}), 400
        _clear_schedule_cache(db_path)
        return jsonify({
            'success': True,
            'kind': 'applied_plan',
            'created_count': len(created),
            'created': created,
            'message': 'Đã tạo lịch từ kế hoạch gợi ý',
        })
    except Exception as e:
        logger.error("Apply day plan failed: %s", e, exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@schedule_bp.route('/parse-draft', methods=['POST'])
def parse_schedule_draft():
    """Parse free text into schedule fields using the same extractor the
    chat flow uses (IntentOrchestrator.extract_schedule), so the pre-send
    confirm modal reflects Bob's actual understanding -- including
    period-of-day words (sang/chieu/toi) and "noi dung la:" content markers
    -- instead of a separate, cruder client-side guess. Fields the extractor
    isn't confident about (no date/time signal, no content marker) come
    back empty rather than guessed."""
    data = request.get_json() or {}
    message = str(data.get('message') or '').strip()
    if not message:
        return jsonify({'success': False, 'error': 'Missing message'}), 400

    parsed = _draft_orchestrator.extract_schedule(message)

    date_value = ''
    start_clock = ''
    end_clock = ''
    if parsed.get('start_time'):
        start_dt = datetime.fromisoformat(parsed['start_time'])
        date_value = start_dt.date().isoformat()
        start_clock = start_dt.strftime('%H:%M')
    if parsed.get('end_time'):
        end_dt = datetime.fromisoformat(parsed['end_time'])
        end_clock = end_dt.strftime('%H:%M')

    return jsonify({
        'success': True,
        'title': parsed.get('title') or '',
        'description': parsed.get('description') or '',
        'date': date_value,
        'start_time': start_clock,
        'end_time': end_clock,
        'attendees': parsed.get('attendees') or [],
        'location': parsed.get('location') or '',
    })


@schedule_bp.route('/quick-add', methods=['POST'])
def quick_add_plan_item():
    """Add natural-language input as either a checklist task or a calendar activity."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    data = request.get_json() or {}
    text = str(data.get('text') or '').strip()
    date_value = (data.get('date') or datetime.now(LOCAL_TZ).date().isoformat()).strip()

    if not text:
        return jsonify({'success': False, 'error': 'Missing text'}), 400

    suggested_plan = _build_suggested_day_plan(user_id, db_path, text, date_value)
    if suggested_plan:
        return jsonify({'success': True, **suggested_plan})

    plan = _classify_quick_plan(text, date_value)

    if plan.get('kind') == 'activity':
        try:
            schedule_id = ScheduleService.create_schedule(
                plan['title'],
                plan.get('description', ''),
                plan['start_time'],
                [],
                end_time=plan.get('end_time'),
                duration_minutes=plan.get('duration_minutes'),
                db_path=db_path,
            )
            created_schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
            calendar_sync_pending = _sync_schedule_to_calendar_async(user_id, schedule_id, db_path)
            History.create(
                f"Tạo lịch nhanh: {plan['title']}",
                f"Nguồn nhập: {text}",
                action_type='schedule_created',
                related_id=schedule_id,
                db_path=db_path,
            )
            _clear_schedule_cache(db_path)
            return jsonify({
                'success': True,
                'kind': 'activity',
                'classification': plan,
                'schedule_id': schedule_id,
                'schedule': created_schedule,
                'calendar_sync_pending': calendar_sync_pending,
                'message': 'Đã thêm vào lịch',
            })
        except Exception as e:
            logger.error("Quick activity creation failed: %s", e, exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    checklist_date = date_value
    cached = Cache.get(_checklist_cache_key(user_id, checklist_date), db_path=db_path)
    payload = _normalize_checklist_payload(cached)
    item = {
        'id': f"manual:{uuid.uuid4().hex[:12]}",
        'title': plan.get('title') or text,
        'completed': False,
        'created_at': datetime.utcnow().isoformat(),
        'source': 'manual',
        'item_type': 'task',
        'due_date': plan.get('due_date') or '',
        'due_at': '',
        'ai_reason': plan.get('ai_reason') or '',
        'priority_score': plan.get('priority_score') or 0,
        'pinned': False,
    }
    payload['custom_items'] = _sort_custom_items([item, *payload.get('custom_items', [])])
    Cache.set(
        _checklist_cache_key(user_id, checklist_date),
        payload,
        ttl=_CHECKLIST_CACHE_TTL_SECONDS,
        db_path=db_path,
    )
    return jsonify({
        'success': True,
        'kind': 'task',
        'classification': plan,
        'date': checklist_date,
        'item': item,
        **payload,
        'message': 'Đã thêm vào checklist',
    })


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
