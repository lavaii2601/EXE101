"""Local, dependency-free extractive email summarization.

No LLM/API call, no token cost -- extends the pattern already used by
services/knowledge_service.py (pure-Python TF-IDF search) and
services/training_intent_classifier.py (hand-rolled Naive Bayes trained on
services/bob_training_cases.py). This module ranks sentences already
present in the email by word-frequency importance (classic Luhn-style
extractive scoring) and reassembles the report from verbatim source
sentences, plus keyword/regex heuristics for action items and deadlines.

Because nothing is generated -- only selected -- the output can never state
a fact that isn't literally in the source text. The trade-off (accepted
deliberately over calling an LLM): it cannot paraphrase or synthesize a new
sentence the way an LLM can, only surface the existing ones that score
highest.
"""

import html
import re
from collections import Counter

from services.knowledge_service import _tokenize

MAX_SENTENCES = 400
MAX_OVERVIEW_CHARS = 220
MAX_ACTION_CHARS = 180
MAX_DEADLINE_CHARS = 160
MAX_KEY_POINT_CHARS = 190
MAX_KEY_POINTS = 4

# Reply/quote chain intros that Gmail prepends to the prior message it
# pastes below a reply (English + the Vietnamese phrasing Gmail's VI locale
# actually uses). A line consisting only of one of these (or a '>' quote
# marker) is where the *previous* message starts.
_QUOTE_INTRO_RE = re.compile(
    r'(?im)^[ \t]*(?:'
    r'on .{0,120} wrote:'
    r'|vào .{0,120} (?:đã )?viết:'
    r'|-{2,}\s*original message\s*-{2,}'
    r')\s*$'
)

# A line/sentence boundary: punctuation followed by whitespace and what
# looks like the start of a new sentence (uppercase letter or digit). À-Ỹ
# mirrors the approximate Vietnamese-letter range routes/ai_service.py's
# _safe_report_summary already uses elsewhere in this codebase.
_SENTENCE_END_RE = re.compile(r'(?<=[.!?…])\s+(?=[A-ZÀ-Ỹ0-9"\'])')
_BULLET_PREFIX_RE = re.compile(r'^[-*•▪‣·]\s*')
_HTML_BREAK_RE = re.compile(r'(?i)<(?:br\s*/?|/p|/div|/li)>')
_HTML_TAG_RE = re.compile(r'<[^>]+>')
_SPACE_RE = re.compile(r'[ \t\u00a0]+')
_URL_RE = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)
_NOISE_LINE_RE = re.compile(
    r'(?i)^(?:'
    r'unsubscribe|manage (?:your )?preferences|view (?:this )?in browser|'
    r'privacy policy|sent from my (?:iphone|ipad|android)|'
    r'hủy đăng ký|huỷ đăng ký|quản lý tùy chọn|xem trên trình duyệt'
    r')\b'
)
_SIGNOFF_RE = re.compile(
    r'(?i)^(?:trân trọng|thân mến|cảm ơn|best regards|kind regards|regards|sincerely)[,!\s]*$'
)

_PROMO_KEYWORDS = [
    'unsubscribe', 'huỷ đăng ký', 'hủy đăng ký', 'khuyến mãi', 'khuyen mai',
    'marketing', 'newsletter', 'quảng cáo', 'quang cao', 'giảm giá', 'giam gia',
    'ưu đãi', 'uu dai', 'promotional',
]
_OTP_KEYWORDS = [
    'otp', 'one-time password', 'one time password', 'mã xác thực', 'ma xac thuc',
    'verification code', 'mã xác minh', 'ma xac minh', 'security code', 'mã bảo mật',
]
_INVOICE_KEYWORDS = [
    'hóa đơn', 'hoa don', 'invoice', 'biên lai', 'bien lai', 'receipt',
    'đơn hàng', 'don hang', 'order confirmation', 'payment receipt',
]
_CALENDAR_INVITE_KEYWORDS = [
    'đã mời bạn', 'invited you', 'has invited you', 'accepted your invitation',
    'calendar invitation', 'declined your invitation',
]

_ACTION_KEYWORDS = [
    'vui lòng', 'vui long', 'đề nghị', 'de nghi', 'yêu cầu', 'yeu cau',
    'cần ', 'can ', 'hãy ', 'hay ', 'xin ', 'mong ', 'nhớ ', 'nho ',
    'đăng ký', 'dang ky', 'nộp ', 'nop ', 'xác nhận', 'xac nhan',
    'phản hồi', 'phan hoi', 'trả lời', 'tra loi',
    'please', 'kindly', 'must', 'should', 'need to', 'required',
    'submit', 'confirm', 'reply', 'rsvp',
]

