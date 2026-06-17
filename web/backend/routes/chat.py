from flask import Blueprint, request, jsonify
import os
import sys
import logging
import re
import unicodedata
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ai_service import AIService
from services.gmail_service import GmailService
from services.intent_orchestrator import IntentOrchestrator
from services.schedule_service import ScheduleService
from models.history import History
from models.schedule import Schedule
from models.user import User
from utils.user_context import get_current_user_id, get_user_db_path, get_user_token_file
from services.calendar_service import CalendarService

# Configure module logger
logger = logging.getLogger(__name__)

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')
ai_service = AIService()
intent_orchestrator = IntentOrchestrator()


def _ensure_chat_session(user_id, session_id, mode='worker', title=None):
    return History.ensure_chat_session(
        user_id=user_id,
        session_id=session_id,
        title=title,
        mode=mode,
        db_path=get_user_db_path(user_id),
    )


def _normalize_intent_text(value):
    value = unicodedata.normalize('NFD', str(value or '').lower())
    value = ''.join(char for char in value if unicodedata.category(char) != 'Mn')
    return value.replace('đ', 'd')


def _is_latest_email_summary_request(message):
    normalized = _normalize_intent_text(message)
    email_word = r'(?:e-?mails?|gmails?|mails?|thu|hop thu|inbox)'
    has_email = re.search(rf'\b{email_word}\b', normalized) is not None
    has_latest = (
        any(term in normalized for term in (
            'moi nhat', 'gan nhat', 'gan day', 'vua nhan', 'moi nhan',
            'latest', 'newest', 'most recent', 'recent',
            'just received', 'newly received', 'last received'
        ))
        or re.search(r'\blast\s+(?:e-?mails?|mails?|message|messages)\b', normalized) is not None
    )
    return has_email and has_latest


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


