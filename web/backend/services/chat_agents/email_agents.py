"""Email-domain chat agents: latest-summary, search, mark read/unread, and
the private helpers they share (search-query parsing, mark propose/apply,
result-reference resolution, draft-reply suggestions)."""
import os
import re
import logging
from datetime import datetime, timedelta

from services.gmail_service import get_cached_gmail_service
from models.history import History
from models.session_memory import SessionMemory
from utils.user_context import get_user_token_file
from utils.quota import enforce_ai_quota

from .common import ai_service, AgentResult, _normalize_intent_text

logger = logging.getLogger(__name__)


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
        return max(1, min(int(match.group(1)), 50))

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
    count = max(1, min(int(count or 1), 50))
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
    quota_exhausted = False
    for email_id in email_ids:
        email = full_emails.get(email_id)
        if not email:
            logger.warning("Could not load full Gmail message %s", email_id)
            continue

        # Chat can request up to 50 emails in one message, so this loop is
        # the same 'email_summary' cost center as routes/email.py's batch
        # endpoint -- without this check a free user could summarize far
        # more than the advertised daily quota through chat alone.
        if enforce_ai_quota(user_id, 'email_summary'):
            quota_exhausted = True
            break

        summary = ai_service.summarize_email_polished(email, user_id=user_id)
        emails.append(email)
        index = len(emails)
        sections.append(
            f"{index}. {email.get('subject') or '(Không có tiêu đề)'}\n"
            f"Người gửi: {email.get('sender') or 'Không xác định'}\n"
            f"Thời gian: {email.get('date') or 'Không xác định'}\n\n"
            f"{summary}"
        )

    if not emails:
        if quota_exhausted:
            raise RuntimeError(
                'Bạn đã dùng hết lượt tóm tắt email AI miễn phí hôm nay. '
                'Nâng cấp Premium để tóm tắt không giới hạn.'
            )
        raise RuntimeError('Không thể tải nội dung đầy đủ của các email gần nhất.')

    heading = "EMAIL MỚI NHẤT" if len(emails) == 1 else f"{len(emails)} EMAIL GẦN NHẤT"
    body = f"{heading}\n\n" + "\n\n--------------------\n\n".join(sections)
    if quota_exhausted:
        body += (
            f"\n\n(Đã dừng ở {len(emails)} email do hết lượt tóm tắt email AI miễn phí hôm nay. "
            "Nâng cấp Premium để tóm tắt không giới hạn.)"
        )
    return body, emails


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


def _email_lookup_query(message):
    normalized = _normalize_intent_text(message)
    include_read = 'chua doc' not in normalized and 'unread' not in normalized
    parts = ['in:inbox' if include_read else 'is:unread']

    quoted = re.search(r'"([^"]{2,80})"', message or '')
    if quoted:
        parts.append(f'"{quoted.group(1).strip()}"')
    else:
        sender_match = re.search(r'(?:tu|from)\s+([\w\.-]+@[\w\.-]+\.\w+)', normalized)
        if sender_match:
            parts.append(f'from:{sender_match.group(1)}')

    exclusion = _email_exclusion_query_part(message)
    if exclusion:
        parts.append(exclusion)
    return ' '.join(parts), include_read


def _email_exclusion_query_part(message):
    """Preserve a simple explicit exclusion in Gmail search syntax."""
    normalized = _normalize_intent_text(message)
    match = re.search(
        r"\b(?:except|excluding|exclude|loai tru|tru)\s+"
        r"(?:email(?:s)?\s+|mail\s+)?([^,.;\n]{2,80})",
        normalized,
    )
    if not match:
        return ""
    value = re.sub(
        r"\b(?:please|nhe|giup minh|giup toi|cam on)\b.*$",
        "",
        match.group(1),
    ).strip(" \"'")
    return f'-"{value}"' if value else ""


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


