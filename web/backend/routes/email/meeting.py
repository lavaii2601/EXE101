"""Meeting-suggestion detection: heuristic extraction of a candidate meeting
from one email's text, de-duplication against existing schedules, staleness
pruning, DB persistence via the MeetingSuggestion model, and the three
/meeting-suggestions* routes.

Split out of the former monolithic routes/email.py -- see
routes/email/__init__.py for the package-level overview.

Note for tests/test_email_meeting_detection.py: that file patches
"routes.email.MeetingSuggestion.<method>" (works unchanged -- patching a
class attribute affects every module's reference to the same class object)
but had to have its patch target for _load_schedule_match_index updated to
"routes.email.meeting._load_schedule_match_index" to follow that function to
its new module, the same way services/chat_agents' split required updating
"services.chat_agents._build_workspace_context" to
"services.chat_agents.freeform_agent._build_workspace_context".
"""
import logging
import re
from datetime import datetime, timedelta

from flask import jsonify, request, session

from models.meeting_suggestion import MeetingSuggestion
from models.schedule import Schedule
from utils.user_context import get_current_user_id, get_user_db_path

from routes.email.shared import (
    email_bp,
    _normalize_search_text,
    _parse_email_base_date,
    _extract_weekday_date,
    _extract_times,
    _compact_preview,
)
from routes.email.oauth import _load_gmail_service

# Configure module logger
logger = logging.getLogger(__name__)


def _is_google_calendar_notification(email_or_suggestion):
    sender = _normalize_search_text((email_or_suggestion or {}).get('sender', ''))
    subject = _normalize_search_text((email_or_suggestion or {}).get('subject', ''))
    snippet = _normalize_search_text((email_or_suggestion or {}).get('snippet', ''))
    source = ' '.join([sender, subject, snippet])
    return (
        'calendar-notification@google.com' in source
        or 'lich google' in source
        or 'google calendar' in source
        or subject.startswith('loi nhac:')
        or subject.startswith('reminder:')
    )