def _summarize_latest_emails(user_id, count=1):
    token_file = get_user_token_file(user_id)
    if not token_file or not os.path.exists(token_file):
        raise RuntimeError('Gmail chưa được kết nối cho tài khoản này.')

    service = GmailService(token_file=token_file)
    count = max(1, min(int(count or 1), 5))
    latest = service.get_emails(
        max_results=count,
        query='in:inbox',
        include_read=True
    )
    if not latest:
        raise RuntimeError('Không tìm thấy email nào trong hộp thư đến.')

    emails = []
    sections = []
    for index, metadata in enumerate(latest[:count], start=1):
        email_id = metadata.get('id')
        email = service.get_email_details(email_id, lazy=False) if email_id else None
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
    history_requested = overview or any(term in normalized for term in (
        'lich su', 'hoat dong', 'da lam gi', 'history', 'activity'
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

    emails = GmailService(token_file=token_file).get_emails(
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
            parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return parsed.astimezone()
    except (TypeError, ValueError):
        return None


def _format_calendar_context(message, user_id, db_path):
    window_start, window_end, window_label = _calendar_window(message)
    lines = [
        f"LỊCH VÀ SỰ KIỆN {window_label}",
        f"Khoảng thời gian: {window_start.date().isoformat()} đến {(window_end - timedelta(days=1)).date().isoformat()}",
    ]
    token_file = get_user_token_file(user_id)
    google_events = []
    if token_file and os.path.exists(token_file):
        google_events = CalendarService(token_file=token_file).get_events(
            max_results=50,
            time_min=window_start.isoformat(),
            time_max=window_end.isoformat()
        )

    local_schedules = Schedule.get_between(
        window_start.isoformat(),
        window_end.isoformat(),
        limit=100,
        db_path=db_path
    )

    if not google_events and not local_schedules:
        return "\n".join(lines + [f"Không có lịch hoặc sự kiện trong {window_label.lower()}."])

    seen = set()
    item_index = 1
    for event in google_events:
        fingerprint = (
            str(event.get('title') or '').strip().lower(),
            str(event.get('start') or '').strip()
        )
        seen.add(fingerprint)
        lines.extend([
            f"{item_index}. {event.get('title') or '(Không có tiêu đề)'}",
            f"   Bắt đầu: {event.get('start') or 'Không xác định'}",
            f"   Kết thúc: {event.get('end') or 'Không xác định'}",
            f"   Địa điểm: {event.get('location') or 'Không có'}",
        ])
        item_index += 1

    for schedule in local_schedules:
        fingerprint = (
            str(schedule.get('title') or '').strip().lower(),
            str(schedule.get('start_time') or '').strip()
        )
        if fingerprint in seen:
            continue
        lines.extend([
            f"{item_index}. {schedule.get('title') or '(Không có tiêu đề)'}",
            f"   Bắt đầu: {schedule.get('start_time') or 'Không xác định'}",
            f"   Kết thúc: {schedule.get('end_time') or 'Không xác định'}",
            f"   Trạng thái: {schedule.get('status') or 'pending'}",
        ])
        item_index += 1
    return "\n".join(lines)


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
    user = User.get(user_id) or {}
    return "\n".join([
        "HỒ SƠ VÀ CÀI ĐẶT",
        f"Tên: {user.get('name') or user.get('gmail_name') or 'Chưa thiết lập'}",
        f"Email: {user.get('gmail_email') or user.get('email') or 'Chưa thiết lập'}",
        f"Chế độ làm việc: {user.get('user_mode') or 'Chưa chọn'}",
        f"Gmail đã kết nối: {'Có' if user.get('gmail_connected') else 'Không'}",
    ])


def _direct_schedule_list_response(message, user_id, db_path):
    context = _format_calendar_context(message, user_id, db_path)
    return (
        context
        + "\n\nMình chỉ liệt kê dữ liệu lịch đang có trong Calendar/FlowMate, "
        "không tự suy đoán thêm sự kiện ngoài dữ liệu này."
    )


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


def _direct_email_search_response(message, user_id, limit=8):
    token_file = get_user_token_file(user_id)
    if not token_file or not os.path.exists(token_file):
        return "Gmail chưa được kết nối, nên mình chưa thể xem email thật của bạn."

    query, include_read = _email_lookup_query(message)
    emails = GmailService(token_file=token_file).get_emails(
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
    return sources, "\n\n".join(context_parts)


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


@chat_bp.route('/message', methods=['POST'])
def send_message():
    """Send message to AI assistant"""
    data = request.get_json() or {}
    user_message = data.get('message', '').strip()
    user_id = get_current_user_id(request)
    stored_user = User.get(user_id) or {}
    mode = (data.get('mode') or stored_user.get('user_mode') or 'worker').strip().lower()
    mode_prompts = {
        'student': (
            "Student Mode: prioritize assignments, class email, study deadlines, "
            "group projects, and clear study plans."
        ),
        'freelancer': (
            "Freelancer Mode: prioritize client communication, project delivery, "
            "invoices, scope, and independent workload planning."
        ),
        'creator': (
            "Creator Mode: prioritize brand communication, content calendars, campaign "
            "briefs, publishing reminders, and creative deliverables."
        ),
        'worker': (
            "Worker Mode: prioritize work email, meetings, daily tasks, follow-ups, "
            "and concise progress reports."
        ),
        'business': (
            "Business Mode: prioritize operations, executive email, team calendars, "
            "decisions, risks, and action-oriented business summaries."
        ),
        'mentor': (
            "Mentor Mode: prioritize mentee communication, guidance sessions, "
            "feedback deadlines, and progress tracking."
        ),
        'teacher': (
            "Teacher Mode: prioritize classes, curriculum, student communication, "
            "grading deadlines, and teaching follow-ups."
        )
    }
    mode_prompt = mode_prompts.get(mode, mode_prompts['worker'])
    task = (data.get('task', 'chat') or 'chat').strip().lower()
    if task not in ['chat', 'summary', 'reply', 'analyze']:
        task = 'chat'
    
    if not user_message:
        return jsonify({'error': 'Empty message'}), 400
    
    db_path = get_user_db_path(user_id)
    History.init_db(db_path=db_path)
    Schedule.init_db(db_path=db_path)
    chat_session_id = _ensure_chat_session(
        user_id,
        data.get('session_id') or data.get('chat_session_id'),
        mode=mode,
        title=user_message[:80]
    )

    def save_chat_history(user_text, assistant_text, action_type='chat', related_id=None):
        return History.create(
            user_text,
            assistant_text,
            action_type=action_type,
            related_id=related_id,
            db_path=db_path,
            chat_session_id=chat_session_id if action_type == 'chat' else None,
        )

    intent_result = intent_orchestrator.detect(user_message)
    refresh_targets = list(intent_result.get('refresh_targets') or [])

    if intent_result.get('intent') == 'email.latest_summary':
        try:
            requested_count = int((intent_result.get('entities') or {}).get('count') or _latest_email_count(user_message))
            response, source_emails = _summarize_latest_emails(user_id, requested_count)
            source_email = source_emails[0]
            save_chat_history(user_message, response)
            return jsonify({
                'success': True,
                'session_id': chat_session_id,
                'response': response,
                'provider': ai_service.last_provider_used,
                'demo_mode': ai_service.last_provider_used == 'demo',
                'schedule_created': None,
                'schedule_suggestion': None,
                'workspace_sources': ['email'],
                'intent': intent_result,
                'refresh_targets': refresh_targets,
                'email_source': {
                    'id': source_email.get('id'),
                    'sender': source_email.get('sender'),
                    'subject': source_email.get('subject'),
                    'date': source_email.get('date')
                },
                'email_sources': [{
                    'id': email.get('id'),
                    'sender': email.get('sender'),
                    'subject': email.get('subject'),
                    'date': email.get('date')
                } for email in source_emails],
                'grounded': True,
                'ai_used': True
            })
        except Exception as e:
            logger.exception("Failed to summarize latest Gmail messages for user %s", user_id)
            response = f"Khong the lay email gan nhat tu Gmail: {e}"
            save_chat_history(user_message, response)
            return jsonify({
                'success': True,
                'session_id': chat_session_id,
                'response': response,
                'provider': None,
                'demo_mode': False,
                'schedule_created': None,
                'schedule_suggestion': None,
                'intent': intent_result,
                'refresh_targets': refresh_targets,
                'grounded': True,
                'ai_used': False
            })

    client_confirm = bool(data.get('confirmed_schedule'))
    schedule_override = data.get('schedule_override') or {}
    if intent_result.get('intent') == 'schedule.create' and (client_confirm or schedule_override):
        schedule_created = None
        response = "Minh chua tao duoc lich vi thieu ngay/gio bat dau."
        try:
            schedule_created = intent_orchestrator.create_schedule_from_intent(
                intent_result,
                schedule_override,
                db_path
            )
            if schedule_created:
                response = f"Da tao lich: {schedule_created.get('title')} luc {schedule_created.get('start_time')}."
                History.create(
                    f"Tao lich hen: {schedule_created.get('title')}",
                    "Lich hen duoc tao tu xac nhan cua nguoi dung",
                    action_type='schedule_created',
                    related_id=schedule_created.get('id'),
                    db_path=db_path
                )
        except Exception as e:
            logger.exception("Failed to create schedule through intent orchestrator")
            response = f"Khong the tao lich: {e}"

        save_chat_history(user_message, response)
        return jsonify({
            'success': True,
            'session_id': chat_session_id,
            'response': response,
            'provider': None,
            'demo_mode': False,
            'schedule_created': schedule_created,
            'schedule_suggestion': None if schedule_created else (intent_result.get('entities') or {}).get('schedule'),
            'workspace_sources': ['calendar'],
            'intent': intent_result,
            'refresh_targets': ['schedule', 'history'],
            'grounded': True,
            'ai_used': False
        })

    if intent_result.get('intent') == 'schedule.list':
        response = _direct_schedule_list_response(user_message, user_id, db_path)
        save_chat_history(user_message, response)
        return jsonify({
            'success': True,
            'session_id': chat_session_id,
            'response': response,
            'provider': None,
            'demo_mode': False,
            'schedule_created': None,
            'schedule_suggestion': None,
            'workspace_sources': ['calendar'],
            'intent': intent_result,
            'refresh_targets': refresh_targets,
            'grounded': True,
            'ai_used': False
        })

    if intent_result.get('intent') == 'email.search':
        response = _direct_email_search_response(user_message, user_id)
        save_chat_history(user_message, response)
        return jsonify({
            'success': True,
            'session_id': chat_session_id,
            'response': response,
            'provider': None,
            'demo_mode': False,
            'schedule_created': None,
            'schedule_suggestion': None,
            'workspace_sources': ['email'],
            'intent': intent_result,
            'refresh_targets': refresh_targets,
            'grounded': True,
            'ai_used': False
        })

    direct_result = intent_orchestrator.execute_direct(intent_result, user_id, db_path)
    if direct_result and intent_result.get('intent') in {'settings.update_mode', 'history.list', 'schedule.create'}:
        response = direct_result.get('response') or ''
        save_chat_history(user_message, response, action_type=direct_result.get('action_type') or 'chat')
        return jsonify({
            'success': True,
            'session_id': chat_session_id,
            'response': response,
            'provider': None,
            'demo_mode': False,
            'schedule_created': None,
            'schedule_suggestion': direct_result.get('schedule_suggestion'),
            'workspace_sources': direct_result.get('workspace_sources') or [],
            'intent': intent_result,
            'refresh_targets': direct_result.get('refresh_targets') or refresh_targets,
            'grounded': True,
            'ai_used': False
        })

    # Build messages for AI with recent chat context for smarter responses
    messages = [{
        "role": "system",
        "content": (
            "You are FlowMate. " + mode_prompt
            + " Answer in Vietnamese unless the user asks otherwise. Be concise, clear, and action-focused. "
            "Use only provided workspace context for facts about the user's email, calendar, history, or account. "
            "If the data is missing, say you do not have enough data instead of guessing. "
            "Do not invent senders, dates, deadlines, meetings, or completed actions. "
            "Classify useful information as meetings, deadlines, tasks, reminders, important information, or low priority. "
            "Suggest the next action, but do not claim a sensitive action was completed unless the user explicitly confirmed it."
        )
    }]

    workspace_sources = set()
    workspace_context = ''
    try:
        workspace_sources, workspace_context = _build_workspace_context(
            user_message,
            user_id,
            db_path
        )
    except Exception as e:
        logger.exception("Failed to build workspace context for user %s", user_id)

    if not workspace_sources:
        recent_history = History.get_recent(limit=8, db_path=db_path, chat_session_id=chat_session_id)
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
                "Không bịa thêm dữ liệu không có trong context. "
                "Nếu context không đủ, nói rõ thiếu dữ liệu nào.\n\n"
                + workspace_context
            )
        })

    messages.append({
        "role": "user",
        "content": user_message
    })
    
    # Generate response
    response = ai_service.generate_response(messages, task=task, user_id=user_id)
    
    # Save to history
    save_chat_history(user_message, response)
    
    # Auto-detect schedule suggestion from AI response
    schedule_info = extract_schedule_from_response(response, user_message)
    schedule_created = None

    # Check if client asked to confirm/create the schedule now
    if schedule_info:
        if client_confirm or schedule_override:
            # Use override values from client when provided, otherwise use detected info
            payload = {
                'title': schedule_override.get('title') or schedule_info.get('title'),
                'description': schedule_override.get('description') or schedule_info.get('description'),
                'start_time': schedule_override.get('start_time') or schedule_info.get('start_time'),
                'end_time': schedule_override.get('end_time') or schedule_info.get('end_time'),
                'attendees': schedule_override.get('attendees') or schedule_info.get('attendees')
            }
            try:
                schedule_id = ScheduleService.create_schedule(
                    title=payload['title'],
                    description=payload['description'],
                    start_time=payload['start_time'],
                    attendees=payload.get('attendees') or [],
                    db_path=db_path
                )

                # Save to chat history for reference
                History.create(
                    f"Tạo lịch hẹn: {payload['title']}",
                    f"Lịch hẹn được tạo từ xác nhận của người dùng",
                    action_type='schedule_created',
                    related_id=schedule_id,
                    db_path=db_path
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
                import threading as _thr
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

    return jsonify({
        'success': True,
        'session_id': chat_session_id,
        'response': response,
        'provider': ai_service.last_provider_used,
        'demo_mode': ai_service.last_provider_used == 'demo',
        'schedule_created': schedule_created,
        'schedule_suggestion': schedule_suggestion,
        'workspace_sources': sorted(workspace_sources),
        'intent': intent_result,
        'refresh_targets': sorted(set(refresh_targets)),
        'grounded': bool(workspace_sources),
        'ai_used': True
    })

@chat_bp.route('/summarize-email', methods=['POST'])
def summarize_email():
    """Summarize email content"""
    data = request.get_json()
    email_content = data.get('content', '').strip()
    
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)

    if not email_content:
        return jsonify({'error': 'Empty email content'}), 400
    
    summary = ai_service.summarize_email(email_content, user_id=user_id)
    
    # Save to history
    History.create(f"Tóm tắt email", summary, action_type='email_summary', db_path=db_path)
    
    return jsonify({
        'success': True,
        'summary': summary
    })

@chat_bp.route('/generate-reply', methods=['POST'])
def generate_reply():
    """Generate automatic email reply"""
    data = request.get_json()
    context = data.get('context', '').strip()
    choice = data.get('choice', '').strip()
    
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)

    if not context or not choice:
        return jsonify({'error': 'Missing context or choice'}), 400
    
    reply = ai_service.generate_reply(context, choice, user_id=user_id)
    
    # Save to history
    History.create(f"Tạo email trả lời: {choice}", reply, action_type='email_reply', db_path=db_path)
    
    return jsonify({
        'success': True,
        'reply': reply
    })

