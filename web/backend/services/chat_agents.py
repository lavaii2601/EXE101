import json
import os
import re
import logging
import threading as _thr
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from config import Config
from services.ai_service import AIService
from services.gmail_service import get_cached_gmail_service
from services.intent_orchestrator import IntentOrchestrator
from services.schedule_service import ScheduleService
from services.calendar_service import CalendarService
from services.web_research_service import web_research_service
from models.cache import Cache
from models.history import History
from models.schedule import Schedule, LOCAL_TZ
from utils.user_context import get_user_token_file
from routes.knowledge import knowledge_service
from routes.schedule import (
    _clear_schedule_cache,
    _clear_overview_cache,
    _sync_schedule_to_calendar_async,
    _delete_calendar_event_async,
    _prune_stale_duplicate_after_move_async,
    _checklist_cache_key,
    _normalize_checklist_payload,
    _sort_custom_items,
    _CHECKLIST_CACHE_TTL_SECONDS,
    _build_suggested_day_plan,
)

logger = logging.getLogger(__name__)

# Singleton ownership: chat.py imports these back instead of constructing its
# own copies, so ai_service.last_provider_used etc. stay consistent across
# every agent and route that reads them.
ai_service = AIService()
intent_orchestrator = IntentOrchestrator()


@dataclass
class ChatContext:
    user_message: str
    user_id: str
    db_path: str
    chat_session_id: str
    mode: str
    mode_prompt: str
    task: str
    intent_result: dict
    refresh_targets: list = field(default_factory=list)
    client_confirm: bool = False
    schedule_override: dict = field(default_factory=dict)


@dataclass
class AgentResult:
    response: str
    workspace_sources: list = None
    refresh_targets: list = field(default_factory=list)
    schedule_created: dict = None
    schedule_suggestion: dict = None
    day_plan_suggestion: dict = None
    suggested_actions: list = None
    action: str = None
    action_type: str = 'chat'
    ai_used: bool = False
    grounded: bool = True
    provider: str = None
    demo_mode: bool = False
    email_source: dict = None
    email_sources: list = None


def _normalize_intent_text(value):
    value = unicodedata.normalize('NFD', str(value or '').lower())
    value = ''.join(char for char in value if unicodedata.category(char) != 'Mn')
    return value.replace('đ', 'd')


def _latest_email_count(message):
    normalized = _normalize_intent_text(message)
    email_word = r'(?:e-?mails?|gmails?|mails?|thu|hop thu)'
    latest_word = (
        r'(?:moi nhat|gan nhat|gan day|vua nhan|moi nhan|latest|newest|'
        r'most recent|recent|just received|newly received|last)'
    )
    match = (
        re.search(rf'\b(\d{{1,2}})\s*(?:{latest_word}\s*)?{email_word}\b', normalized)
        or re.search(rf'\b{latest_word}\s*(\d{{1,2}})\s*{email_word}\b', normalized)
        or re.search(rf'\b{email_word}\s*{latest_word}\s*(\d{{1,2}})\b', normalized)
    )
    if match:
        return max(1, min(int(match.group(1)), 5))

    number_words = {
        'mot': 1, 'một': 1, 'one': 1,
        'hai': 2, 'two': 2,
        'ba': 3, 'three': 3,
        'bon': 4, 'bốn': 4, 'tu': 4, 'four': 4,
        'nam': 5, 'năm': 5, 'five': 5,
    }
    for word, count in number_words.items():
        if (
            re.search(rf'\b{word}\s+(?:{latest_word}\s+)?{email_word}\b', normalized)
            or re.search(rf'\b{latest_word}\s+{word}\s+{email_word}\b', normalized)
        ):
            return count
    return 1


def _summarize_latest_emails(user_id, count=1, query_override=None):
    token_file = get_user_token_file(user_id)
    if not token_file or not os.path.exists(token_file):
        raise RuntimeError('Gmail chưa được kết nối cho tài khoản này.')

    service = get_cached_gmail_service(token_file)
    count = max(1, min(int(count or 1), 5))
    query, include_read = query_override or ('in:inbox', True)
    latest = service.get_emails(
        max_results=count,
        query=query,
        include_read=include_read
    )
    if not latest:
        raise RuntimeError('Không tìm thấy email nào trong hộp thư đến.')

    email_ids = [metadata.get('id') for metadata in latest[:count] if metadata.get('id')]
    full_emails = {email['id']: email for email in service.get_email_details_batch(email_ids)}

    emails = []
    sections = []
    for index, email_id in enumerate(email_ids, start=1):
        email = full_emails.get(email_id)
        if not email:
            logger.warning("Could not load full Gmail message %s", email_id)
            continue

        summary = ai_service.summarize_email_polished(email, user_id=user_id)
        emails.append(email)
        sections.append(
            f"{index}. {email.get('subject') or '(Không có tiêu đề)'}\n"
            f"Người gửi: {email.get('sender') or 'Không xác định'}\n"
            f"Thời gian: {email.get('date') or 'Không xác định'}\n\n"
            f"{summary}"
        )

    if not emails:
        raise RuntimeError('Không thể tải nội dung đầy đủ của các email gần nhất.')

    heading = "EMAIL MỚI NHẤT" if len(emails) == 1 else f"{len(emails)} EMAIL GẦN NHẤT"
    return f"{heading}\n\n" + "\n\n--------------------\n\n".join(sections), emails


def _intent_sources(message):
    normalized = _normalize_intent_text(message)
    overview = any(term in normalized for term in (
        'tong quan', 'hom nay co gi', 'can lam gi', 'viec cua toi',
        'dashboard', 'overview', 'today overview'
    ))
    # Bare 'hoat dong'/'activity' is excluded here on purpose: it shows up
    # just as often in forward-looking checklist/day-plan requests as in
    # actual "what did I do" lookups, so it would wrongly pull in history
    # context (and skip calendar context, see below) for those messages too.
    history_requested = overview or any(term in normalized for term in (
        'lich su', 'history', 'da lam gi', 'lam gi roi'
    ))
    sources = set()
    if overview or any(term in normalized for term in (
        'email', 'e-mail', 'gmail', 'hop thu', 'thu moi', 'thu chua doc'
    )):
        sources.add('email')
    if overview or (
        not history_requested
        and any(term in normalized for term in (
        'lich', 'calendar', 'cuoc hop', 'su kien', 'appointment', 'meeting'
        ))
    ):
        sources.add('calendar')
    if history_requested:
        sources.add('history')
    if overview or any(term in normalized for term in (
        'ho so', 'tai khoan', 'che do', 'cai dat', 'profile', 'account', 'settings', 'mode'
    )):
        sources.add('profile')
    return sources


def _format_email_context(user_id):
    token_file = get_user_token_file(user_id)
    if not token_file or not os.path.exists(token_file):
        return "EMAIL\nGmail chưa được kết nối."

    emails = get_cached_gmail_service(token_file).get_emails(
        max_results=5,
        query='in:inbox',
        include_read=True
    )
    if not emails:
        return "EMAIL\nKhông có email trong hộp thư đến."

    lines = ["EMAIL GẦN ĐÂY"]
    for index, email in enumerate(emails, start=1):
        snippet = re.sub(r'\s+', ' ', email.get('snippet', '') or '').strip()
        lines.extend([
            f"{index}. Người gửi: {email.get('sender') or 'Không xác định'}",
            f"   Tiêu đề: {email.get('subject') or '(Không có tiêu đề)'}",
            f"   Thời gian: {email.get('date') or 'Không xác định'}",
            f"   Trạng thái: {'Chưa đọc' if email.get('is_unread') else 'Đã đọc'}",
            f"   Xem trước: {snippet[:320] or 'Không có nội dung xem trước'}",
        ])
    return "\n".join(lines)


def _calendar_window(message):
    normalized = _normalize_intent_text(message)
    now = datetime.now().astimezone()
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    if 'tuan truoc' in normalized or 'last week' in normalized:
        return monday - timedelta(days=7), monday, 'TUẦN TRƯỚC'
    if 'tuan nay' in normalized or 'this week' in normalized:
        return monday, monday + timedelta(days=7), 'TUẦN NÀY'
    if 'tuan sau' in normalized or 'next week' in normalized:
        return monday + timedelta(days=7), monday + timedelta(days=14), 'TUẦN SAU'
    if 'hom qua' in normalized or 'yesterday' in normalized:
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1), 'HÔM QUA'
    if 'hom nay' in normalized or 'today' in normalized:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1), 'HÔM NAY'

    return now, now + timedelta(days=30), 'SẮP TỚI'


def _parse_schedule_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TZ)
        return parsed.astimezone(LOCAL_TZ)
    except (TypeError, ValueError):
        return None


def _schedule_response_key(title, start_value):
    start_dt = _parse_schedule_datetime(start_value)
    normalized_title = ' '.join(str(title or '').strip().lower().split())
    normalized_start = start_dt.strftime('%Y-%m-%dT%H:%M') if start_dt else str(start_value or '').strip()
    return normalized_title, normalized_start


def _format_schedule_response_time(start_value, end_value):
    start_dt = _parse_schedule_datetime(start_value)
    end_dt = _parse_schedule_datetime(end_value)
    if not start_dt:
        return 'Khong xac dinh'
    date_text = start_dt.strftime('%d/%m/%Y')
    start_text = start_dt.strftime('%H:%M')
    if end_dt:
        if end_dt.date() == start_dt.date():
            return f'{date_text}, {start_text} - {end_dt.strftime("%H:%M")} (GMT+7)'
        return f'{date_text}, {start_text} - {end_dt.strftime("%d/%m/%Y %H:%M")} (GMT+7)'
    return f'{date_text}, {start_text} (GMT+7)'