def _extract_meeting_suggestion(email):
    subject = str(email.get('subject', '') or '').strip()
    sender = str(email.get('sender', '') or '').strip()
    snippet = str(email.get('snippet', '') or '').strip()
    body = str(email.get('body', '') or '').strip()
    text = ' '.join([subject, snippet, body])
    normalized = _normalize_search_text(text)

    direct_terms = [
        'cuoc hop', 'cuoc hen', 'hop luc', 'lich hen', 'hen gap', 'gap mat',
        'moi hop', 'thu moi hop', 'moi tham gia', 'buoi trao doi', 'buoi phong van',
        'meeting', 'appointment', 'meeting invitation', 'calendar invite',
        'can we meet', 'could we meet', 'let us meet', "let's meet", 'interview',
        'demo call', 'review call', 'consultation', 'sync call',
        'google meet', 'zoom', 'microsoft teams', 'book slot', 'booked',
        'hen kham', 'lich kham', 'buoi hen', 'buoi kham', 'cuoc gap',
        'phong van luc', 'tu van luc', 'trao doi luc', 'gap nhau luc',
        'xac nhan lich hen', 'xac nhan cuoc hen', 'dat lich hen', 'dat lich kham',
        'moi ban den', 'moi quy khach', 'moi anh chi', 'buoi lam viec',
        'phong van', 'kham benh', 'lich thi', 'buoi thi', 'gap truc tiep',
        'tu van truc tiep', 'ghe tham', 'ghe qua van phong', 'dat lich tu van',
        'thu moi', 'giay moi', 'moi den', 'chu tri cuoc hop',
    ]
    schedule_terms = [
        'schedule', 'calendar', 'dat lich', 'xep lich', 'time slot',
        'khung gio', 'thoi gian phu hop', 'available time', 'availability',
        'propose a time', 'suggest a time', 'dat cho', 'dat ban', 'sap xep thoi gian',
    ]
    deadline_terms = [
        'deadline', 'due date', 'due by', 'due on', 'submit by', 'submission',
        'han chot', 'han nop', 'han cuoi', 'den han', 'ngay nop', 'nop bai',
        'het han', 'truoc ngay', 'truoc han'
    ]
    negation_terms = [
        'huy cuoc hop', 'huy lich hen', 'huy buoi hop', 'huy buoi hen',
        'da bi huy', 'da huy', 'hoan lich', 'tam hoan', 'khong dien ra',
        'khong the tham du', 'meeting cancelled', 'meeting canceled',
        'cancelled', 'canceled', 'postponed', 'call off',
    ]
    reschedule_terms = [
        'doi sang', 'doi lich sang', 'chuyen sang', 'lui sang', 'doi ngay hop',
        'doi lich hen sang', 'rescheduled to', 'moved to',
    ]
    # A formal Vietnamese meeting invite often uses labelled fields
    # ("Thời gian:", "Địa điểm:", "Thành phần:") instead of a single obvious
    # keyword, so treat two-or-more such labels as its own signal.
    invite_label_terms = ['thoi gian:', 'dia diem:', 'thanh phan:', 'noi dung cuoc hop', 'chu tri:']
    structured_invite_signal = sum(term in normalized for term in invite_label_terms) >= 2

    time_signal = bool(re.search(r'(?<!\d)(?:[01]?\d|2[0-3])[:h]\d{2}(?!\d)', normalized))
    natural_time_signal = bool(re.search(r'(?<!\d)(?:[01]?\d|2[0-3])\s*(?:gio|g|h)(?:\s*\d{1,2})?\s*(?:sang|chieu|toi)?(?!\d)', normalized))
    date_signal = bool(re.search(
        r'(?<!\d)(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})(?!\d)',
        normalized
    )) or bool(_extract_weekday_date(normalized, _parse_email_base_date(email)))
    is_meeting = (
        any(term in normalized for term in direct_terms)
        or structured_invite_signal
        or (any(term in normalized for term in schedule_terms) and (time_signal or natural_time_signal or date_signal))
        or (any(term in normalized for term in deadline_terms) and (time_signal or natural_time_signal or date_signal))
    )
    if not is_meeting:
        return None

    has_negation = any(term in normalized for term in negation_terms)
    has_reschedule = any(term in normalized for term in reschedule_terms)
    if has_negation and not has_reschedule:
        return None

    meeting_date = None
    date_match = re.search(
        r'(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})(?!\d)',
        normalized
    )
    iso_date_match = re.search(
        r'(?<!\d)(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?!\d)',
        normalized
    )
    text_date_match = re.search(
        r'(?<!\d)(\d{1,2})\s+thang\s+(\d{1,2})(?:\s*,?\s*(\d{4}))?(?!\d)',
        normalized
    )
    base_date = _parse_email_base_date(email)
    try:
        if date_match:
            day, month, year = map(int, date_match.groups())
            if year < 100:
                year += 2000
            meeting_date = datetime(year, month, day).date()
        elif iso_date_match:
            year, month, day = map(int, iso_date_match.groups())
            meeting_date = datetime(year, month, day).date()
        elif text_date_match:
            day, month = int(text_date_match.group(1)), int(text_date_match.group(2))
            year_text = text_date_match.group(3)
            if year_text:
                year = int(year_text)
            else:
                # No year given (e.g. "ngày 25 tháng 7") -- assume the next
                # upcoming occurrence relative to the email's own date.
                year = base_date.year
                candidate = datetime(year, month, day).date()
                if candidate < base_date - timedelta(days=3):
                    year += 1
            meeting_date = datetime(year, month, day).date()
    except ValueError:
        meeting_date = None
    if meeting_date is None:
        meeting_date = _extract_weekday_date(normalized, base_date)

    start_time = None
    end_time = None
    time_matches = _extract_times(normalized)
    if meeting_date and time_matches:
        start_hour, start_minute = time_matches[0]
        start_dt = datetime.combine(
            meeting_date,
            datetime.strptime(f'{start_hour:02d}:{start_minute:02d}', '%H:%M').time()
        )
        start_time = start_dt.isoformat()
        if len(time_matches) > 1:
            end_hour, end_minute = time_matches[1]
            end_dt = datetime.combine(
                meeting_date,
                datetime.strptime(f'{end_hour:02d}:{end_minute:02d}', '%H:%M').time()
            )
            if end_dt > start_dt:
                end_time = end_dt.isoformat()
        if not end_time:
            end_time = (start_dt + timedelta(hours=1)).isoformat()

    email_addresses = re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text)
    attendees = ','.join(dict.fromkeys(email_addresses))
    description = _compact_preview(
        f"Nguồn email từ {sender}\n{snippet or body}",
        max_chars=700
    )

    location = ''
    location_match = re.search(
        r'(?:địa điểm|dia diem|địa chỉ|dia chi|location)\s*[:\-]\s*([^\n,.;]{2,80})',
        text,
        re.IGNORECASE
    )
    if location_match:
        location = re.sub(r'\s+', ' ', location_match.group(1)).strip()[:120]

    return {
        'sender': sender,
        'subject': subject,
        'email_date': email.get('date', ''),
        'snippet': snippet,
        'title': subject or 'Lịch hẹn từ email',
        'description': description,
        'start_time': start_time,
        'end_time': end_time,
        'location': location,
        'attendees': attendees,
    }


