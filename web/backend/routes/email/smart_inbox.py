"""Smart Inbox classification: a deterministic (non-AI) heuristic that
buckets each email into Action required / Waiting / FYI / Low priority
(design doc section 8.2), plus the lightweight category tagger it and
several other modules build on.

Split out of the former monolithic routes/email.py -- see
routes/email/__init__.py for the package-level overview.
"""
import re
from datetime import datetime

from routes.email.shared import _normalize_search_text, _parse_email_base_date, _extract_weekday_date


def _classify_email_lightweight(email):
    text = ' '.join([
        email.get('subject', '') or '',
        email.get('sender', '') or '',
        email.get('snippet', '') or ''
    ]).lower()

    rules = [
        ('meeting', ['meeting', 'hop', 'họp', 'lich hen', 'lịch hẹn', 'appointment', 'schedule', 'calendar', 'zoom', 'meet', 'teams']),
        ('education', ['school', 'class', 'student', 'teacher', 'course', 'lesson', 'assignment', 'giao duc', 'giáo dục', 'hoc sinh', 'học sinh']),
        ('finance', ['invoice', 'payment', 'receipt', 'bank', 'billing', 'hoa don', 'hóa đơn', 'thanh toan', 'thanh toán']),
        ('promotion', ['sale', 'discount', 'promotion', 'newsletter', 'unsubscribe', 'coupon', 'marketing', 'khuyến mãi']),
        ('work', ['task', 'project', 'deadline', 'report', 'proposal', 'contract', 'cong viec', 'công việc']),
        ('personal', ['family', 'friend', 'personal'])
    ]

    for tag, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return tag
    return 'other'


# Deadline terms shared with _extract_meeting_suggestion's own deadline_terms
# list below -- kept as a separate constant here (rather than importing from
# inside that function) since Smart Inbox needs it standalone, without the
# rest of the meeting-detection signal combination.
_DEADLINE_TERMS = [
    'deadline', 'due date', 'due by', 'due on', 'submit by', 'submission',
    'han chot', 'han nop', 'han cuoi', 'den han', 'ngay nop', 'nop bai',
    'het han', 'truoc ngay', 'truoc han'
]
_WAITING_TERMS = [
    'pending', 'under review', 'we will get back to you', "we'll get back to you",
    'processing your request', 'your request has been received',
    'dang xu ly', 'dang cho', 'da tiep nhan', 'se phan hoi', 'se lien he lai',
]
_AUTOMATED_SENDER_TERMS = ['noreply', 'no-reply', 'donotreply', 'notifications@', 'notification@']


def _looks_automated(sender):
    sender_lower = str(sender or '').lower()
    return any(term in sender_lower for term in _AUTOMATED_SENDER_TERMS)


def _email_needs_reply_heuristic(subject, snippet):
    # Mirrors services/chat_agents.py's _email_needs_reply heuristic,
    # re-defined locally rather than cross-imported -- routes shouldn't
    # reach into a service module's own private helper.
    text = f"{subject or ''} {snippet or ''}"
    if '?' in text:
        return True
    keywords = ['please confirm', 'let me know', 'can you', 'could you', 'xac nhan', 'phan hoi']
    normalized = _normalize_search_text(text)
    return any(keyword in normalized for keyword in keywords)


def _smart_inbox_bucket(email):
    """Classifies one email into Action required / Waiting / FYI / Low
    priority (design doc section 8.2). Deliberately a deterministic
    heuristic, not an AI call -- Bob often runs with no real LLM configured
    (BOB_LOCAL_ONLY, Ollama not enabled), so Smart Inbox can't depend on one
    to work at all."""
    tag = email.get('tag') or _classify_email_lightweight(email)
    subject = email.get('subject', '') or ''
    snippet = email.get('snippet', '') or ''
    sender = email.get('sender', '') or ''
    normalized = _normalize_search_text(' '.join([subject, sender, snippet]))

    if tag == 'promotion' or _looks_automated(sender):
        return 'low_priority'

    has_deadline = any(term in normalized for term in _DEADLINE_TERMS)
    if has_deadline or (email.get('is_unread') and _email_needs_reply_heuristic(subject, snippet)):
        return 'action_required'

    if any(term in normalized for term in _WAITING_TERMS):
        return 'waiting'

    return 'fyi'


def _extract_deadline_date(email):
    """A deadline date, if _DEADLINE_TERMS matched and a date/weekday
    reference is nearby. Reuses the same date-parsing helpers
    _extract_meeting_suggestion already relies on (_extract_weekday_date,
    _parse_email_base_date) rather than re-deriving date logic; the
    numeric/ISO/text-date regexes are duplicated in miniature here since
    they're inlined inside _extract_meeting_suggestion rather than
    factored into their own function."""
    subject = str(email.get('subject', '') or '')
    snippet = str(email.get('snippet', '') or '')
    body = str(email.get('body', '') or '')
    text = ' '.join([subject, snippet, body])
    normalized = _normalize_search_text(text)

    if not any(term in normalized for term in _DEADLINE_TERMS):
        return None

    base_date = _parse_email_base_date(email)
    try:
        date_match = re.search(r'(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})(?!\d)', normalized)
        if date_match:
            day, month, year = map(int, date_match.groups())
            if year < 100:
                year += 2000
            return datetime(year, month, day).date()
        iso_date_match = re.search(r'(?<!\d)(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?!\d)', normalized)
        if iso_date_match:
            year, month, day = map(int, iso_date_match.groups())
            return datetime(year, month, day).date()
        text_date_match = re.search(r'(?<!\d)(\d{1,2})\s+thang\s+(\d{1,2})(?:\s*,?\s*(\d{4}))?(?!\d)', normalized)
        if text_date_match:
            day, month = int(text_date_match.group(1)), int(text_date_match.group(2))
            year = int(text_date_match.group(3)) if text_date_match.group(3) else base_date.year
            return datetime(year, month, day).date()
    except ValueError:
        pass
    return _extract_weekday_date(normalized, base_date)