def _query_override_from_entities(entities, message=None):
    """Build a Gmail query from AI/rule-classified entities: `query`
    (sender/keyword/unread_only) and/or `date_window` (a specific day or week
    the user asked about, e.g. "hom nay"), instead of re-parsing the raw
    message text with regex.
    """
    entities = entities or {}
    query_info = entities.get('query')
    date_window = entities.get('date_window')
    exclusion = _email_exclusion_query_part(message)
    if not isinstance(query_info, dict) and not date_window and not exclusion:
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
    if exclusion:
        parts.append(exclusion)

    if len(parts) == 1:
        return None
    return ' '.join(parts), include_read


def _direct_email_search_response(
    message,
    user_id,
    limit=8,
    query_override=None,
    return_emails=False,
):
    token_file = get_user_token_file(user_id)
    if not token_file or not os.path.exists(token_file):
        response = "Gmail chưa được kết nối, nên mình chưa thể xem email thật của bạn."
        return (response, []) if return_emails else response

    query, include_read = query_override or _email_lookup_query(message)
    emails = get_cached_gmail_service(token_file).get_emails(
        max_results=max(1, min(limit, 10)),
        query=query,
        include_read=include_read
    )
    if not emails:
        response = "Không tìm thấy email phù hợp trong Gmail theo dữ liệu hiện tại."
        return (response, []) if return_emails else response

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
    response = "\n".join(lines)
    return (response, emails) if return_emails else response


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


def _remember_email_result_map(ctx, emails):
    """Best-effort persistence for ordinal follow-ups in this chat only."""
    if not ctx.chat_session_id or not emails:
        return
    try:
        SessionMemory.remember_email_results(
            ctx.user_id,
            ctx.chat_session_id,
            emails,
            db_path=ctx.db_path,
            workspace_id=ctx.workspace_id,
        )
    except Exception:
        # A failed convenience-memory write must not hide real Gmail results.
        logger.warning(
            "Failed to remember Gmail result order for session %s",
            ctx.chat_session_id,
            exc_info=True,
        )