def _load_schedule_match_index(db_path):
    index = []
    for schedule in Schedule.get_all(limit=500, db_path=db_path):
        try:
            schedule_dt = datetime.fromisoformat(
                str(schedule.get('start_time') or '').replace('Z', '+00:00')
            )
            if schedule_dt.tzinfo is not None:
                schedule_dt = schedule_dt.replace(tzinfo=None)
        except (TypeError, ValueError):
            continue
        end_dt = None
        try:
            end_dt = datetime.fromisoformat(
                str(schedule.get('end_time') or '').replace('Z', '+00:00')
            )
            if end_dt.tzinfo is not None:
                end_dt = end_dt.replace(tzinfo=None)
        except (TypeError, ValueError):
            end_dt = None
        index.append({
            'start_time': schedule_dt,
            'end_time': end_dt,
            'title': _normalize_search_text(schedule.get('title', '')),
            'attendees': _normalize_search_text(schedule.get('attendees', '')),
        })
    return index


def _token_set(value):
    tokens = re.findall(r'[a-z0-9]+', _normalize_search_text(value))
    ignored = {
        'loi', 'nhac', 'reminder', 'calendar', 'lich', 'google', 'meeting',
        'event', 'cuoc', 'hop', 'hen', 'vao', 'luc', 'thu', 'thang', 'nam',
        'gmt', 'am', 'pm'
    }
    return {token for token in tokens if len(token) >= 3 and token not in ignored}


def _token_overlap(left, right):
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return 0
    return len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))


def _meeting_suggestion_exists_in_schedule(suggestion, schedule_index):
    if _is_google_calendar_notification(suggestion):
        return True

    suggested_start = suggestion.get('start_time')
    if not suggested_start:
        return False
    try:
        suggested_dt = datetime.fromisoformat(suggested_start)
    except (TypeError, ValueError):
        return False

    if suggested_dt.tzinfo is not None:
        suggested_dt = suggested_dt.replace(tzinfo=None)

    subject = _normalize_search_text(suggestion.get('subject', ''))
    suggestion_title = _normalize_search_text(suggestion.get('title', ''))
    suggestion_attendees = _normalize_search_text(suggestion.get('attendees', ''))
    for schedule in schedule_index:
        schedule_dt = schedule.get('start_time')
        schedule_end = schedule.get('end_time')
        if schedule_end and schedule_dt <= suggested_dt <= schedule_end:
            return True
        same_day = schedule_dt.date() == suggested_dt.date()
        title = schedule.get('title', '')
        attendees = schedule.get('attendees', '')
        if same_day and (
            _token_overlap(title, subject) >= 0.45
            or _token_overlap(title, suggestion_title) >= 0.45
            or (suggestion_attendees and attendees and _token_overlap(attendees, suggestion_attendees) >= 0.5)
        ):
            return True
        if abs((schedule_dt - suggested_dt).total_seconds()) > 300:
            continue
        if not title or title in subject or subject in title:
            return True
    return False


def _is_meeting_suggestion_stale(suggestion):
    """True once the suggested meeting time is fully in the past.

    _extract_meeting_suggestion resolves relative phrases ("ngay mai",
    "tuan sau", weekday names) against the *email's own send date*
    (_parse_email_base_date), which is the correct reading of what the
    email meant when it arrived. But an old inbox email scanned today can
    still resolve to a date that has since passed -- without this check
    that suggestion would sit at the top of the pending list forever
    (MeetingSuggestion.get_pending sorts start_time ascending), making the
    feature look "stuck" re-surfacing old mail instead of upcoming ones.
    """
    reference = suggestion.get('end_time') or suggestion.get('start_time')
    if not reference:
        return False
    try:
        reference_dt = datetime.fromisoformat(str(reference))
    except (TypeError, ValueError):
        return False
    if reference_dt.tzinfo is not None:
        reference_dt = reference_dt.replace(tzinfo=None)
    return reference_dt < datetime.now()