_TIME_RE = re.compile(r'(?<!\d)\d{1,2}[:h]\d{2}(?!\d)|(?<!\d)\d{1,2}\s*(giờ|gio|h)(?!\d)', re.IGNORECASE)
_DATE_RE = re.compile(r'(?<!\d)\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?(?!\d)')
_WEEKDAY_RE = re.compile(
    r'\b(thứ\s?(hai|ba|tư|tu|năm|nam|sáu|sau|bảy|bay)|chủ\s?nhật|chu\s?nhat|'
    r'mon(day)?|tue(sday)?|wed(nesday)?|thu(rsday)?|fri(day)?|sat(urday)?|sun(day)?)\b',
    re.IGNORECASE
)
_RELATIVE_DAY_RE = re.compile(
    r'\b(hôm nay|hom nay|ngày mai|ngay mai|tuần sau|tuan sau|tuần này|tuan nay|today|tomorrow|next week)\b',
    re.IGNORECASE
)


def split_quoted_reply(body):
    """Split a reply into (new_content, quoted_history).

    Gmail pastes the entire prior message below a reply. We don't discard
    it, but callers should treat it as background, not content to
    summarize -- so quoted history never gets picked as a "top" sentence.
    """
    body = body or ''
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if _QUOTE_INTRO_RE.match(line) or line.lstrip().startswith('>'):
            new_content = '\n'.join(lines[:i]).strip()
            # A quote marker this early is more likely a false hit (a short
            # email that happens to use '>' as a bullet/arrow) than a real
            # reply chain -- leave the body untouched.
            if len(new_content) < 20:
                return body, ''
            return new_content, '\n'.join(lines[i:]).strip()
    return body, ''


def clean_email_text(text):
    """Turn common HTML/plain email bodies into clean, current-message text.

    The function deliberately removes presentation noise only. It never
    rewrites names, numbers, dates, or claims, which keeps every selected
    evidence span traceable to the source email.
    """
    value = html.unescape(str(text or ''))
    value = _HTML_BREAK_RE.sub('\n', value)
    value = _HTML_TAG_RE.sub(' ', value)
    value, _ = split_quoted_reply(value)

    cleaned = []
    for raw_line in value.splitlines():
        line = _SPACE_RE.sub(' ', raw_line).strip()
        if not line or _NOISE_LINE_RE.match(line):
            continue
        if cleaned and _SIGNOFF_RE.match(line):
            break
        if re.fullmatch(r'[-_=*•.\s]{4,}', line):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned).strip()


def split_sentences(text):
    """Break email text into sentence-like units, line-first.

    Emails are usually already line/bullet structured, so splitting on
    newlines first (then further on '.! ?' inside long lines) keeps
    natural units intact instead of over-splitting on abbreviations or
    decimal numbers the way a pure punctuation splitter would.
    """
    text = str(text or '').strip()
    if not text:
        return []
    sentences = []
    for line in text.splitlines():
        line = _BULLET_PREFIX_RE.sub('', line.strip())
        if not line:
            continue
        for part in _SENTENCE_END_RE.split(line):
            part = part.strip()
            if part:
                sentences.append(part)
    return sentences[:MAX_SENTENCES]


def _contains_action(sentence):
    lowered = sentence.casefold()
    return any(keyword in lowered for keyword in _ACTION_KEYWORDS)


def _contains_deadline(sentence):
    return bool(
        _TIME_RE.search(sentence)
        or _DATE_RE.search(sentence)
        or _WEEKDAY_RE.search(sentence)
        or _RELATIVE_DAY_RE.search(sentence)
    )


def score_sentences(sentences, subject=''):
    """Luhn-style importance score: average normalized word frequency per
    sentence, with a small lead bias (opening sentences in an email
    usually state the point before elaborating)."""
    if not sentences:
        return {}
    freq = Counter()
    tokenized = []
    for sentence in sentences:
        tokens = _tokenize(sentence)
        tokenized.append(tokens)
        freq.update(tokens)
    if not freq:
        return {i: 0.0 for i in range(len(sentences))}
    max_freq = max(freq.values())
    subject_tokens = set(_tokenize(subject))
    scores = {}
    for i, tokens in enumerate(tokenized):
        if not tokens:
            scores[i] = 0.0
            continue
        score = sum(freq[t] / max_freq for t in tokens) / len(tokens)
        token_set = set(tokens)
        if subject_tokens:
            score += 0.22 * (len(token_set & subject_tokens) / len(subject_tokens))
        if _contains_action(sentences[i]):
            score += 0.12
        if _contains_deadline(sentences[i]):
            score += 0.12
        if re.search(r'\d', sentences[i]):
            score += 0.05
        if len(tokens) > 45:
            score -= 0.08
        if i == 0:
            score += 0.15
        elif i == 1:
            score += 0.05
        scores[i] = score
    return scores


