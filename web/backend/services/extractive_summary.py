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

import re
from collections import Counter

from services.knowledge_service import _tokenize

MAX_SENTENCES = 400

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


def score_sentences(sentences):
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
    scores = {}
    for i, tokens in enumerate(tokenized):
        if not tokens:
            scores[i] = 0.0
            continue
        score = sum(freq[t] / max_freq for t in tokens) / len(tokens)
        if i == 0:
            score += 0.15
        elif i == 1:
            score += 0.05
        scores[i] = score
    return scores


def rank_sentence_indices(sentences):
    scores = score_sentences(sentences)
    return sorted(range(len(sentences)), key=lambda i: scores.get(i, 0.0), reverse=True)


def detect_special_email(subject, body):
    """Return a short label for automated/OTP/invoice/promo email, or None."""
    text = f"{subject or ''} {str(body or '')[:400]}".lower()
    if any(kw in text for kw in _OTP_KEYWORDS):
        return "Day la email chua ma xac thuc/OTP tu dong."
    if any(kw in text for kw in _CALENDAR_INVITE_KEYWORDS):
        return "Day la loi moi lich (calendar invite) tu dong."
    if any(kw in text for kw in _INVOICE_KEYWORDS):
        return "Day la hoa don/xac nhan don hang tu dong."
    if any(kw in text for kw in _PROMO_KEYWORDS):
        return "Day la email quang cao/khuyen mai."
    return None


def find_action_sentences(sentences, limit=3):
    matches = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(kw in lowered for kw in _ACTION_KEYWORDS):
            matches.append(sentence)
            if len(matches) >= limit:
                break
    return matches


def find_deadline_sentences(sentences, limit=2):
    matches = []
    for sentence in sentences:
        if (_TIME_RE.search(sentence) or _DATE_RE.search(sentence)
                or _WEEKDAY_RE.search(sentence) or _RELATIVE_DAY_RE.search(sentence)):
            matches.append(sentence)
            if len(matches) >= limit:
                break
    return matches


def summarize_structured(subject, body, sender='', to='', cc=''):
    """Adaptive report: TOM TAT always, plus DIEM QUAN TRONG / VIEC CAN LAM /
    THOI HAN-UU TIEN only when the email actually has content for them.

    Earlier versions always printed all 4 sections, padding empty ones with
    'Khong co.' -- a one-line 'thanks' reply and a dense multi-topic email
    both came out as the same fixed 4-block shape. Shaping the output to
    what's actually there keeps simple emails short instead of templated."""
    subject = str(subject or '').strip()
    body = str(body or '').strip()
    new_content, _ = split_quoted_reply(body)
    content = new_content or body

    special = detect_special_email(subject, content)
    sentences = split_sentences(content)

    if not sentences:
        return f"TOM TAT\n{subject or 'Khong co noi dung de tom tat.'}"

    ranked = rank_sentence_indices(sentences)

    if special:
        top_sentence = sentences[ranked[0]]
        tom_tat = f"{special} {top_sentence}".strip()
    else:
        top_indices = sorted(ranked[:2])
        tom_tat = ' '.join(sentences[i] for i in top_indices)
    if cc:
        tom_tat += " (Email nay co CC them nguoi khac.)"

    sections = [("TOM TAT", tom_tat)]

    important_indices = sorted(ranked[:4])
    important = [sentences[i] for i in important_indices if sentences[i] not in tom_tat][:3]
    if important:
        sections.append(("DIEM QUAN TRONG", '\n'.join(f"- {s}" for s in important)))

    # Action/deadline sentences may legitimately overlap each other (a
    # sentence can be both an ask and time-bound), but repeating the exact
    # same line already shown in TOM TAT reads as sloppy, not just redundant.
    actions = [s for s in find_action_sentences(sentences) if s not in tom_tat]
    if actions:
        sections.append(("VIEC CAN LAM", '\n'.join(f"- {s}" for s in actions)))

    deadlines = [s for s in find_deadline_sentences(sentences) if s not in tom_tat]
    if deadlines:
        sections.append(("THOI HAN / UU TIEN", '\n'.join(f"- {s}" for s in deadlines)))

    return "\n\n".join(f"{title}\n{block}" for title, block in sections)


def summarize_short(subject, body):
    """1-2 sentence summary for the plain summarize_email() route."""
    subject = str(subject or '').strip()
    body = str(body or '').strip()
    new_content, _ = split_quoted_reply(body)
    content = new_content or body

    special = detect_special_email(subject, content)
    if special:
        return special

    sentences = split_sentences(content)
    if not sentences:
        return subject or 'Khong co noi dung de tom tat.'

    ranked = rank_sentence_indices(sentences)
    top_indices = sorted(ranked[:2])
    return ' '.join(sentences[i] for i in top_indices)


def summarize_one_line(subject, snippet, body):
    """Single best sentence -- for the bulk per-email report."""
    subject = str(subject or '').strip()
    text = str(snippet or '').strip() or str(body or '').strip()
    if not text:
        return subject or 'Khong co noi dung.'

    special = detect_special_email(subject, text)
    if special:
        return special

    new_content, _ = split_quoted_reply(text)
    content = new_content or text
    sentences = split_sentences(content)
    if not sentences:
        return subject or content[:140]

    ranked = rank_sentence_indices(sentences)
    return sentences[ranked[0]]