def _store_meeting_suggestions(emails, db_path):
    detected = []
    schedule_index = None
    for email in emails:
        try:
            email_id = email.get('id')
            if not email_id:
                continue
            suggestion = _extract_meeting_suggestion(email)
            if not suggestion:
                continue
            if _is_meeting_suggestion_stale(suggestion):
                MeetingSuggestion.dismiss_email(email_id, db_path=db_path)
                continue
            if _is_google_calendar_notification(email) or _is_google_calendar_notification(suggestion):
                MeetingSuggestion.dismiss_email(email_id, db_path=db_path)
                continue
            if schedule_index is None:
                schedule_index = _load_schedule_match_index(db_path)
            if _meeting_suggestion_exists_in_schedule(suggestion, schedule_index):
                MeetingSuggestion.dismiss_email(email_id, db_path=db_path)
                continue
            suggestion_id = MeetingSuggestion.upsert(email_id, suggestion, db_path=db_path)
            detected.append({'id': suggestion_id, 'email_id': email_id, **suggestion})
        except Exception as e:
            logger.warning(
                "Skipping meeting suggestion scan for email %s: %s",
                (email or {}).get('id', 'unknown'),
                e,
                exc_info=True,
            )
    return detected


def _prune_existing_meeting_suggestions(db_path):
    schedule_index = _load_schedule_match_index(db_path)
    pending = MeetingSuggestion.get_pending(db_path=db_path)
    visible = []
    for suggestion in pending:
        email_id = suggestion.get('email_id')
        if _is_meeting_suggestion_stale(suggestion):
            if email_id:
                MeetingSuggestion.dismiss_email(email_id, db_path=db_path)
            continue
        # With no existing schedules there is nothing to de-duplicate
        # against -- skipping the match check here used to hide every valid
        # email suggestion from a brand-new user or an empty calendar.
        if schedule_index and _meeting_suggestion_exists_in_schedule(suggestion, schedule_index):
            if email_id:
                MeetingSuggestion.dismiss_email(email_id, db_path=db_path)
            continue
        visible.append(suggestion)
    return visible


def _safe_prune_existing_meeting_suggestions(db_path):
    try:
        return _prune_existing_meeting_suggestions(db_path)
    except Exception:
        logger.warning("Skipping meeting suggestion pruning", exc_info=True)
        return []


def _safe_pending_meeting_suggestions(db_path):
    try:
        return MeetingSuggestion.get_pending(db_path=db_path)
    except Exception:
        logger.warning("Skipping pending meeting suggestions", exc_info=True)
        return []


@email_bp.route('/meeting-suggestions', methods=['GET'])
def get_meeting_suggestions():
    user_id = get_current_user_id(request, session=session)
    db_path = get_user_db_path(user_id)
    suggestions = _prune_existing_meeting_suggestions(db_path)
    return jsonify({
        'success': True,
        'suggestions': suggestions,
        'count': len(suggestions),
    })


@email_bp.route('/meeting-suggestions/scan', methods=['POST'])
def scan_meeting_suggestions():
    user_id = get_current_user_id(request, session=session)
    db_path = get_user_db_path(user_id)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated'}), 401

    try:
        emails = service.get_emails(
            max_results=20,
            query='in:inbox',
            include_read=True,
            lazy=False,
            raise_errors=True,
        )
        detected = _store_meeting_suggestions(emails, db_path)
        pending = _prune_existing_meeting_suggestions(db_path)
        return jsonify({
            'success': True,
            'scanned': len(emails),
            'detected': len(detected),
            'suggestions': pending,
            'count': len(pending),
        })
    except Exception as e:
        logger.error(f"Error in scan_meeting_suggestions: {str(e)}", exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500


@email_bp.route('/meeting-suggestions/<int:suggestion_id>/status', methods=['PATCH'])
def update_meeting_suggestion_status(suggestion_id):
    user_id = get_current_user_id(request, session=session)
    db_path = get_user_db_path(user_id)
    data = request.get_json() or {}
    status = str(data.get('status') or '').strip().lower()
    if status not in {'dismissed', 'created'}:
        return jsonify({'error': 'Invalid suggestion status'}), 400
    updated = MeetingSuggestion.update_status(
        suggestion_id,
        status,
        schedule_id=data.get('schedule_id'),
        db_path=db_path,
    )
    if not updated:
        return jsonify({'error': 'Suggestion not found'}), 404
    return jsonify({'success': True, 'status': status})