def _format_calendar_context(message, user_id, db_path, window_override=None):
    if window_override:
        window_start, window_end, window_label = window_override
    else:
        window_start, window_end, window_label = _calendar_window(message)
    lines = [
        f"LICH VA SU KIEN {window_label}",
        f"Khoang thoi gian: {window_start.date().isoformat()} den {(window_end - timedelta(days=1)).date().isoformat()}",
    ]
    token_file = get_user_token_file(user_id)
    google_events = []
    if token_file and os.path.exists(token_file):
        google_events = CalendarService(token_file=token_file).get_events(
            max_results=50,
            time_min=window_start.replace(tzinfo=LOCAL_TZ).isoformat(),
            time_max=window_end.replace(tzinfo=LOCAL_TZ).isoformat()
        )

    local_schedules = Schedule.get_between(
        window_start.isoformat(),
        window_end.isoformat(),
        limit=100,
        db_path=db_path
    )

    if not google_events and not local_schedules:
        return "\n".join(lines + [f"Khong co lich hoac su kien trong {window_label.lower()}."])

    items_by_key = {}
    for event in google_events:
        key = _schedule_response_key(event.get('title'), event.get('start'))
        if key not in items_by_key:
            items_by_key[key] = {
                'title': event.get('title') or '(Khong co tieu de)',
                'start': event.get('start'),
                'end': event.get('end'),
                'location': event.get('location') or '',
                'status': '',
            }

    for schedule in local_schedules:
        key = _schedule_response_key(schedule.get('title'), schedule.get('start_time'))
        if key in items_by_key:
            existing = items_by_key[key]
            existing['status'] = existing.get('status') or schedule.get('status') or ''
            existing['location'] = existing.get('location') or schedule.get('location') or ''
            continue
        items_by_key[key] = {
            'title': schedule.get('title') or '(Khong co tieu de)',
            'start': schedule.get('start_time'),
            'end': schedule.get('end_time'),
            'location': schedule.get('location') or '',
            'status': schedule.get('status') or '',
        }

    items = sorted(
        items_by_key.values(),
        key=lambda item: (
            _parse_schedule_datetime(item.get('start')) or datetime.max.replace(tzinfo=LOCAL_TZ),
            item.get('title') or ''
        )
    )
    if not items:
        return "\n".join(lines + [f"Khong co lich hoac su kien trong {window_label.lower()}."])

    for item_index, item in enumerate(items, start=1):
        lines.append(f"{item_index}. {item.get('title')}")
        lines.append(f"   Thoi gian: {_format_schedule_response_time(item.get('start'), item.get('end'))}")
        if item.get('location'):
            lines.append(f"   Dia diem: {item.get('location')}")
        if item.get('status') and item.get('status') != 'pending':
            lines.append(f"   Trang thai: {item.get('status')}")
    return "\n".join(lines)


_SCHEDULE_ACTION_STOPWORDS = (
    'doi', 'sua', 'cap nhat', 'thay doi', 'chuyen', 'xoa', 'huy', 'bo lich',
    'cancel', 'delete', 'tao', 'dat', 'them', 'add', 'book', 'nhac toi', 'remind',
)
_SCHEDULE_NOUN_STOPWORDS = (
    'lich', 'su kien', 'hen', 'hop', 'meeting', 'appointment', 'calendar',
)


def _find_matching_schedules(message, db_path, window_days=14):
    """Best-effort keyword match against existing schedules in a date window --
    NEVER used to act directly. Callers must always show the matched
    schedule's current title+time back to the user for confirmation before
    mutating anything (see ScheduleUpdateAgent/ScheduleDeleteAgent)."""
    normalized = _normalize_intent_text(message)
    for phrase in _SCHEDULE_ACTION_STOPWORDS + _SCHEDULE_NOUN_STOPWORDS:
        normalized = normalized.replace(phrase, ' ')
    significant_words = [w for w in normalized.split() if len(w) >= 3]
    if not significant_words:
        return []

    now = datetime.now()
    window_start = now - timedelta(days=1)
    window_end = now + timedelta(days=window_days)
    candidates = Schedule.get_between(window_start.isoformat(), window_end.isoformat(), limit=100, db_path=db_path)

    scored = []
    for schedule in candidates:
        title_normalized = _normalize_intent_text(schedule.get('title') or '')
        score = sum(1 for word in significant_words if word in title_normalized)
        if score > 0:
            item = dict(schedule)
            item['_score'] = score
            scored.append(item)

    scored.sort(key=lambda item: item['_score'], reverse=True)
    return scored


def _format_history_context(db_path):
    records = History.get_recent(limit=10, db_path=db_path)
    if not records:
        return "LỊCH SỬ HOẠT ĐỘNG\nChưa có hoạt động nào."

    lines = ["LỊCH SỬ HOẠT ĐỘNG GẦN ĐÂY"]
    for index, record in enumerate(records, start=1):
        request_text = re.sub(r'\s+', ' ', record.get('user_message', '') or '').strip()
        result_text = re.sub(r'\s+', ' ', record.get('assistant_response', '') or '').strip()
        lines.extend([
            f"{index}. Loại: {record.get('action_type') or 'activity'}",
            f"   Thời gian: {record.get('created_at') or 'Không xác định'}",
            f"   Nội dung: {request_text[:240] or 'Không có'}",
            f"   Kết quả: {result_text[:320] or 'Không có'}",
        ])
    return "\n".join(lines)


def _format_profile_context(user_id):
    from models.user import User
    user = User.get(user_id) or {}
    return "\n".join([
        "HỒ SƠ VÀ CÀI ĐẶT",
        f"Tên: {user.get('name') or user.get('gmail_name') or 'Chưa thiết lập'}",
        f"Email: {user.get('gmail_email') or user.get('email') or 'Chưa thiết lập'}",
        f"Chế độ làm việc: {user.get('user_mode') or 'Chưa chọn'}",
        f"Gmail đã kết nối: {'Có' if user.get('gmail_connected') else 'Không'}",
    ])


def _direct_schedule_list_response(message, user_id, db_path, window_override=None):
    context = _format_calendar_context(message, user_id, db_path, window_override=window_override)
    return (
        context
        + "\n\nMình chỉ liệt kê dữ liệu lịch đang có trong Calendar/FlowMate, "
        "không tự suy đoán thêm sự kiện ngoài dữ liệu này."
    )


_CURRENT_TIME_TERMS = (
    'may gio', 'bay gio la may gio', 'hien tai may gio', 'gio hien tai',
    'hom nay ngay may', 'hom nay la ngay nao', 'ngay hien tai',
    'what time', 'current time', 'time now', 'what date', "today's date",
)


def _direct_current_time_response(message):
    normalized = _normalize_intent_text(message)
    if not any(term in normalized for term in _CURRENT_TIME_TERMS):
        return None

    now = datetime.now(LOCAL_TZ)
    weekday = (
        'thứ Hai', 'thứ Ba', 'thứ Tư', 'thứ Năm', 'thứ Sáu', 'thứ Bảy', 'Chủ nhật'
    )[now.weekday()]
    time_24 = now.strftime('%H:%M:%S')
    date_text = f"{weekday}, ngày {now.day:02d}/{now.month:02d}/{now.year}"
    tz_key = getattr(LOCAL_TZ, 'key', None)
    tz_label = f"{tz_key}, UTC+7" if tz_key else "UTC+7"

    if any(term in normalized for term in ('what time', 'current time', 'time now', 'what date', "today's date")):
        return (
            f"In Vietnam ({tz_label}), it is {time_24} on {date_text}."
        )

    return (
        f"Hiện tại ở Việt Nam ({tz_label}) là {time_24}, "
        f"{date_text}."
    )


WINDOW_LABELS_VN = {
    'today': 'HÔM NAY',
    'yesterday': 'HÔM QUA',
    'this_week': 'TUẦN NÀY',
    'next_week': 'TUẦN SAU',
    'last_week': 'TUẦN TRƯỚC',
}


def _window_override_from_entities(entities):
    """Turn an AI-classified `window` entity into the (start, end, label) tuple
    that _format_calendar_context expects, so an AI-assisted schedule.list
    intent actually changes which range gets queried -- not just the label.
    """
    window = (entities or {}).get('window')
    if not isinstance(window, dict):
        return None
    try:
        start = datetime.fromisoformat(str(window.get('start'))).replace(tzinfo=LOCAL_TZ)
        end = datetime.fromisoformat(str(window.get('end'))).replace(tzinfo=LOCAL_TZ)
    except (TypeError, ValueError):
        return None
    if end <= start:
        return None
    label = WINDOW_LABELS_VN.get(window.get('label'), 'KHOẢNG THỜI GIAN ĐÃ CHỌN')
    return start, end, label


def _email_lookup_query(message):
    normalized = _normalize_intent_text(message)
    include_read = 'chua doc' not in normalized and 'unread' not in normalized
    query = 'in:inbox' if include_read else 'is:unread'

    quoted = re.search(r'"([^"]{2,80})"', message or '')
    if quoted:
        return f'{query} "{quoted.group(1).strip()}"', include_read

    sender_match = re.search(r'(?:tu|from)\s+([\w\.-]+@[\w\.-]+\.\w+)', normalized)
    if sender_match:
        return f'{query} from:{sender_match.group(1)}', include_read

    return query, include_read


def _gmail_date_query_parts(date_window):
    """before: is exclusive in Gmail's query syntax, so it's set to the day
    after the window's (inclusive) end date."""
    if not isinstance(date_window, dict):
        return []
    try:
        start = datetime.fromisoformat(str(date_window.get('start'))).date()
        end = datetime.fromisoformat(str(date_window.get('end'))).date()
    except (TypeError, ValueError):
        return []
    if end < start:
        return []
    after = start.strftime('%Y/%m/%d')
    before = (end + timedelta(days=1)).strftime('%Y/%m/%d')
    return [f'after:{after}', f'before:{before}']


