from flask import Blueprint, request, jsonify
import os
import sys
import re
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.chat_agents import (
    ai_service,
    intent_orchestrator,
    get_agent,
    ChatContext,
    learn_from_exchange_async,
    learn_from_mentors_async,
    normalize_agent_result_language,
)
from services.gmail_service import get_cached_gmail_service
from services.tool_catalog import (
    AGENT_CAPABILITIES,
    AGENT_SYNC_TARGETS,
    AGENT_CONFIRMATION_REQUIRED,
)
from models.history import History
from models.schedule import Schedule
from models.session_memory import SessionMemory
from models.user import User
from utils.user_context import get_current_user_id, get_user_db_path, get_user_token_file
from datetime import datetime

# Configure module logger
logger = logging.getLogger(__name__)

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')


def _format_user_datetime(value, fallback=None):
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return fallback or str(value)
    return parsed.strftime('%d/%m/%Y. %H:%M')


def _ensure_chat_session(user_id, session_id, mode='worker', title=None):
    return History.ensure_chat_session(
        user_id=user_id,
        session_id=session_id,
        title=title,
        mode=mode,
        db_path=get_user_db_path(user_id),
    )


def _agent_profile():
    return {
        'name': 'Bob',
        'product': 'FlowMate',
        'version': '2026-07-workflow-intent-500',
        'channels': ['web', 'mobile'],
        'capabilities': AGENT_CAPABILITIES,
        'sync_targets': AGENT_SYNC_TARGETS,
        'confirmation_required_actions': AGENT_CONFIRMATION_REQUIRED,
        'rules': [
            'Dùng dữ liệu workspace thật khi trả lời về email, lịch, lịch sử, hồ sơ.',
            'Khi cần dữ liệu web công khai hoặc thông tin mới, tra cứu Internet có giới hạn và nêu nguồn.',
            'Có thể học quy tắc xử lý từ các AI mentor đã cấu hình; bài học được lưu riêng theo user và không thay thế xác nhận của người dùng.',
            'Không bịa email, người gửi, ngày giờ, deadline hoặc hành động đã hoàn tất.',
            'Chỉ thực hiện hành động ghi dữ liệu sau khi người dùng xác nhận.',
            'Luôn trả refresh_targets để web/mobile đồng bộ màn liên quan.',
        ],
    }


def _describe_intent_entities(intent, entities):
    """Short human-readable summary of what the agent extracted for this
    intent, so the chat UI can show *why* it answered the way it did.
    Returns None when there's nothing meaningful to show (e.g. email.search
    only carries entities on the AI-assisted classification path)."""
    entities = entities or {}
    if intent == 'email.search':
        query = entities.get('query') or {}
        parts = []
        if query.get('sender'):
            parts.append(f"người gửi: {query['sender']}")
        if query.get('keyword'):
            parts.append(f"từ khóa: {query['keyword']}")
        return "Đã hiểu: " + ", ".join(parts) if parts else None
    if intent == 'schedule.create':
        schedule = entities.get('schedule') or {}
        parts = []
        if schedule.get('start_time'):
            parts.append(f"thời gian: {_format_user_datetime(schedule['start_time'])}")
        if schedule.get('attendees'):
            parts.append(f"người tham gia: {', '.join(schedule['attendees'])}")
        return "Đã hiểu: " + ", ".join(parts) if parts else None
    if intent == 'email.latest_summary':
        count = entities.get('count')
        if count:
            return f"Đã hiểu: lấy {count} email gần nhất"
    return None