class EmailLatestSummaryAgent:
    """AGENT_CAPABILITIES: roughly 'email.inbox_triage' / 'overview.daily_brief'."""

    def handle(self, ctx):
        try:
            requested_count = int(
                (ctx.intent_result.get('entities') or {}).get('count')
                or _latest_email_count(ctx.user_message)
            )
            query_override = _query_override_from_entities(
                ctx.intent_result.get('entities'),
                message=ctx.user_message,
            )
            response, source_emails = _summarize_latest_emails(ctx.user_id, requested_count, query_override=query_override)
            _remember_email_result_map(ctx, source_emails)
            source_email = source_emails[0]
            suggested_actions = [
                _build_draft_reply_suggestion(email)
                for email in source_emails
                if _email_needs_reply(email)
            ]
            return AgentResult(
                response=response,
                provider='bob-local',
                demo_mode=False,
                suggested_actions=suggested_actions,
                workspace_sources=['email'],
                refresh_targets=ctx.refresh_targets,
                ai_used=False,
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


class EmailSearchAgent:
    """AGENT_CAPABILITIES: roughly 'email.inbox_triage'."""

    def handle(self, ctx):
        query_override = _query_override_from_entities(
            ctx.intent_result.get('entities'),
            message=ctx.user_message,
        )
        response, source_emails = _direct_email_search_response(
            ctx.user_message,
            ctx.user_id,
            query_override=query_override,
            return_emails=True,
        )
        _remember_email_result_map(ctx, source_emails)
        return AgentResult(
            response=response,
            workspace_sources=['email'],
            refresh_targets=ctx.refresh_targets,
            action='Tìm email trong Gmail',
        )


def _mark_emails(ctx, read):
    """Write tool -- always proposes which emails would be marked first,
    only calls Gmail's mark_as_read/unread once the user confirms (see
    tool_catalog.WRITE_TOOL_NAMES)."""
    if ctx.action_confirm and (ctx.action_override or {}).get('email_ids'):
        return _mark_emails_apply(ctx, read)
    return _mark_emails_propose(ctx, read)


_EMAIL_ORDINAL_WORDS = {
    'first': 1,
    'second': 2,
    'third': 3,
    'fourth': 4,
    'fifth': 5,
    'sixth': 6,
    'seventh': 7,
    'eighth': 8,
    'ninth': 9,
    'tenth': 10,
    'nhat': 1,
    'hai': 2,
    'ba': 3,
    'bon': 4,
    'tu': 4,
    'nam': 5,
    'sau': 6,
    'bay': 7,
    'tam': 8,
    'chin': 9,
    'muoi': 10,
}


def _email_result_reference(message):
    """Parse a reference to the ordered email list Bob just displayed."""
    raw_text = str(message or '').lower()
    text = _normalize_intent_text(message)
    numeric_patterns = (
        r'\b(?:cai|email|e-?mail|mail|message|tin nhan)\s+(?:so|thu)\s*#?\s*(\d{1,2})\b',
        r'\b(?:number|item|no\.?)\s*#?\s*(\d{1,2})\b',
        r'(?<!\w)#\s*(\d{1,2})\b',
        r'\b(\d{1,2})(?:st|nd|rd|th)\b',
    )
    for pattern in numeric_patterns:
        match = re.search(pattern, text)
        if match:
            return 'ordinal', int(match.group(1))

    word_match = re.search(
        r'\b(?:the\s+)?'
        r'(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)'
        r'(?:\s+(?:one|email|e-?mail|mail|message))?\b',
        text,
    )
    if word_match:
        return 'ordinal', _EMAIL_ORDINAL_WORDS[word_match.group(1)]

    vietnamese_word_match = re.search(
        r'\b(?:cai|email|e-?mail|mail|tin nhan)\s+thu\s+'
        r'(nhat|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi)\b',
        text,
    )
    if vietnamese_word_match:
        return 'ordinal', _EMAIL_ORDINAL_WORDS[vietnamese_word_match.group(1)]

    if re.search(
        r'\b(?:those|them|these(?:\s+(?:emails?|messages?))?|'
        r'cac\s+(?:email|thu)\s+do|nhung\s+cai\s+do|tat\s+ca\s+nhung\s+cai\s+do)\b',
        text,
    ):
        return 'all', None
    if re.search(
        r'\b(?:that\s+one|this\s+one|it|cai\s+do|cai\s+nay|email\s+do)\b',
        text,
    ) or re.search(r'\bnó\b', raw_text):
        return 'single', None
    return None


def _email_mark_proposal(targets, read, extra=""):
    label = 'đã đọc' if read else 'chưa đọc'
    titles = [email.get('title') or email.get('subject') or '(không có tiêu đề)' for email in targets]
    tool_name = 'email.mark_read' if read else 'email.mark_unread'
    return AgentResult(
        response=f"Mình sẽ đánh dấu {label}: {', '.join(titles)}.{extra} Xác nhận nhé?",
        pending_action={
            'tool': tool_name,
            'arguments': {
                'email_ids': [email.get('id') for email in targets],
                'titles': titles,
            },
        },
        workspace_sources=['email'],
        action=f"Đề xuất đánh dấu email {label}, cần xác nhận",
    )


def _email_reference_proposal(ctx, read):
    reference = _email_result_reference(
        ctx.original_user_message or ctx.user_message
    )
    if not reference:
        return None

    try:
        remembered = SessionMemory.get_email_results(
            ctx.user_id,
            ctx.chat_session_id,
            db_path=ctx.db_path,
            workspace_id=ctx.workspace_id,
        )
    except Exception:
        logger.warning(
            "Failed to load Gmail result order for session %s",
            ctx.chat_session_id,
            exc_info=True,
        )
        remembered = []
    if not remembered:
        return AgentResult(
            response=(
                "Mình chưa có danh sách email nào trong cuộc trò chuyện này để đối chiếu. "
                "Bạn hãy tìm hoặc liệt kê email trước, rồi chọn theo số thứ tự nhé."
            ),
            workspace_sources=['email'],
            action='Thiếu danh sách email trong phiên để tham chiếu',
        )

    kind, ordinal = reference
    if kind == 'ordinal':
        if ordinal < 1 or ordinal > len(remembered):
            return AgentResult(
                response=(
                    f"Danh sách email gần nhất trong cuộc trò chuyện này chỉ có "
                    f"{len(remembered)} mục, nên không có mục số {ordinal}."
                ),
                workspace_sources=['email'],
                action='Số thứ tự email nằm ngoài danh sách trong phiên',
            )
        targets = [remembered[ordinal - 1]]
    elif kind == 'all':
        targets = remembered
    elif len(remembered) == 1:
        targets = remembered
    else:
        return AgentResult(
            response=(
                f"Danh sách gần nhất có {len(remembered)} email. "
                "Bạn muốn đánh dấu email số mấy?"
            ),
            workspace_sources=['email'],
            action='Cần số thứ tự email rõ ràng',
        )
    return _email_mark_proposal(targets, read)


def _mark_emails_propose(ctx, read):
    token_file = get_user_token_file(ctx.user_id)
    if not token_file or not os.path.exists(token_file):
        return AgentResult(response="Gmail chưa được kết nối cho tài khoản này.", action='Gmail chưa kết nối')

    reference_result = _email_reference_proposal(ctx, read)
    if reference_result is not None:
        return reference_result

    query_override = _query_override_from_entities(
        ctx.intent_result.get('entities'),
        message=ctx.user_message,
    )
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
    extra = (
        f" (còn {len(emails) - len(targets)} email khác khớp, bạn nói rõ hơn để mình xử lý tiếp nếu cần)"
        if len(emails) > len(targets) else ""
    )
    return _email_mark_proposal(targets, read, extra=extra)


def _mark_emails_apply(ctx, read):
    token_file = get_user_token_file(ctx.user_id)
    if not token_file or not os.path.exists(token_file):
        return AgentResult(response="Gmail chưa được kết nối cho tài khoản này.", action='Gmail chưa kết nối')

    email_ids = ctx.action_override.get('email_ids') or []
    titles = ctx.action_override.get('titles') or []
    service = get_cached_gmail_service(token_file)

    marked = []
    for index, email_id in enumerate(email_ids):
        try:
            if read:
                service.mark_as_read(email_id)
            else:
                service.mark_as_unread(email_id)
            marked.append(titles[index] if index < len(titles) else email_id)
        except Exception:
            logger.exception("Failed to mark email %s as %s", email_id, 'read' if read else 'unread')

    if not marked:
        return AgentResult(
            response="Mình không đánh dấu được email nào, bạn thử lại sau nhé.",
            workspace_sources=['email'],
            action='Không đánh dấu được email',
        )

    from routes.email import _clear_email_list_cache
    _clear_email_list_cache(ctx.user_id)

    label = 'đã đọc' if read else 'chưa đọc'
    for title in marked:
        History.create(
            f"Đánh dấu email {label}: {title}",
            "Đánh dấu qua chat sau xác nhận",
            action_type='chat',
            db_path=ctx.db_path,
            workspace_id=ctx.workspace_id,
        )

    return AgentResult(
        response=f"Đã đánh dấu {label}: {', '.join(marked)}.",
        workspace_sources=['email'],
        refresh_targets=['email', 'overview', 'history'],
        action_applied={'tool': 'email.mark_read' if read else 'email.mark_unread', 'marked': marked},
        action=f"Đã đánh dấu email {label}",
    )


class EmailMarkReadAgent:
    """AGENT_CAPABILITIES: roughly 'email.inbox_triage'. Write tool --
    proposes before marking (see _mark_emails)."""

    def handle(self, ctx):
        return _mark_emails(ctx, read=True)


class EmailMarkUnreadAgent:
    """AGENT_CAPABILITIES: roughly 'email.inbox_triage'. Write tool --
    proposes before marking (see _mark_emails)."""

    def handle(self, ctx):
        return _mark_emails(ctx, read=False)