def _query_override_from_entities(entities):
    """Build a Gmail query from AI/rule-classified entities: `query`
    (sender/keyword/unread_only) and/or `date_window` (a specific day or week
    the user asked about, e.g. "hom nay"), instead of re-parsing the raw
    message text with regex.
    """
    entities = entities or {}
    query_info = entities.get('query')
    date_window = entities.get('date_window')
    if not isinstance(query_info, dict) and not date_window:
        return None
    query_info = query_info if isinstance(query_info, dict) else {}

    unread_only = bool(query_info.get('unread_only'))
    include_read = not unread_only
    parts = ['is:unread' if unread_only else 'in:inbox']

    sender = str(query_info.get('sender') or '').strip()
    keyword = str(query_info.get('keyword') or '').strip()
    if sender and re.match(r'^[\w.+-]+@[\w.-]+\.\w+$', sender):
        parts.append(f'from:{sender}')
    elif sender:
        keyword = f'{sender} {keyword}'.strip()
    if keyword:
        parts.append(f'"{keyword[:80]}"')

    parts.extend(_gmail_date_query_parts(date_window))

    if len(parts) == 1:
        return None
    return ' '.join(parts), include_read


def _direct_email_search_response(message, user_id, limit=8, query_override=None):
    token_file = get_user_token_file(user_id)
    if not token_file or not os.path.exists(token_file):
        return "Gmail chưa được kết nối, nên mình chưa thể xem email thật của bạn."

    query, include_read = query_override or _email_lookup_query(message)
    emails = get_cached_gmail_service(token_file).get_emails(
        max_results=max(1, min(limit, 10)),
        query=query,
        include_read=include_read
    )
    if not emails:
        return "Không tìm thấy email phù hợp trong Gmail theo dữ liệu hiện tại."

    lines = [
        "EMAIL TÌM THẤY",
        f"Nguồn: Gmail thật, truy vấn: {query}",
    ]
    for index, email in enumerate(emails, start=1):
        snippet = re.sub(r'\s+', ' ', email.get('snippet', '') or '').strip()
        lines.extend([
            f"{index}. {email.get('subject') or '(Không có tiêu đề)'}",
            f"   Người gửi: {email.get('sender') or 'Không xác định'}",
            f"   Thời gian: {email.get('date') or 'Không xác định'}",
            f"   Trạng thái: {'Chưa đọc' if email.get('is_unread') else 'Đã đọc'}",
            f"   Xem trước: {snippet[:220] or 'Không có nội dung xem trước'}",
        ])
    lines.append("\nMình không tự kết luận nội dung ngoài phần Gmail trả về ở trên.")
    return "\n".join(lines)


def _format_knowledge_context(message, user_id=None):
    try:
        results = knowledge_service.search(message, top_k=3, user_id=user_id)
    except Exception:
        logger.warning("Knowledge base search failed", exc_info=True)
        return ''
    if not results:
        return ''
    lines = ["KIẾN THỨC THAM KHẢO (FlowMate/Bob)"]
    for index, doc in enumerate(results, start=1):
        lines.append(f"{index}. {doc.get('title')}: {doc.get('content')}")
    return "\n".join(lines)


_WEB_LEARNING_HINT_TERMS = (
    'hoc', 'hoc hoi', 'trau doi', 'cai thien', 'toi uu', 'kinh nghiem',
    'best practice', 'practice', 'guide', 'how to', 'workflow', 'process',
    'quy trinh', 'nguyen tac', 'framework', 'playbook', 'automation',
    'agent', 'assistant', 'email management', 'calendar management',
    'task management', 'productivity', 'prompt', 'safety',
)


def _learning_quota_available(user_id, db_path, scope, max_per_day):
    try:
        max_per_day = int(max_per_day)
    except (TypeError, ValueError):
        max_per_day = 0
    if max_per_day <= 0:
        return False
    if not user_id or user_id == 'default':
        return False
    if not db_path:
        return True
    key = f"learning_quota::{scope}::{user_id}::{datetime.now(LOCAL_TZ).date().isoformat()}"
    payload = Cache.get(key, db_path=db_path) or {}
    count = int(payload.get('count') or 0)
    if count >= max_per_day:
        return False
    Cache.set(key, {'count': count + 1}, ttl=36 * 3600, db_path=db_path)
    return True


def _should_extract_web_learning(query):
    normalized = _normalize_intent_text(query)
    return any(term in normalized for term in _WEB_LEARNING_HINT_TERMS)