def _build_agent_trace(intent_result, workspace_sources=None, refresh_targets=None, ai_used=False, action=None):
    intent = intent_result.get('intent') if intent_result else 'chat.freeform'
    entities = (intent_result or {}).get('entities') or {}
    schedule = entities.get('schedule') if isinstance(entities, dict) else None
    steps = ["Hiểu yêu cầu"]
    sources = sorted(set(workspace_sources or []))
    if sources:
        labels = {
            'email': 'email',
            'calendar': 'lịch',
            'history': 'lịch sử',
            'profile': 'hồ sơ',
            'knowledge': 'kiến thức',
            'internet': 'internet',
            'time': 'thời gian hệ thống',
        }
        steps.append("Kiểm tra " + ", ".join(labels.get(source, source) for source in sources))
    if intent and intent != 'chat.freeform':
        steps.append(f"Nhận diện intent: {intent}")
    entity_step = _describe_intent_entities(intent, entities)
    if entity_step:
        steps.append(entity_step)
    if action:
        steps.append(action)
    elif schedule:
        steps.append("Chuẩn bị gợi ý lịch cần xác nhận")
    elif ai_used:
        steps.append("Soạn phản hồi bằng AI")

    return {
        'mode': 'agent',
        'intent': intent,
        'confidence': (intent_result or {}).get('confidence'),
        'requires_confirmation': bool((intent_result or {}).get('requires_confirmation')),
        'workspace_sources': sources,
        'refresh_targets': sorted(set(refresh_targets or [])),
        'steps': steps,
        'capabilities': [item['id'] for item in AGENT_CAPABILITIES],
        'sync_contract': {
            'targets': AGENT_SYNC_TARGETS,
            'web_mobile_parity': True,
        },
    }


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
            "Student Mode: treat the user's academic life as the primary workspace. "
            "Prioritize assignments, exams, class email, teacher/school messages, "
            "course materials, group projects, tuition or administration notices, "
            "and study deadlines before general productivity items. When planning, "
            "separate work into subjects/courses, deadlines, difficulty, energy level, "
            "available calendar gaps, and concrete next study blocks. Prefer concise "
            "study plans with time blocks, review cycles, deliverables, and a short "
            "next action. For ambiguous student requests, first look for class/email/"
            "calendar/checklist context, then ask only the smallest missing question. "
            "Use student-friendly coaching: break big assignments into steps, suggest "
            "Pomodoro or spaced-repetition when useful, protect sleep/rest, and avoid "
            "inventing grades, deadlines, classes, or school policies not in context."
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

    intent_result = intent_orchestrator.detect_workflow_with_ai(
        user_message, ai_service, user_id=user_id, db_path=db_path, chat_session_id=chat_session_id,
    )
    refresh_targets = list(intent_result.get('refresh_targets') or [])

    ctx = ChatContext(
        user_message=user_message,
        user_id=user_id,
        db_path=db_path,
        chat_session_id=chat_session_id,
        mode=mode,
        mode_prompt=mode_prompt,
        task=task,
        intent_result=intent_result,
        refresh_targets=refresh_targets,
        client_confirm=bool(data.get('confirmed_schedule')),
        schedule_override=data.get('schedule_override') or {},
        action_confirm=bool(data.get('confirmed_action')),
        action_override=data.get('action_override') or {},
    )

    agent = get_agent(intent_result.get('intent'))
    result = agent.handle(ctx)
    if result is None:
        result = get_agent('chat.freeform').handle(ctx)
    result = normalize_agent_result_language(result, user_message, user_id=user_id)

    save_chat_history(user_message, result.response, action_type=result.action_type)
    learn_from_exchange_async(user_message, result.response, user_id)
    learn_from_mentors_async(
        user_message,
        result.response,
        user_id,
        intent_result=intent_result,
        workspace_sources=result.workspace_sources,
        primary_provider=result.provider,
        db_path=db_path,
    )

    response_payload = {
        'success': True,
        'session_id': chat_session_id,
        'response': result.response,
        'provider': result.provider,
        'demo_mode': result.demo_mode,
        'schedule_created': result.schedule_created,
        'schedule_suggestion': result.schedule_suggestion,
        'pending_action': result.pending_action,
        'action_applied': result.action_applied,
        'intent': intent_result,
        'refresh_targets': result.refresh_targets,
        'agent_trace': _build_agent_trace(
            intent_result,
            workspace_sources=result.workspace_sources,
            refresh_targets=result.refresh_targets,
            ai_used=result.ai_used,
            action=result.action,
        ),
        'grounded': result.grounded,
        'ai_used': result.ai_used,
    }
    if result.workspace_sources is not None:
        response_payload['workspace_sources'] = result.workspace_sources
    if result.suggested_actions is not None:
        response_payload['suggested_actions'] = result.suggested_actions
    if result.email_source is not None:
        response_payload['email_source'] = result.email_source
    if result.email_sources is not None:
        response_payload['email_sources'] = result.email_sources
    if result.day_plan_suggestion is not None:
        response_payload['day_plan_suggestion'] = result.day_plan_suggestion

    return jsonify(response_payload)


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