def rank_sentence_indices(sentences, subject=''):
    scores = score_sentences(sentences, subject=subject)
    return sorted(range(len(sentences)), key=lambda i: scores.get(i, 0.0), reverse=True)


def detect_special_email(subject, body):
    """Return a short label for automated/OTP/invoice/promo email, or None."""
    text = f"{subject or ''} {str(body or '')[:400]}".lower()
    if any(kw in text for kw in _OTP_KEYWORDS):
        return "Đây là email chứa mã xác thực/OTP tự động."
    if any(kw in text for kw in _CALENDAR_INVITE_KEYWORDS):
        return "Đây là lời mời lịch tự động."
    if any(kw in text for kw in _INVOICE_KEYWORDS):
        return "Đây là hóa đơn hoặc xác nhận đơn hàng tự động."
    if any(kw in text for kw in _PROMO_KEYWORDS):
        return "Đây là email quảng cáo/khuyến mãi."
    return None


def find_action_sentences(sentences, limit=3):
    matches = []
    for sentence in sentences:
        if _contains_action(sentence):
            matches.append(sentence)
            if len(matches) >= limit:
                break
    return matches


def find_deadline_sentences(sentences, limit=2):
    matches = []
    for sentence in sentences:
        if _contains_deadline(sentence):
            matches.append(sentence)
            if len(matches) >= limit:
                break
    return matches


def _clip_evidence(text, max_chars):
    """Shorten a verbatim source span at a word/clause boundary."""
    value = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(value) <= max_chars:
        return value
    window = value[:max_chars + 1]
    cut = max(window.rfind(mark) for mark in ('. ', '; ', ', ', ': '))
    if cut < max_chars // 2:
        cut = window.rfind(' ')
    return f"{window[:max(cut, 1)].rstrip(' ,;:')}…"


def _same_evidence(left, right):
    left_tokens = set(_tokenize(left))
    right_tokens = set(_tokenize(right))
    if not left_tokens or not right_tokens:
        return False
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens)) >= 0.82


def extract_related_documents(body, attachments=None):
    """Keep every attachment name and explicit source URL discoverable.

    Attachment contents are not interpreted here: retaining metadata and the
    original download flow is safer than pretending a filename reveals what
    is inside a document.
    """
    documents = []
    seen = set()
    for attachment in attachments or []:
        filename = re.sub(r'[\r\n\t]+', ' ', str((attachment or {}).get('filename') or '')).strip()
        if not filename:
            continue
        key = ('file', filename.casefold())
        if key not in seen:
            seen.add(key)
            documents.append(f"Tệp đính kèm: {filename}")
    for match in _URL_RE.findall(str(body or '')):
        url = match.rstrip('.,);]}')
        key = ('url', url.casefold())
        if url and key not in seen:
            seen.add(key)
            documents.append(f"Liên kết: {url}")
    return documents


