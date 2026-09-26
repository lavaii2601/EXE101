"""Natural-language quick-plan parsing: date/time/duration extraction from
freeform Vietnamese/English text, the "suggest a day plan" slot-finding
engine, and the plan-day/parse-draft/quick-add routes built on top of it."""
import re
import uuid
from datetime import datetime, timedelta, time as dt_time

from flask import request, jsonify

from services.schedule_service import ScheduleService
from models.cache import Cache
from models.schedule import Schedule, LOCAL_TZ
from models.history import History
from utils.user_context import get_current_user_id, get_user_db_path

from .shared import (
    schedule_bp,
    logger,
    _draft_orchestrator,
    _parse_duration_minutes,
    _compute_end_time,
    _clear_schedule_cache,
)
from .checklist import (
    _checklist_cache_key,
    _normalize_checklist_payload,
    _sort_custom_items,
    _CHECKLIST_CACHE_TTL_SECONDS,
)
from .gcal_sync import _sync_schedule_to_calendar_async

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
    return re.sub(r'\s+', ' ', title).strip(' ,.-')


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
    checklist_key = _checklist_cache_key(user_id, checklist_date)
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
    payload = None
    for _ in range(3):
        current = _normalize_checklist_payload(Cache.get(checklist_key, db_path=db_path))
        candidate = {
            **current,
            'custom_items': _sort_custom_items([item, *current.get('custom_items', [])]),
        }
        saved, latest = Cache.set_versioned(
            checklist_key,
            candidate,
            expected_revision=current['revision'],
            ttl=_CHECKLIST_CACHE_TTL_SECONDS,
            db_path=db_path,
        )
        if saved:
            payload = latest
            break
    if payload is None:
        return jsonify({
            'error': 'checklist_conflict',
            'message': 'Checklist changed repeatedly. Reload and try again.',
        }), 409
    return jsonify({
        'success': True,
        'kind': 'task',
        'classification': plan,
        'date': checklist_date,
        'item': item,
        **payload,
        'message': 'Đã thêm vào checklist',
    })