def _extract_reply_address(sender_header):
    """Pull a bare email address out of a "Name <addr>" From header."""
    match = re.search(r'[\w\.+-]+@[\w\.-]+\.\w+', sender_header or '')
    return match.group(0) if match else ''


@chat_bp.route('/send-drafted-reply', methods=['POST'])
def send_drafted_reply():
    """Send a reply that the AI already drafted for a specific email --
    the user clicking 'Soạn trả lời' then 'Gửi luôn' (two deliberate steps)
    is the confirmation gate, mirroring the schedule_suggestion confirm card."""
    data = request.get_json(silent=True) or {}
    email_id = (data.get('email_id') or '').strip()
    reply_text = (data.get('reply_text') or '').strip()
    if not email_id or not reply_text:
        return jsonify({'error': 'Missing email_id or reply_text'}), 400

    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    token_file = get_user_token_file(user_id)
    if not token_file or not os.path.exists(token_file):
        return jsonify({'error': 'Gmail chưa được kết nối'}), 401

    service = get_cached_gmail_service(token_file)
    original = service.get_email_details(email_id, lazy=True)
    if not original:
        return jsonify({'error': 'Không tìm thấy email gốc'}), 404

    to_address = _extract_reply_address(original.get('sender'))
    if not to_address:
        return jsonify({'error': 'Không xác định được địa chỉ người nhận'}), 400

    subject = original.get('subject') or '(Không có tiêu đề)'
    if not subject.lower().startswith('re:'):
        subject = f"Re: {subject}"

    try:
        success = service.send_email(to_address, subject, reply_text)
    except Exception as e:
        logger.exception("Failed to send drafted reply for email %s", email_id)
        return jsonify({'error': str(e)}), 500

    if not success:
        return jsonify({'error': 'Gửi email không thành công'}), 500

    History.create(
        f"Gửi email tới {to_address}",
        reply_text,
        action_type='email_sent',
        db_path=db_path,
    )
    return jsonify({'success': True})


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


@chat_bp.route('/sessions/<session_id>', methods=['DELETE'])
def delete_chat_session(session_id):
    """Delete a saved chat session immediately."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    deleted = History.delete_chat_session(
        user_id=user_id,
        session_id=session_id,
        db_path=db_path,
    )
    if not deleted:
        return jsonify({'success': False, 'error': 'chat_session_not_found'}), 404
    SessionMemory.delete_for_session(session_id, db_path=db_path)
    return jsonify({'success': True})


@chat_bp.route('/providers', methods=['GET'])
def get_ai_providers():
    """Get AI provider status and fallback chain"""
    return jsonify({
        'success': True,
        'providers': ai_service.get_provider_status()
    })


@chat_bp.route('/agent-profile', methods=['GET'])
def get_agent_profile():
    """Return the shared agent contract used by web and mobile clients."""
    return jsonify({
        'success': True,
        'agent': _agent_profile(),
        'providers': ai_service.get_provider_status(),
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
    if chat_session_id:
        SessionMemory.delete_for_session(chat_session_id, db_path=db_path)

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