@chat_bp.route('/history', methods=['GET'])
def get_history():
    """Get chat history"""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    limit = request.args.get('limit', 20, type=int)
    chat_session_id = request.args.get('session_id') or request.args.get('chat_session_id')
    if chat_session_id:
        if not History.chat_session_available(user_id, chat_session_id, db_path=db_path):
            return jsonify({
                'success': True,
                'session_id': None,
                'expired': True,
                'history': []
            })
    history = History.get_recent(limit=limit, db_path=db_path, chat_session_id=chat_session_id)
    
    return jsonify({
        'success': True,
        'session_id': chat_session_id,
        'history': history
    })


@chat_bp.route('/sessions', methods=['GET'])
def get_chat_sessions():
    """List saved chat sessions that are still within retention."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    limit = request.args.get('limit', 30, type=int)
    sessions = History.list_chat_sessions(user_id=user_id, limit=limit, db_path=db_path)
    return jsonify({
        'success': True,
        'sessions': sessions,
        'retention': {
            'min_days': 30,
            'max_days': 93,
            'default_days': 90,
        }
    })


@chat_bp.route('/sessions/<session_id>', methods=['PATCH'])
def update_chat_session(session_id):
    """Update chat session metadata such as title or retention period."""
    data = request.get_json(silent=True) or {}
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    updated = History.update_chat_session(
        user_id=user_id,
        session_id=session_id,
        title=data.get('title') if 'title' in data else None,
        retention_days=data.get('retention_days') if 'retention_days' in data else None,
        db_path=db_path,
    )
    if not updated:
        return jsonify({'success': False, 'error': 'chat_session_not_found'}), 404
    return jsonify({'success': True})


@chat_bp.route('/providers', methods=['GET'])
def get_ai_providers():
    """Get AI provider status and fallback chain"""
    return jsonify({
        'success': True,
        'providers': ai_service.get_provider_status()
    })

@chat_bp.route('/clear', methods=['POST'])
def clear_conversation():
    """Clear conversation history"""
    data = request.get_json(silent=True) or {}
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    chat_session_id = data.get('session_id') or data.get('chat_session_id')
    if chat_session_id:
        chat_session_id = _ensure_chat_session(user_id, chat_session_id)
    
    # Delete only chat messages, preserve email and schedule history
    deleted_count = History.clear_all(action_type='chat', db_path=db_path, chat_session_id=chat_session_id)
    
    return jsonify({
        'success': True,
        'session_id': chat_session_id,
        'message': f'Đã xóa {deleted_count} tin nhắn',
        'deleted_count': deleted_count
    })

@chat_bp.route('/clear-all', methods=['POST'])
def clear_all_history():
    """Clear all history including emails and schedules"""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    
    deleted_count = History.clear_all(db_path=db_path)
    
    return jsonify({
        'success': True,
        'message': f'Đã xóa {deleted_count} bản ghi lịch sử',
        'deleted_count': deleted_count
    })