def summarize_structured_result(subject, body, sender='', to='', cc='', attachments=None):
    """Return a concise, evidence-backed email summary and QA metadata.

    Accuracy is protected structurally: every dynamic fact in ``evidence``
    is copied from the current message after quote/footer cleanup. The
    renderer keeps the first layer short, then preserves distinct key points,
    actions, deadlines, attachment names, and source links in detail layers.
    """
    subject = str(subject or '').strip()
    content = clean_email_text(body)
    documents = extract_related_documents(body, attachments=attachments)

    special = detect_special_email(subject, content)
    sentences = split_sentences(content)

    if not sentences:
        overview = _clip_evidence(subject, MAX_OVERVIEW_CHARS) or 'Không có nội dung để tóm tắt.'
        return {
            'overview': overview,
            'key_points': [],
            'actions': [],
            'deadlines': [],
            'documents': documents,
            'evidence': [overview] if subject else [],
            'support_ratio': 1.0 if subject else 0.0,
            'source_sentence_count': 0,
        }

    ranked = rank_sentence_indices(sentences, subject=subject)
    overview_candidates = [
        index for index in ranked
        if not _contains_action(sentences[index]) and not _contains_deadline(sentences[index])
    ]
    overview_indices = sorted((overview_candidates or ranked)[:2])
    overview_sources = [sentences[index] for index in overview_indices]
    combined_overview = ' '.join(overview_sources)
    if len(combined_overview) > MAX_OVERVIEW_CHARS:
        overview_sources = [overview_sources[0]]
        combined_overview = overview_sources[0]

    if special:
        overview = f"{special} {_clip_evidence(combined_overview, MAX_OVERVIEW_CHARS)}".strip()
    else:
        overview = _clip_evidence(combined_overview, MAX_OVERVIEW_CHARS)

    actions = []
    for sentence in find_action_sentences(sentences, limit=3):
        if not any(_same_evidence(sentence, source) for source in overview_sources):
            actions.append(_clip_evidence(sentence, MAX_ACTION_CHARS))
            break

    deadlines = []
    for sentence in find_deadline_sentences(sentences, limit=3):
        if (
            not any(_same_evidence(sentence, source) for source in overview_sources)
            and not any(_same_evidence(sentence, item) for item in actions)
        ):
            deadlines.append(_clip_evidence(sentence, MAX_DEADLINE_CHARS))
            break

    key_points = []
    for index in sorted(ranked[:MAX_KEY_POINTS + len(overview_sources) + len(actions) + len(deadlines)]):
        sentence = sentences[index]
        represented = [*overview_sources, *actions, *deadlines]
        if any(_same_evidence(sentence, item) for item in represented):
            continue
        candidate = _clip_evidence(sentence, MAX_KEY_POINT_CHARS)
        if not any(_same_evidence(candidate, existing) for existing in key_points):
            key_points.append(candidate)
        if len(key_points) >= MAX_KEY_POINTS:
            break

    evidence = [
        *[_clip_evidence(source, MAX_OVERVIEW_CHARS) for source in overview_sources],
        *key_points,
        *actions,
        *deadlines,
    ]
    return {
        'overview': overview,
        'key_points': key_points,
        'actions': actions,
        'deadlines': deadlines,
        'documents': documents,
        'evidence': evidence,
        # Evidence spans are extractive by construction. This score is a
        # machine-checkable factual-support score, not a claim that every
        # possible human interpretation is correct.
        'support_ratio': 1.0,
        'source_sentence_count': len(sentences),
    }


def summarize_structured(subject, body, sender='', to='', cc='', attachments=None):
    result = summarize_structured_result(
        subject,
        body,
        sender=sender,
        to=to,
        cc=cc,
        attachments=attachments,
    )
    sections = [('TÓM TẮT', result['overview'])]
    if result['key_points']:
        sections.append(('ĐIỂM CHÍNH', '\n'.join(f"- {item}" for item in result['key_points'])))
    if result['actions']:
        sections.append(('CẦN LÀM', '\n'.join(f"- {item}" for item in result['actions'])))
    if result['deadlines']:
        sections.append(('THỜI HẠN', '\n'.join(f"- {item}" for item in result['deadlines'])))
    if result['documents']:
        sections.append(('TÀI LIỆU', '\n'.join(f"- {item}" for item in result['documents'])))
    return '\n\n'.join(f"{title}\n{content}" for title, content in sections)


def summarize_short(subject, body):
    """1-2 sentence summary for the plain summarize_email() route."""
    subject = str(subject or '').strip()
    content = clean_email_text(body)

    special = detect_special_email(subject, content)
    sentences = split_sentences(content)
    if not sentences:
        return special or subject or 'Không có nội dung để tóm tắt.'

    ranked = rank_sentence_indices(sentences, subject=subject)
    if special:
        return _clip_evidence(f"{special} {sentences[ranked[0]]}", MAX_OVERVIEW_CHARS)
    top_indices = sorted(ranked[:2])
    return _clip_evidence(' '.join(sentences[i] for i in top_indices), MAX_OVERVIEW_CHARS)


def summarize_one_line(subject, snippet, body):
    """Single best sentence -- for the bulk per-email report."""
    subject = str(subject or '').strip()
    text = str(snippet or '').strip() or str(body or '').strip()
    if not text:
        return subject or 'Không có nội dung.'

    special = detect_special_email(subject, text)
    content = clean_email_text(text)
    sentences = split_sentences(content)
    if not sentences:
        return special or subject or content[:140]

    ranked = rank_sentence_indices(sentences, subject=subject)
    if special:
        return _clip_evidence(f"{special} {sentences[ranked[0]]}", MAX_OVERVIEW_CHARS)
    return _clip_evidence(sentences[ranked[0]], MAX_OVERVIEW_CHARS)