def _extract_web_learning_candidate(research_result, user_id):
    if not getattr(ai_service, 'configured_providers', None):
        return None
    query = str((research_result or {}).get('query') or '').strip()
    results = (research_result or {}).get('results') or []
    if not query or not results or not _should_extract_web_learning(query):
        return None

    source_lines = []
    for index, result in enumerate(results[:4], start=1):
        snippet = re.sub(r'\s+', ' ', str(result.get('snippet') or '')).strip()
        source_lines.append(
            f"{index}. {result.get('title') or result.get('url')}\n"
            f"URL: {result.get('url')}\n"
            f"Snippet: {snippet[:700]}"
        )
    messages = [
        {
            "role": "system",
            "content": (
                "You distill public web research into durable learning notes for Bob, "
                "a FlowMate workflow assistant. Save only reusable process knowledge, "
                "best practices, source-use rules, or action-handling principles. "
                "Do not save raw search results, news trivia, volatile facts, private data, "
                "or one-off answers. Return only JSON: "
                '{"should_learn": true/false, "title": "<short>", '
                '"content": "<1-3 reusable sentences with source URLs if relevant>", '
                '"tags": "<comma-separated>", "confidence": 0.0-1.0}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Query: {query}\n\nSources:\n" + "\n\n".join(source_lines)
            ),
        },
    ]
    try:
        raw = ai_service.generate_response(
            messages,
            max_tokens=min(int(getattr(Config, 'AI_MENTOR_MAX_TOKENS', 260)), 320),
            task='analyze',
            user_id=user_id,
        )
    except Exception:
        logger.info("Web learning extraction skipped", exc_info=True)
        return None

    data = _parse_memory_json(raw)
    if not data or not data.get('should_learn'):
        return None
    try:
        confidence = float(data.get('confidence', 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.70:
        return None
    title = _redact_mentor_text(str(data.get('title') or '').strip())[:150]
    content = _redact_mentor_text(str(data.get('content') or '').strip())[:900]
    tags = str(data.get('tags') or '').strip()[:220]
    if not title or not content:
        return None
    return {'title': title, 'content': content, 'tags': tags, 'confidence': confidence}


def _learn_from_web_research(research_result, user_id, db_path=None):
    if not getattr(Config, 'WEB_RESEARCH_AUTO_LEARN_ENABLED', True):
        return
    if not user_id or user_id == 'default':
        return
    query = str((research_result or {}).get('query') or '').strip()
    if not query or not _should_extract_web_learning(query):
        return
    if not getattr(ai_service, 'configured_providers', None):
        return

    if not _learning_quota_available(
        user_id,
        db_path,
        'web',
        getattr(Config, 'WEB_RESEARCH_LEARNING_MAX_PER_DAY', 6),
    ):
        return

    candidate = _extract_web_learning_candidate(research_result, user_id)
    if not candidate:
        return

    title = f"Web learning: {candidate['title']}"
    content = (
        f"Query: {query}\n"
        f"Confidence: {candidate.get('confidence', 0):.2f}\n"
        f"Lesson: {candidate['content']}"
    )
    tags = ','.join(
        part.strip()
        for part in f"web-learning,internet,curated,{candidate.get('tags') or ''}".split(',')
        if part.strip()
    )[:240]

    existing_match = None
    try:
        for result in knowledge_service.search(title, top_k=5, min_score=0.38, user_id=user_id):
            if result.get("source") == "web" and result.get("user_id") == user_id:
                existing_match = result
                break
    except Exception:
        existing_match = None

    try:
        if existing_match:
            knowledge_service.update_document(
                existing_match["id"],
                title=title,
                content=content,
                tags=tags,
            )
        else:
            knowledge_service.add_document(
                title,
                content,
                tags=tags,
                source="web",
                user_id=user_id,
            )
    except Exception:
        logger.warning("Failed to save web research memory for user %s", user_id, exc_info=True)


def _learn_from_web_research_async(research_result, user_id, db_path=None):
    _thr.Thread(
        target=_learn_from_web_research,
        args=(research_result, user_id, db_path),
        daemon=True,
    ).start()


def _build_workspace_context(message, user_id, db_path):
    sources = _intent_sources(message)
    context_parts = []
    if 'email' in sources:
        context_parts.append(_format_email_context(user_id))
    if 'calendar' in sources:
        context_parts.append(_format_calendar_context(message, user_id, db_path))
    if 'history' in sources:
        context_parts.append(_format_history_context(db_path))
    if 'profile' in sources:
        context_parts.append(_format_profile_context(user_id))

    # Always attempt a (free, local) knowledge-base lookup -- the TF-IDF
    # relevance threshold already filters out unrelated chit-chat, so this
    # only adds context when it actually found something relevant. Scoped
    # to this user_id so another user's auto-learned memories never leak in.
    knowledge_context = _format_knowledge_context(message, user_id=user_id)
    if knowledge_context:
        context_parts.append(knowledge_context)
        sources.add('knowledge')

    try:
        web_research = web_research_service.research(message, workspace_sources=sources)
    except Exception:
        logger.warning("Web research failed for user %s", user_id, exc_info=True)
        web_research = None
    if web_research and web_research.get('context'):
        context_parts.append(web_research['context'])
        sources.add('internet')
        _learn_from_web_research_async(web_research, user_id, db_path)

    return sources, "\n\n".join(context_parts)


# Cheap, local gate before paying for an AI round-trip to check "is there
# anything worth remembering here" -- most chat turns aren't (a one-off
# question, a status check, small talk), so most messages should never reach
# the AI extraction call at all. Bilingual, mirrors the same pattern used to
# gate AI-assisted intent classification in intent_orchestrator.py.
_MEMORY_HINT_TERMS = (
    "nho la", "nho rang", "tu nay", "tu gio", "luon luon", "moi lan",
    "goi toi la", "xung ho", "quy tac", "thuc ra", "khong phai", "ma la",
    "uu tien", "thoi quen", "so thich",
    "remember", "from now on", "always", "every time", "call me",
    "actually it's", "actually it is", "note that", "my preference",
    "rule of thumb", "i prefer", "in the future",
)


def _has_memory_hint(message):
    normalized = _normalize_intent_text(message)
    return any(term in normalized for term in _MEMORY_HINT_TERMS)


def _parse_memory_json(raw):
    if not raw:
        return None
    cleaned = str(raw).strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        data = json.loads(cleaned)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _extract_memory_candidate(user_message, assistant_response, user_id):
    system_message = {
        "role": "system",
        "content": (
            "Ban la module trich xuat tri nho dai han cho tro ly AI Bob. Doc tin nhan cua "
            "nguoi dung va cau tra loi cua Bob, xac dinh xem co THONG TIN ON DINH dang nho "
            "lau dai khong: nguoi dung sua loi Bob, neu so thich/quy tac ca nhan, cach xung "
            "ho rieng, thuat ngu/quy tac nghiep vu rieng cua ho. KHONG trich xuat du lieu "
            "tam thoi mot lan (mot lich hen cu the, mot email cu the, cau hoi thong thuong, "
            "small talk). Neu khong co gi dang nho, tra ve should_remember=false. Nguoi dung "
            "co the viet tieng Viet hoac tieng Anh. TRA VE DUY NHAT JSON, khong giai thich, "
            "khong dung markdown: "
            '{"should_remember": true/false, "title": "<ngan gon>", '
            '"content": "<noi dung can nho, 1-2 cau>", "tags": "<tu khoa, cach nhau boi dau phay>"}'
        ),
    }
    user_turn = {
        "role": "user",
        "content": f"TIN NHAN NGUOI DUNG: \"{user_message}\"\n\nTRA LOI CUA BOB: \"{assistant_response}\"",
    }
    try:
        raw = ai_service.generate_response(
            [system_message, user_turn],
            max_tokens=220,
            task="memory_extraction",
            user_id=user_id,
        )
    except Exception:
        logger.warning("Memory extraction AI call failed", exc_info=True)
        return None
    data = _parse_memory_json(raw)
    if not data or not data.get("should_remember"):
        return None
    title = str(data.get("title") or "").strip()[:150]
    content = str(data.get("content") or "").strip()[:500]
    tags = str(data.get("tags") or "").strip()[:200]
    if not title or not content:
        return None
    return {"title": title, "content": content, "tags": tags}


def learn_from_exchange(user_message, assistant_response, user_id):
    """Best-effort: silently look for a fact/preference/correction worth
    remembering in this exchange and save it as a per-user 'auto' knowledge
    document, so Bob can recall it in later chats without the user ever
    having to fill in the manual Knowledge form. Must never raise -- this
    always runs as a fire-and-forget background thread off the chat
    response path."""
    try:
        if not user_id or user_id == 'default' or not _has_memory_hint(user_message):
            return
        candidate = _extract_memory_candidate(user_message, assistant_response, user_id)
        if not candidate:
            return

        # Look for an existing auto-learned memory on the same topic for
        # this user and update it in place instead of accumulating
        # near-duplicate memories every time a similar thing comes up.
        existing_match = None
        try:
            for result in knowledge_service.search(candidate["title"], top_k=3, min_score=0.35, user_id=user_id):
                if result.get("source") == "auto" and result.get("user_id") == user_id:
                    existing_match = result
                    break
        except Exception:
            existing_match = None

        if existing_match:
            knowledge_service.update_document(
                existing_match["id"],
                title=candidate["title"],
                content=candidate["content"],
                tags=candidate["tags"],
            )
            logger.info("Updated auto-learned memory %s for user %s", existing_match["id"], user_id)
        else:
            knowledge_service.add_document(
                candidate["title"], candidate["content"],
                tags=candidate["tags"], source="auto", user_id=user_id,
            )
            logger.info("Saved new auto-learned memory for user %s: %s", user_id, candidate["title"])
    except Exception:
        logger.warning("learn_from_exchange failed for user %s", user_id, exc_info=True)


def learn_from_exchange_async(user_message, assistant_response, user_id):
    _thr.Thread(
        target=learn_from_exchange,
        args=(user_message, assistant_response, user_id),
        daemon=True,
    ).start()


_MENTOR_PRIVATE_SOURCES = {'email', 'calendar', 'history', 'profile'}
_MENTOR_LEARNING_HINT_TERMS = (
    'hoc hoi', 'tu hoc', 'trau doi', 'dan anh', 'cai thien', 'rut kinh nghiem',
    'learn from', 'self learn', 'improve', 'mentor', 'critique',
)
_MENTOR_ACTION_INTENTS = (
    'email.', 'schedule.', 'calendar.', 'overview.', 'settings.',
    'history.', 'knowledge.',
)


def _parse_mentor_providers():
    aliases = {
        'chatgpt': 'openai',
        'gpt': 'openai',
        'openai': 'openai',
        'gemini': 'gemini',
        'google': 'gemini',
        'claude': 'claude',
        'anthropic': 'claude',
        'openrouter': 'openrouter',
        'mistral': 'mistral',
        'ollama': 'ollama',
    }
    wanted = []
    for raw in str(getattr(Config, 'AI_MENTOR_PROVIDERS', '') or '').split(','):
        provider = aliases.get(raw.strip().lower())
        if provider and provider not in wanted:
            wanted.append(provider)
    return wanted


def _mentor_learning_allowed(user_message, user_id, intent_result=None, workspace_sources=None):
    if not getattr(Config, 'AI_MENTOR_LEARNING_ENABLED', True):
        return False
    if not user_id or user_id == 'default':
        return False
    if len((user_message or '').strip()) < int(getattr(Config, 'AI_MENTOR_MIN_MESSAGE_CHARS', 18)):
        return False
    if not getattr(ai_service, 'configured_providers', None):
        return False

    sources = set(workspace_sources or [])
    if sources and sources <= {'time'}:
        return False
    has_private_context = bool(sources & _MENTOR_PRIVATE_SOURCES)
    if has_private_context and not getattr(Config, 'AI_MENTOR_ALLOW_PRIVATE_CONTEXT', False):
        return False

    normalized = _normalize_intent_text(user_message)
    if any(term in normalized for term in _MENTOR_LEARNING_HINT_TERMS):
        return True

    intent = (intent_result or {}).get('intent') or 'chat.freeform'
    if any(intent.startswith(prefix) for prefix in _MENTOR_ACTION_INTENTS):
        return True
    if sources & {'knowledge', 'internet'}:
        return True
    return False


def _select_mentor_providers(primary_provider=None):
    configured = set(getattr(ai_service, 'configured_providers', []) or [])
    if not configured:
        return []
    max_providers = max(1, min(int(getattr(Config, 'AI_MENTOR_MAX_PROVIDERS', 2)), 4))
    preferred = _parse_mentor_providers()
    candidates = [provider for provider in preferred if provider in configured]
    for provider in getattr(ai_service, 'configured_providers', []) or []:
        if provider not in candidates:
            candidates.append(provider)

    primary = (primary_provider or '').strip().lower()
    if primary in candidates and len(candidates) > 1:
        candidates = [provider for provider in candidates if provider != primary] + [primary]

    healthy = []
    for provider in candidates:
        try:
            if ai_service._is_provider_healthy(provider):
                healthy.append(provider)
        except Exception:
            continue
    return healthy[:max_providers]


def _build_mentor_prompt(user_message, assistant_response, intent_result=None, workspace_sources=None):
    intent = (intent_result or {}).get('intent') or 'chat.freeform'
    confidence = (intent_result or {}).get('confidence')
    sources = ', '.join(sorted(set(workspace_sources or []))) or 'none'
    return [
        {
            "role": "system",
            "content": (
                "You are a senior AI mentor reviewing Bob, a FlowMate workspace agent. "
                "Your job is to extract at most ONE durable process lesson that would help Bob handle "
                "future information-processing or action-planning tasks better. "
                "Do not copy private details, names, emails, calendar contents, or one-off facts. "
                "Generalize into a reusable rule, checklist, risk reminder, or action policy. "
                "Return only JSON, no markdown: "
                '{"should_learn": true/false, "title": "<short>", "content": "<reusable lesson, 1-3 sentences>", '
                '"tags": "<comma-separated>", "confidence": 0.0-1.0}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Intent: {intent}\n"
                f"Confidence: {confidence}\n"
                f"Workspace sources used: {sources}\n\n"
                f"User request:\n{_truncate_for_mentor(user_message, 900)}\n\n"
                f"Bob response/action:\n{_truncate_for_mentor(assistant_response, 1200)}\n\n"
                "Extract a durable improvement lesson only if this turn teaches a reusable workflow, "
                "reasoning, safety, source-use, or action-confirmation pattern."
            ),
        },
    ]


def _truncate_for_mentor(value, limit):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(' ', 1)[0].strip() + '...'


def _mentor_candidate_from_raw(raw):
    data = _parse_memory_json(raw)
    if not data or not data.get('should_learn'):
        return None
    try:
        confidence = float(data.get('confidence', 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.70:
        return None

    title = _redact_mentor_text(str(data.get('title') or '').strip())[:150]
    content = _redact_mentor_text(str(data.get('content') or '').strip())[:700]
    tags = str(data.get('tags') or '').strip()[:220]
    if not title or not content:
        return None
    return {'title': title, 'content': content, 'tags': tags, 'confidence': confidence}


def _redact_mentor_text(value):
    text = str(value or '')
    text = re.sub(r'[\w.+-]+@[\w.-]+\.\w+', '[email]', text)
    text = re.sub(r'\b(?:\+?\d[\d\s().-]{7,}\d)\b', '[phone]', text)
    return text


def _save_mentor_lesson(candidate, user_id, provider):
    title = f"AI mentor lesson: {candidate['title']}"
    tags = ','.join(
        part.strip()
        for part in f"mentor,ai-peer,{provider},{candidate.get('tags') or ''}".split(',')
        if part.strip()
    )[:240]
    content = (
        f"Mentor provider: {provider}\n"
        f"Confidence: {candidate.get('confidence', 0):.2f}\n"
        f"Lesson: {candidate['content']}"
    )

    existing_match = None
    try:
        for result in knowledge_service.search(title, top_k=5, min_score=0.38, user_id=user_id):
            if result.get("source") == "mentor" and result.get("user_id") == user_id:
                existing_match = result
                break
    except Exception:
        existing_match = None

    if existing_match:
        knowledge_service.update_document(
            existing_match["id"],
            title=title,
            content=content,
            tags=tags,
        )
    else:
        knowledge_service.add_document(
            title,
            content,
            tags=tags,
            source="mentor",
            user_id=user_id,
        )


def learn_from_mentors(user_message, assistant_response, user_id, intent_result=None, workspace_sources=None, primary_provider=None, db_path=None):
    try:
        if not _mentor_learning_allowed(
            user_message,
            user_id,
            intent_result=intent_result,
            workspace_sources=workspace_sources,
        ):
            return

        providers = _select_mentor_providers(primary_provider=primary_provider)
        if not providers:
            return
        if not _learning_quota_available(
            user_id,
            db_path,
            'mentor',
            getattr(Config, 'AI_MENTOR_LEARNING_MAX_PER_DAY', 6),
        ):
            return

        messages = _build_mentor_prompt(
            user_message,
            assistant_response,
            intent_result=intent_result,
            workspace_sources=workspace_sources,
        )
        max_tokens = int(getattr(Config, 'AI_MENTOR_MAX_TOKENS', 260))
        saved = 0
        for provider in providers:
            try:
                raw = ai_service.generate_with_provider(
                    provider,
                    messages,
                    max_tokens=max_tokens,
                    task='analyze',
                )
                candidate = _mentor_candidate_from_raw(raw)
                if not candidate:
                    continue
                _save_mentor_lesson(candidate, user_id, provider)
                saved += 1
                if saved >= 1:
                    break
            except Exception:
                logger.info("AI mentor provider %s did not produce a lesson", provider, exc_info=True)
    except Exception:
        logger.warning("learn_from_mentors failed for user %s", user_id, exc_info=True)


def learn_from_mentors_async(user_message, assistant_response, user_id, intent_result=None, workspace_sources=None, primary_provider=None, db_path=None):
    _thr.Thread(
        target=learn_from_mentors,
        args=(user_message, assistant_response, user_id, intent_result, workspace_sources, primary_provider, db_path),
        daemon=True,
    ).start()


def _capability_prompt_lines(agent_capabilities):
    lines = []
    for item in agent_capabilities:
        confirmation = 'requires confirmation' if item.get('confirmation_required') else 'read/analysis'
        lines.append(
            f"- {item['id']}: {item['description']} ({confirmation}; refresh: {', '.join(item.get('refresh_targets') or [])})"
        )
    return "\n".join(lines)


def _build_agent_system_prompt(mode_prompt, agent_capabilities):
    return (
        "You are Bob, the AI agent inside FlowMate -- a workspace agent for email, "
        "calendar, schedules, history, and user settings. If asked your name, say Bob. "
        "Never mention which underlying AI provider or model powers you. " + mode_prompt
        + " The user may write in Vietnamese or English. Detect the language of "
        "their latest message and answer in that same language; if a message mixes "
        "both, default to Vietnamese. Switch language immediately if the user "
        "explicitly asks you to. "
        "Operate like an agent: identify the user's goal, inspect available workspace context, "
        "decide the next best action, and produce a useful result. "
        "When a supported direct action is needed, rely on the app tools/orchestrator instead of pretending. "
        "For sensitive or persistent actions such as creating schedules, changing settings, sending messages, "
        "or modifying external data, ask for or respect explicit confirmation before claiming completion. "
        "Use only provided workspace context for facts about the user's email, calendar, history, or account. "
        "When INTERNET RESEARCH context is provided, treat it as public web evidence, cite the relevant title "
        "or URL for external facts, and distinguish it from private workspace data. "
        "If mentor-learned knowledge appears in context, use it as a process guideline, not as a factual claim "
        "about the user's private data or as permission to skip confirmation. "
        "If data is missing, say exactly what is missing and give the smallest useful next step. "
        "Do not invent senders, dates, deadlines, meetings, completed actions, or external facts. "
        "Classify useful information as meetings, deadlines, tasks, reminders, important information, or low priority. "
        "Keep responses concise, clear, action-focused, and include a next action when helpful. "
        "Your trained capabilities are:\n"
        + _capability_prompt_lines(agent_capabilities)
    )


def extract_schedule_from_response(response, user_message):
    """
    Detect if AI response contains scheduling information
    Returns dict with schedule data or None
    """
    # Previously we gated schedule extraction on explicit keywords.
    # Remove keyword gating so AI can decide from the prompt/response when to create a schedule.
    combined_text = (user_message + ' ' + response).lower()

    # Try to extract schedule details
    schedule_info = {
        'title': '',
        'description': response,
        'start_time': None,
        'attendees': []
    }

    # Extract title (first meaningful part of response or user message)
    if 'lịch hẹn:' in response.lower():
        title_match = re.search(r'lịch hẹn:\s*([^\n]+)', response, re.IGNORECASE)
        if title_match:
            schedule_info['title'] = title_match.group(1).strip()[:100]

    if not schedule_info['title']:
        # Use first few words from user message
        words = user_message.split()[:5]
        schedule_info['title'] = ' '.join(words)[:100]

    now = datetime.now()
    start_time = None

    # Parse explicit date first: dd/mm/yyyy or dd-mm-yyyy
    date_match = re.search(r'(\d{1,4})[/-](\d{1,2})[/-](\d{1,4})', combined_text)
    date_value = None
    if date_match:
        g1 = date_match.group(1)
        g2 = date_match.group(2)
        g3 = date_match.group(3)
        # Support formats: DD/MM/YYYY or YYYY-MM-DD
        try:
            if len(g1) == 4:
                # YYYY-MM-DD
                year = int(g1)
                month = int(g2)
                day = int(g3)
            else:
                # DD/MM/YYYY or D/M/YY
                day = int(g1)
                month = int(g2)
                year = int(g3)

            if year < 100:
                year += 2000

            date_value = datetime(year, month, day).date()
        except Exception:
            date_value = None
    elif 'ngày mai' in combined_text or 'tomorrow' in combined_text:
        date_value = (now + timedelta(days=1)).date()
    elif 'tuần sau' in combined_text or 'next week' in combined_text:
        date_value = (now + timedelta(weeks=1)).date()
    elif 'hôm nay' in combined_text or 'today' in combined_text:
        date_value = now.date()

    # Parse time variants: HH:MM, 10h, 10h30, 10 giờ
    time_value = None
    time_match = re.search(r'(?<!\d)(\d{1,2})[:h](\d{2})(?!\d)', combined_text)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            time_value = datetime.strptime(f"{hour:02d}:{minute:02d}", '%H:%M').time()
    else:
        hour_only_match = re.search(r'(?<!\d)(\d{1,2})\s*(giờ|h)(?!\d)', combined_text)
        if hour_only_match:
            hour = int(hour_only_match.group(1))
            if 0 <= hour <= 23:
                time_value = datetime.strptime(f"{hour:02d}:00", '%H:%M').time()

    # Combine parsed date/time with sensible defaults
    if date_value and time_value:
        start_time = datetime.combine(date_value, time_value)
    elif date_value:
        start_time = datetime.combine(date_value, datetime.strptime('09:00', '%H:%M').time())
    elif time_value:
        start_time = datetime.combine(now.date(), time_value)
    else:
        # Default to tomorrow at current time if no clear temporal signal
        start_time = now + timedelta(days=1)

    schedule_info['start_time'] = start_time.isoformat()

    # Extract email addresses (attendees)
    emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', combined_text)
    schedule_info['attendees'] = list(set(emails))  # Remove duplicates

    return schedule_info if schedule_info['title'] else None


_REPLY_NEEDED_KEYWORDS = (
    'vui long', 'xac nhan', 'phan hoi', 'rsvp', 'please', 'could you',
    'confirm', 'reply', 'respond',
)


def _email_needs_reply(email):
    """Heuristic: does this email look like it's waiting on a reply?"""
    text = ' '.join([
        str(email.get('subject', '') or ''),
        str(email.get('snippet', '') or ''),
        str(email.get('body', '') or ''),
    ])
    if '?' in text:
        return True
    normalized = _normalize_intent_text(text)
    return any(keyword in normalized for keyword in _REPLY_NEEDED_KEYWORDS)


def _build_draft_reply_suggestion(email):
    body = email.get('body') or email.get('snippet') or ''
    context = (
        f"From: {email.get('sender', 'Unknown')}\n"
        f"Subject: {email.get('subject', '')}\n\n"
        f"{body[:800]}"
    )
    return {
        'type': 'draft_reply',
        'label': f"Soạn trả lời: {email.get('subject') or '(Không có tiêu đề)'}",
        'email_id': email.get('id'),
        'context': context,
    }


def _wrap_direct_result(direct_result, ctx):
    """Shared wrapping for intents handled by IntentOrchestrator.execute_direct()
    (history.list, settings.update_mode, and schedule.create's "not yet
    confirmed" sub-case). Returns None when execute_direct itself returned
    None, signalling the caller to fall through to FreeformChatAgent --
    mirrors today's `if direct_result and intent in {...}:` fallthrough."""
    if not direct_result:
        return None
    return AgentResult(
        response=direct_result.get('response') or '',
        workspace_sources=direct_result.get('workspace_sources') or [],
        refresh_targets=direct_result.get('refresh_targets') or ctx.refresh_targets,
        schedule_suggestion=direct_result.get('schedule_suggestion'),
        action_type=direct_result.get('action_type') or 'chat',
        action='Thực hiện hành động trực tiếp',
    )


class EmailLatestSummaryAgent:
    """AGENT_CAPABILITIES: roughly 'email.inbox_triage' / 'overview.daily_brief'."""

    def handle(self, ctx):
        try:
            requested_count = int(
                (ctx.intent_result.get('entities') or {}).get('count')
                or _latest_email_count(ctx.user_message)
            )
            query_override = _query_override_from_entities(ctx.intent_result.get('entities'))
            response, source_emails = _summarize_latest_emails(ctx.user_id, requested_count, query_override=query_override)
            source_email = source_emails[0]
            suggested_actions = [
                _build_draft_reply_suggestion(email)
                for email in source_emails
                if _email_needs_reply(email)
            ]
            return AgentResult(
                response=response,
                provider=ai_service.last_provider_used,
                demo_mode=ai_service.last_provider_used == 'demo',
                suggested_actions=suggested_actions,
                workspace_sources=['email'],
                refresh_targets=ctx.refresh_targets,
                ai_used=True,
                action='Tóm tắt email mới nhất',
                email_source={
                    'id': source_email.get('id'),
                    'sender': source_email.get('sender'),
                    'subject': source_email.get('subject'),
                    'date': source_email.get('date')
                },
                email_sources=[{
                    'id': email.get('id'),
                    'sender': email.get('sender'),
                    'subject': email.get('subject'),
                    'date': email.get('date')
                } for email in source_emails],
            )
        except Exception as e:
            logger.exception("Failed to summarize latest Gmail messages for user %s", ctx.user_id)
            response = f"Khong the lay email gan nhat tu Gmail: {e}"
            return AgentResult(
                response=response,
                refresh_targets=ctx.refresh_targets,
                action='Không lấy được Gmail',
            )


class ScheduleCreateAgent:
    """AGENT_CAPABILITIES: roughly 'schedule.manage'. Owns both sub-paths
    that today live in two separate locations in chat.py: the "already
    confirmed" create flow, and the "not yet confirmed" propose flow
    (delegated to IntentOrchestrator.execute_direct via _wrap_direct_result)."""

    def handle(self, ctx):
        if ctx.client_confirm or ctx.schedule_override:
            return self._handle_confirmed(ctx)
        direct_result = intent_orchestrator.execute_direct(ctx.intent_result, ctx.user_id, ctx.db_path)
        return _wrap_direct_result(direct_result, ctx)

    def _handle_confirmed(self, ctx):
        schedule_created = None
        response = "Minh chua tao duoc lich vi thieu ngay/gio bat dau."
        try:
            schedule_created = intent_orchestrator.create_schedule_from_intent(
                ctx.intent_result,
                ctx.schedule_override,
                ctx.db_path
            )
            if schedule_created:
                response = f"Da tao lich: {schedule_created.get('title')} luc {schedule_created.get('start_time')}."
                History.create(
                    f"Tao lich hen: {schedule_created.get('title')}",
                    "Lich hen duoc tao tu xac nhan cua nguoi dung",
                    action_type='schedule_created',
                    related_id=schedule_created.get('id'),
                    db_path=ctx.db_path
                )
        except Exception as e:
            logger.exception("Failed to create schedule through intent orchestrator")
            response = f"Khong the tao lich: {e}"

        return AgentResult(
            response=response,
            workspace_sources=['calendar'],
            refresh_targets=['schedule', 'history'],
            schedule_created=schedule_created,
            schedule_suggestion=None if schedule_created else (ctx.intent_result.get('entities') or {}).get('schedule'),
            action='Tạo lịch sau xác nhận' if schedule_created else 'Cần bổ sung thông tin lịch',
        )


def _format_match_list(matches, verb):
    lines = [f"Mình thấy vài lịch khớp, bạn muốn {verb} cái nào? Hãy nói rõ hơn nhé."]
    for index, sched in enumerate(matches[:5], start=1):
        lines.append(f"{index}. {sched.get('title')} - {sched.get('start_time')}")
    return "\n".join(lines)


class ScheduleUpdateAgent:
    """AGENT_CAPABILITIES: roughly 'schedule.manage'. Only handles new
    start_time/end_time/attendees from the message -- deliberately does not
    attempt to infer a new title from freeform text (too ambiguous, risks
    silently overwriting the wrong field)."""

    def handle(self, ctx):
        if ctx.client_confirm and (ctx.schedule_override or {}).get('schedule_id'):
            return self._handle_confirmed(ctx)
        return self._propose(ctx)

    def _propose(self, ctx):
        # Prefer the AI-classified new time (handles paraphrases/relative
        # dates like "thu 5 tuan sau" that the regex fallback can't) when
        # the AI-assisted path actually ran; otherwise fall back to the same
        # regex-based extraction the rule-based path always uses.
        ai_new_values = (ctx.intent_result.get('entities') or {}).get('new_values')
        if ai_new_values and (ai_new_values.get('start_time') or ai_new_values.get('end_time')):
            new_values = ai_new_values
        else:
            new_values = intent_orchestrator.extract_schedule(ctx.user_message)
        has_change = bool(new_values.get('start_time') or new_values.get('end_time'))
        if not has_change:
            return AgentResult(
                response="Mình chưa hiểu bạn muốn đổi sang ngày/giờ nào, bạn nói rõ hơn giúp mình nhé.",
                action='Cần thêm thông tin để sửa lịch',
            )
        matches = _find_matching_schedules(ctx.user_message, ctx.db_path)
        if not matches:
            return AgentResult(
                response="Mình không tìm thấy lịch hẹn phù hợp trong 14 ngày tới. Bạn cho mình biết rõ tên lịch hẹn nhé.",
                workspace_sources=['calendar'],
                action='Không tìm thấy lịch cần sửa',
            )
        if len(matches) > 1:
            return AgentResult(
                response=_format_match_list(matches, 'sửa'),
                workspace_sources=['calendar'],
                action='Nhiều lịch khớp, cần xác định rõ',
            )
        sched = matches[0]
        suggestion = {
            'action': 'update',
            'schedule_id': sched.get('id'),
            'title': sched.get('title'),
            'start_time': sched.get('start_time'),
            'end_time': sched.get('end_time'),
            'new_start_time': new_values.get('start_time'),
            'new_end_time': new_values.get('end_time'),
        }
        return AgentResult(
            response=(
                f"Mình tìm thấy lịch '{sched.get('title')}' lúc {sched.get('start_time')}. "
                "Xác nhận đổi sang thời gian mới?"
            ),
            schedule_suggestion=suggestion,
            workspace_sources=['calendar'],
            action='Đề xuất sửa lịch cần xác nhận',
        )

    def _handle_confirmed(self, ctx):
        schedule_id = ctx.schedule_override.get('schedule_id')
        previous = Schedule.get_by_id(schedule_id, db_path=ctx.db_path)
        if not previous:
            return AgentResult(
                response="Lịch hẹn này không còn tồn tại, có thể đã bị xóa trước đó.",
                workspace_sources=['calendar'],
                action='Lịch không còn tồn tại',
            )

        update_data = {}
        if ctx.schedule_override.get('new_start_time'):
            update_data['start_time'] = ctx.schedule_override['new_start_time']
        if ctx.schedule_override.get('new_end_time'):
            update_data['end_time'] = ctx.schedule_override['new_end_time']

        if not update_data:
            return AgentResult(
                response="Không có thay đổi nào để cập nhật.",
                workspace_sources=['calendar'],
                action='Không có thay đổi',
            )

        try:
            Schedule.update(schedule_id, db_path=ctx.db_path, **update_data)
            _clear_schedule_cache(ctx.db_path)
            _clear_overview_cache(ctx.user_id)
            updated = Schedule.get_by_id(schedule_id, db_path=ctx.db_path)
            _sync_schedule_to_calendar_async(ctx.user_id, schedule_id, ctx.db_path)
            _prune_stale_duplicate_after_move_async(ctx.user_id, ctx.db_path, schedule_id, previous, updated)
            History.create(
                f"Chinh sua lich hen: {previous.get('title')}",
                f"Cap nhat: {', '.join(update_data.keys())}",
                action_type='schedule_updated',
                related_id=schedule_id,
                db_path=ctx.db_path,
            )
            response = f"Đã cập nhật lịch '{updated.get('title')}' sang {updated.get('start_time')}."
        except Exception as e:
            logger.exception("Failed to update schedule %s via chat", schedule_id)
            response = f"Không thể cập nhật lịch: {e}"

        return AgentResult(
            response=response,
            workspace_sources=['calendar'],
            refresh_targets=['schedule', 'history'],
            action='Đã cập nhật lịch',
        )


class ScheduleDeleteAgent:
    """AGENT_CAPABILITIES: roughly 'schedule.manage'."""

    def handle(self, ctx):
        if ctx.client_confirm and (ctx.schedule_override or {}).get('schedule_id'):
            return self._handle_confirmed(ctx)
        return self._propose(ctx)

    def _propose(self, ctx):
        matches = _find_matching_schedules(ctx.user_message, ctx.db_path)
        if not matches:
            return AgentResult(
                response="Mình không tìm thấy lịch hẹn phù hợp để xóa trong 14 ngày tới.",
                workspace_sources=['calendar'],
                action='Không tìm thấy lịch cần xóa',
            )
        if len(matches) > 1:
            return AgentResult(
                response=_format_match_list(matches, 'xóa'),
                workspace_sources=['calendar'],
                action='Nhiều lịch khớp, cần xác định rõ',
            )
        sched = matches[0]
        suggestion = {
            'action': 'delete',
            'schedule_id': sched.get('id'),
            'title': sched.get('title'),
            'start_time': sched.get('start_time'),
            'end_time': sched.get('end_time'),
        }
        return AgentResult(
            response=f"Mình tìm thấy lịch '{sched.get('title')}' lúc {sched.get('start_time')}. Xác nhận xóa?",
            schedule_suggestion=suggestion,
            workspace_sources=['calendar'],
            action='Đề xuất xóa lịch cần xác nhận',
        )

    def _handle_confirmed(self, ctx):
        schedule_id = ctx.schedule_override.get('schedule_id')
        schedule = Schedule.get_by_id(schedule_id, db_path=ctx.db_path)
        if not schedule:
            return AgentResult(
                response="Lịch hẹn này không còn tồn tại, có thể đã bị xóa trước đó.",
                workspace_sources=['calendar'],
                action='Lịch không còn tồn tại',
            )

        try:
            calendar_event_id = schedule.get('calendar_event_id')
            Schedule.delete(schedule_id, db_path=ctx.db_path)
            _clear_schedule_cache(ctx.db_path)
            _clear_overview_cache(ctx.user_id)
            if calendar_event_id:
                _delete_calendar_event_async(ctx.user_id, calendar_event_id, ctx.db_path)
            History.create(
                f"Xoa lich hen: {schedule.get('title')}",
                "Lich hen da bi xoa qua chat",
                action_type='schedule_deleted',
                related_id=schedule_id,
                db_path=ctx.db_path,
            )
            response = f"Đã xóa lịch '{schedule.get('title')}'."
        except Exception as e:
            logger.exception("Failed to delete schedule %s via chat", schedule_id)
            response = f"Không thể xóa lịch: {e}"

        return AgentResult(
            response=response,
            workspace_sources=['calendar'],
            refresh_targets=['schedule', 'history'],
            action='Đã xóa lịch',
        )


class ScheduleListAgent:
    """AGENT_CAPABILITIES: roughly 'calendar.sync'."""

    def handle(self, ctx):
        window_override = _window_override_from_entities(ctx.intent_result.get('entities'))
        response = _direct_schedule_list_response(
            ctx.user_message, ctx.user_id, ctx.db_path, window_override=window_override
        )
        return AgentResult(
            response=response,
            workspace_sources=['calendar'],
            refresh_targets=ctx.refresh_targets,
            action='Liệt kê lịch từ dữ liệu thật',
        )


class EmailSearchAgent:
    """AGENT_CAPABILITIES: roughly 'email.inbox_triage'."""

    def handle(self, ctx):
        query_override = _query_override_from_entities(ctx.intent_result.get('entities'))
        response = _direct_email_search_response(ctx.user_message, ctx.user_id, query_override=query_override)
        return AgentResult(
            response=response,
            workspace_sources=['email'],
            refresh_targets=ctx.refresh_targets,
            action='Tìm email trong Gmail',
        )


def _mark_emails(ctx, read):
    token_file = get_user_token_file(ctx.user_id)
    if not token_file or not os.path.exists(token_file):
        return AgentResult(response="Gmail chưa được kết nối cho tài khoản này.", action='Gmail chưa kết nối')

    query_override = _query_override_from_entities(ctx.intent_result.get('entities'))
    query, include_read = query_override or _email_lookup_query(ctx.user_message)
    service = get_cached_gmail_service(token_file)
    emails = service.get_emails(max_results=10, query=query, include_read=True)
    if not emails:
        return AgentResult(
            response="Mình không tìm thấy email phù hợp trong Gmail theo dữ liệu hiện tại.",
            workspace_sources=['email'],
            action='Không tìm thấy email',
        )

    targets = emails[:3]
    marked = []
    for email in targets:
        try:
            if read:
                service.mark_as_read(email.get('id'))
            else:
                service.mark_as_unread(email.get('id'))
            marked.append(email)
        except Exception:
            logger.exception("Failed to mark email %s as %s", email.get('id'), 'read' if read else 'unread')

    from routes.email import _clear_email_list_cache
    _clear_email_list_cache(ctx.user_id)

    label = 'đã đọc' if read else 'chưa đọc'
    action_type = 'chat'
    for email in marked:
        History.create(
            f"Đánh dấu email {label}: {email.get('subject') or '(không có tiêu đề)'}",
            "Đánh dấu qua chat",
            action_type=action_type,
            db_path=ctx.db_path,
        )

    if not marked:
        return AgentResult(
            response="Mình tìm thấy email nhưng không thể đánh dấu được, bạn thử lại sau nhé.",
            workspace_sources=['email'],
            action='Không đánh dấu được email',
        )

    titles = ", ".join(e.get('subject') or '(không có tiêu đề)' for e in marked)
    extra = (
        f" (còn {len(emails) - len(targets)} email khác khớp, bạn nói rõ hơn để mình xử lý tiếp nếu cần)"
        if len(emails) > len(targets) else ""
    )
    return AgentResult(
        response=f"Đã đánh dấu {label}: {titles}.{extra}",
        workspace_sources=['email'],
        refresh_targets=['email', 'overview', 'history'],
        action=f"Đánh dấu email {label}",
    )


class EmailMarkReadAgent:
    """AGENT_CAPABILITIES: roughly 'email.inbox_triage'. No confirmation
    needed -- marking read/unread is low-risk and trivially reversible,
    unlike schedule mutation or sending email."""

    def handle(self, ctx):
        return _mark_emails(ctx, read=True)


class EmailMarkUnreadAgent:
    """AGENT_CAPABILITIES: roughly 'email.inbox_triage'."""

    def handle(self, ctx):
        return _mark_emails(ctx, read=False)


class HistoryListAgent:
    """AGENT_CAPABILITIES: roughly 'history.audit'."""

    def handle(self, ctx):
        direct_result = intent_orchestrator.execute_direct(ctx.intent_result, ctx.user_id, ctx.db_path)
        return _wrap_direct_result(direct_result, ctx)


class SettingsUpdateModeAgent:
    """AGENT_CAPABILITIES: roughly 'settings.profile_mode'. Can return None
    (when the mode entity couldn't be resolved), signalling the caller to
    fall through to FreeformChatAgent -- mirrors today's behavior exactly."""

    def handle(self, ctx):
        direct_result = intent_orchestrator.execute_direct(ctx.intent_result, ctx.user_id, ctx.db_path)
        return _wrap_direct_result(direct_result, ctx)


class DayPlanSuggestAgent:
    """AGENT_CAPABILITIES: roughly 'schedule.manage'. Suggests calendar time
    slots for the activities listed in the chat message, reusing the exact
    same day-plan engine (_build_suggested_day_plan) as the Overview
    quick-add box -- same per-activity time/duration profiles, same
    conflict-aware slot search against existing schedules. Deliberately
    does NOT create anything itself: creating schedules always needs
    explicit confirmation, and the chat UI lets the user review/edit the
    suggestion and apply it through the existing, already-tested
    /schedule/plan-day/apply endpoint -- the same confirm-before-create
    path Overview already uses, instead of building a second one in chat."""

    def handle(self, ctx):
        date_value = datetime.now(LOCAL_TZ).date().isoformat()
        plan = _build_suggested_day_plan(ctx.user_id, ctx.db_path, ctx.user_message, date_value)
        if not plan:
            return None

        lines = [f"Mình gợi ý khung giờ sau cho {len(plan['items'])} hoạt động hôm nay, bạn xem và bấm áp dụng nếu hợp lý:"]
        for item in plan['items']:
            time_label = _format_schedule_response_time(item.get('start_time'), item.get('end_time'))
            lines.append(f"- {item.get('title')}: {time_label}")

        return AgentResult(
            response="\n".join(lines),
            day_plan_suggestion=plan,
            workspace_sources=['calendar'],
            refresh_targets=ctx.refresh_targets,
            action='Đề xuất lịch theo hoạt động, cần xác nhận',
        )


_CHECKLIST_PRIORITY_SCORE = {'high': 95, 'normal': 60, 'low': 30}
_CHECKLIST_PRIORITY_REASON = {
    'high': 'Việc gấp/quan trọng theo yêu cầu của bạn.',
    'normal': 'Thêm từ yêu cầu trong chat.',
    'low': 'Không gấp, có thể làm khi rảnh.',
}


class ChecklistCreateAgent:
    """AGENT_CAPABILITIES: roughly 'overview.daily_brief'. Adds the
    activities listed in the chat message straight to today's checklist --
    same no-confirmation behavior as the existing quick-add checklist path,
    since checklist items are low-risk/reversible (no calendar side effect),
    unlike schedule.create which always proposes first. Each item carries
    its own urgency (extracted per-item by the intent orchestrator, not one
    flat priority for the whole list) so wording like 'gap'/'khong gap' in
    the original message actually changes where it lands in the checklist."""

    def handle(self, ctx):
        raw_items = (ctx.intent_result.get('entities') or {}).get('items') or []
        normalized_items = []
        for entry in raw_items:
            if isinstance(entry, dict):
                title = str(entry.get('title') or '').strip()
                priority = str(entry.get('priority') or 'normal').strip().lower()
            else:
                title = str(entry or '').strip()
                priority = 'normal'
            if not title:
                continue
            if priority not in _CHECKLIST_PRIORITY_SCORE:
                priority = 'normal'
            normalized_items.append((title, priority))
        if not normalized_items:
            return None

        date_value = datetime.now(LOCAL_TZ).date().isoformat()
        cache_key = _checklist_cache_key(ctx.user_id, date_value)
        cached = Cache.get(cache_key, db_path=ctx.db_path)
        payload = _normalize_checklist_payload(cached)
        existing_titles = {entry['title'].strip().lower() for entry in payload['custom_items']}

        added = []
        for title, priority in normalized_items:
            if title.lower() in existing_titles:
                continue
            payload['custom_items'].append({
                'id': f"manual:{uuid.uuid4().hex[:12]}",
                'title': title[:240],
                'completed': False,
                'created_at': datetime.utcnow().isoformat(),
                'source': 'manual',
                'item_type': 'task',
                'due_date': date_value,
                'due_at': '',
                'ai_reason': _CHECKLIST_PRIORITY_REASON[priority],
                'priority_score': _CHECKLIST_PRIORITY_SCORE[priority],
                'pinned': priority == 'high',
            })
            existing_titles.add(title.lower())
            added.append(title)

        if not added:
            return AgentResult(
                response="Các việc này đã có trong checklist hôm nay rồi.",
                workspace_sources=['overview'],
                refresh_targets=ctx.refresh_targets,
                action='Checklist đã có sẵn các việc này',
            )

        payload['custom_items'] = _sort_custom_items(payload['custom_items'])
        Cache.set(cache_key, payload, ttl=_CHECKLIST_CACHE_TTL_SECONDS, db_path=ctx.db_path)
        _clear_overview_cache(ctx.user_id)

        response = "Mình đã thêm vào checklist hôm nay:\n" + "\n".join(f"- {title}" for title in added)
        return AgentResult(
            response=response,
            workspace_sources=['overview'],
            refresh_targets=sorted(set(ctx.refresh_targets) | {'overview'}),
            action='Đã thêm việc vào checklist',
        )


class FreeformChatAgent:
    """AGENT_CAPABILITIES: roughly 'overview.daily_brief' / 'knowledge.lookup'
    plus the catch-all chat.freeform fallback for any other/unknown intent."""

    def handle(self, ctx):
        direct_time = _direct_current_time_response(ctx.user_message)
        if direct_time:
            return AgentResult(
                response=direct_time,
                workspace_sources=['time'],
                refresh_targets=sorted(set(ctx.refresh_targets)),
                ai_used=False,
                grounded=True,
                action='Đọc thời gian hệ thống theo UTC+7',
            )

        # Local import to avoid a circular import: chat.py imports get_agent
        # from this module, so this module can't import chat.py at module
        # load time. AGENT_CAPABILITIES only exists in chat.py.
        from routes.chat import AGENT_CAPABILITIES

        messages = [{
            "role": "system",
            "content": _build_agent_system_prompt(ctx.mode_prompt, AGENT_CAPABILITIES)
        }]

        workspace_sources = set()
        workspace_context = ''
        try:
            workspace_sources, workspace_context = _build_workspace_context(
                ctx.user_message,
                ctx.user_id,
                ctx.db_path
            )
        except Exception:
            logger.exception("Failed to build workspace context for user %s", ctx.user_id)

        if not workspace_sources:
            recent_history = History.get_recent(limit=8, db_path=ctx.db_path, chat_session_id=ctx.chat_session_id)
            for record in reversed(recent_history):
                if record.get('action_type') != 'chat':
                    continue

                prev_user = (record.get('user_message') or '').strip()
                prev_assistant = (record.get('assistant_response') or '').strip()
                if prev_user:
                    messages.append({"role": "user", "content": prev_user})
                if prev_assistant:
                    messages.append({"role": "assistant", "content": prev_assistant})

        if workspace_context:
            messages.append({
                "role": "user",
                "preserve_context": True,
                "content": (
                    "DỮ LIỆU WORKSPACE THỰC TẾ\n"
                    "Chỉ dùng dữ liệu dưới đây để trả lời câu hỏi tiếp theo. "
                    "Mục INTERNET RESEARCH (nếu có) là dữ liệu web công khai và phải kèm nguồn khi dùng. "
                    "Không bịa thêm dữ liệu không có trong context. "
                    "Nếu context không đủ, nói rõ thiếu dữ liệu nào.\n\n"
                    + workspace_context
                )
            })

        messages.append({
            "role": "user",
            "content": ctx.user_message
        })

        # Generate response
        response = ai_service.generate_response(messages, task=ctx.task, user_id=ctx.user_id)

        # Auto-detect schedule suggestion from AI response
        schedule_info = extract_schedule_from_response(response, ctx.user_message)
        schedule_created = None

        # Check if client asked to confirm/create the schedule now
        if schedule_info:
            if ctx.client_confirm or ctx.schedule_override:
                # Use override values from client when provided, otherwise use detected info
                payload = {
                    'title': ctx.schedule_override.get('title') or schedule_info.get('title'),
                    'description': ctx.schedule_override.get('description') or schedule_info.get('description'),
                    'start_time': ctx.schedule_override.get('start_time') or schedule_info.get('start_time'),
                    'end_time': ctx.schedule_override.get('end_time') or schedule_info.get('end_time'),
                    'attendees': ctx.schedule_override.get('attendees') or schedule_info.get('attendees')
                }
                try:
                    schedule_id = ScheduleService.create_schedule(
                        title=payload['title'],
                        description=payload['description'],
                        start_time=payload['start_time'],
                        attendees=payload.get('attendees') or [],
                        db_path=ctx.db_path
                    )

                    # Save to chat history for reference
                    History.create(
                        f"Tạo lịch hẹn: {payload['title']}",
                        f"Lịch hẹn được tạo từ xác nhận của người dùng",
                        action_type='schedule_created',
                        related_id=schedule_id,
                        db_path=ctx.db_path
                    )

                    schedule_created = {
                        'id': schedule_id,
                        'title': payload['title'],
                        'start_time': payload['start_time']
                    }

                    logger.info(f"Created schedule (confirmed): {payload['title']}")
                except Exception as e:
                    logger.error(f"Failed to create schedule on confirmation: {e}")

                # Spawn background calendar sync for created schedule
                try:
                    user_id = ctx.user_id
                    db_path = ctx.db_path

                    def _bg_sync():
                        try:
                            token_file = get_user_token_file(user_id)
                            if not token_file or not os.path.exists(token_file):
                                return
                            cal = CalendarService(token_file=token_file)
                            schedule = Schedule.get_by_id(schedule_id, db_path=db_path)
                            if not schedule:
                                return
                            if schedule.get('calendar_event_id'):
                                cal.update_event(
                                    event_id=schedule.get('calendar_event_id'),
                                    title=schedule.get('title'),
                                    description=schedule.get('description'),
                                    start_time=schedule.get('start_time'),
                                    end_time=schedule.get('end_time'),
                                    attendees=[a.strip() for a in (schedule.get('attendees') or '').split(',') if a.strip()]
                                )
                            else:
                                event_id = cal.create_event(
                                    title=schedule.get('title'),
                                    description=schedule.get('description'),
                                    start_time=schedule.get('start_time'),
                                    end_time=schedule.get('end_time'),
                                    attendees=[a.strip() for a in (schedule.get('attendees') or '').split(',') if a.strip()]
                                )
                                if event_id:
                                    Schedule.update(schedule_id, calendar_event_id=event_id, db_path=db_path)
                        except Exception:
                            pass
                    _thr.Thread(target=_bg_sync, daemon=True).start()
                except Exception:
                    pass
            else:
                # Do not create schedule automatically - return suggestion for client to confirm
                schedule_created = None

        schedule_suggestion = None
        if schedule_info and not schedule_created:
            schedule_suggestion = schedule_info

        return AgentResult(
            response=response,
            provider=ai_service.last_provider_used,
            demo_mode=ai_service.last_provider_used == 'demo',
            schedule_created=schedule_created,
            schedule_suggestion=schedule_suggestion,
            workspace_sources=sorted(workspace_sources),
            refresh_targets=sorted(set(ctx.refresh_targets)),
            ai_used=True,
            grounded=bool(workspace_sources),
            action='Đề xuất lịch cần xác nhận' if schedule_suggestion else None,
        )


_FREEFORM_AGENT = FreeformChatAgent()

_AGENT_REGISTRY = {
    'email.latest_summary': EmailLatestSummaryAgent(),
    'schedule.create': ScheduleCreateAgent(),
    'schedule.update': ScheduleUpdateAgent(),
    'schedule.delete': ScheduleDeleteAgent(),
    'schedule.list': ScheduleListAgent(),
    'email.search': EmailSearchAgent(),
    'email.mark_read': EmailMarkReadAgent(),
    'email.mark_unread': EmailMarkUnreadAgent(),
    'history.list': HistoryListAgent(),
    'settings.update_mode': SettingsUpdateModeAgent(),
    'checklist.create': ChecklistCreateAgent(),
    'schedule.suggest_plan': DayPlanSuggestAgent(),
}


def get_agent(intent):
    return _AGENT_REGISTRY.get(intent, _FREEFORM_AGENT)
