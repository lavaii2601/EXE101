from flask import Blueprint, request, jsonify
import os
import sys
import logging
import re
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ai_service import AIService
from services.schedule_service import ScheduleService
from models.history import History
from models.schedule import Schedule
from utils.user_context import get_current_user_id, get_user_db_path, get_user_token_file
from services.calendar_service import CalendarService

# Configure module logger
logger = logging.getLogger(__name__)

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')
ai_service = AIService()

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
    task = (data.get('task', 'chat') or 'chat').strip().lower()
    if task not in ['chat', 'summary', 'reply', 'analyze']:
        task = 'chat'
    
    if not user_message:
        return jsonify({'error': 'Empty message'}), 400
    
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    History.init_db(db_path=db_path)
    Schedule.init_db(db_path=db_path)

    # Build messages for AI with recent chat context for smarter responses
    messages = [
        {
            "role": "system",
            "content": "Bạn là TeacherBot, trợ lý giáo viên. Trả lời ngắn gọn, chuyên nghiệp, hữu ích về email, lịch hẹn và công việc giảng dạy."
        }
    ]

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

    messages.append({
        "role": "user",
        "content": user_message
    })
    
    # Generate response
    response = ai_service.generate_response(messages, task=task, user_id=user_id)
    
    # Save to history
    History.create(user_message, response, action_type='chat', db_path=db_path)
    
    # Auto-detect and save schedule if mentioned in response
    schedule_info = extract_schedule_from_response(response, user_message)
    schedule_created = None
    
    if schedule_info:
        try:
            schedule_id = ScheduleService.create_schedule(
                title=schedule_info['title'],
                description=schedule_info['description'],
                start_time=schedule_info['start_time'],
                attendees=schedule_info['attendees'],
                db_path=db_path
            )
            
            # Also save to chat history for reference
            History.create(
                f"Tạo lịch hẹn: {schedule_info['title']}",
                f"Lịch hẹn được tạo tự động từ chat",
                action_type='schedule_created',
                related_id=schedule_id,
                db_path=db_path
            )
            
            schedule_created = {
                'id': schedule_id,
                'title': schedule_info['title'],
                'start_time': schedule_info['start_time']
            }
            
            logger.info(f"Auto-created schedule: {schedule_info['title']}")
        except Exception as e:
            logger.error(f"Failed to auto-create schedule: {e}")

        # Spawn background calendar sync for auto-created schedule
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

        # Background calendar sync is handled by schedule creation (non-blocking)
    
    return jsonify({
        'success': True,
        'response': response,
        'provider': ai_service.last_provider_used,
        'demo_mode': ai_service.last_provider_used == 'demo',
        'schedule_created': schedule_created
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
