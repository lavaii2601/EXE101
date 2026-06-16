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


def _normalize_intent_text(value):
    value = unicodedata.normalize('NFD', str(value or '').lower())
    value = ''.join(char for char in value if unicodedata.category(char) != 'Mn')
    return value.replace('đ', 'd')


def _is_latest_email_summary_request(message):
    normalized = _normalize_intent_text(message)
    has_email = any(term in normalized for term in (
        'email', 'e-mail', 'gmail', 'mail', 'thu moi', 'hop thu'
    ))
    has_latest = any(term in normalized for term in (
        'moi nhat', 'gan nhat', 'vua nhan', 'moi nhan',
        'latest', 'newest', 'most recent'
    ))
    has_summary = any(term in normalized for term in (
        'tom tat', 'noi dung', 'noi gi', 'co gi', 'doc ',
        'summary', 'summarize', 'what does'
    ))
    return has_email and has_latest and has_summary


def _latest_email_count(message):
    normalized = _normalize_intent_text(message)
    match = re.search(
        r'\b(\d{1,2})\s*(?:email|e-mail|mail|thu)\b',
        normalized
    )
    if match:
        return max(1, min(int(match.group(1)), 5))

    number_words = {
        'mot': 1,
        'hai': 2,
        'ba': 3,
        'bon': 4,
        'tu': 4,
        'nam': 5,
    }
    for word, count in number_words.items():
        if re.search(rf'\b{word}\s+(?:email|e-mail|mail|thu)\b', normalized):
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

    local_schedules = []
    for schedule in Schedule.get_all(limit=100, db_path=db_path):
        start_time = _parse_schedule_datetime(schedule.get('start_time'))
        if start_time and window_start <= start_time < window_end:
            local_schedules.append(schedule)
    local_schedules.sort(
        key=lambda item: _parse_schedule_datetime(item.get('start_time')) or window_end
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

    if _is_latest_email_summary_request(user_message):
        try:
            requested_count = _latest_email_count(user_message)
            response, source_emails = _summarize_latest_emails(user_id, requested_count)
            source_email = source_emails[0]
            History.create(user_message, response, action_type='chat', db_path=db_path)
            return jsonify({
                'success': True,
                'response': response,
                'provider': ai_service.last_provider_used,
                'demo_mode': ai_service.last_provider_used == 'demo',
                'schedule_created': None,
                'schedule_suggestion': None,
                'workspace_sources': ['email'],
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
                } for email in source_emails]
            })
        except Exception as e:
            logger.exception("Failed to summarize latest Gmail messages for user %s", user_id)
            response = f"Không thể lấy email gần nhất từ Gmail: {e}"
            History.create(user_message, response, action_type='chat', db_path=db_path)
            return jsonify({
                'success': True,
                'response': response,
                'provider': None,
                'demo_mode': False,
                'schedule_created': None,
                'schedule_suggestion': None
            })

    # Build messages for AI with recent chat context for smarter responses
    messages = [{
        "role": "system",
        "content": (
            "You are FlowMate. " + mode_prompt
            + " Be concise, clear, and action-focused. Classify useful information as "
            "meetings, deadlines, tasks, reminders, important information, or low priority. "
            "Suggest the next action, but do not claim a sensitive action was completed "
            "unless the user explicitly confirmed it."
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
        recent_history = History.get_recent(limit=8, db_path=db_path)
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
                "Không bịa thêm dữ liệu không có trong context.\n\n"
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
    History.create(user_message, response, action_type='chat', db_path=db_path)
    
    # Auto-detect schedule suggestion from AI response
    schedule_info = extract_schedule_from_response(response, user_message)
    schedule_created = None

    # Check if client asked to confirm/create the schedule now
    client_confirm = bool(data.get('confirmed_schedule'))
    schedule_override = data.get('schedule_override') or {}

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
        'response': response,
        'provider': ai_service.last_provider_used,
        'demo_mode': ai_service.last_provider_used == 'demo',
        'schedule_created': schedule_created,
        'schedule_suggestion': schedule_suggestion,
        'workspace_sources': sorted(workspace_sources)
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
    history = History.get_recent(limit=limit, db_path=db_path)
    
    return jsonify({
        'success': True,
        'history': history
    })

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
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    
    # Delete only chat messages, preserve email and schedule history
    deleted_count = History.clear_all(action_type='chat', db_path=db_path)
    
    return jsonify({
        'success': True,
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
