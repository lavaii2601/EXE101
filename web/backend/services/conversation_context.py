"""Shared bilingual and multi-turn conversation helpers for Bob.

These helpers intentionally stay lightweight and deterministic.  They do not
try to translate or fully understand a message; they provide enough signals
for the intent classifier and response layer to make better use of the current
chat without allowing old turns to become new commands.
"""

import re
import unicodedata


_VIETNAMESE_CHAR_RE = re.compile(
    r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩị"
    r"óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# Function words carry more language signal than shared product vocabulary
# such as email, calendar, meeting, mode, checklist, or deadline.
_VI_WORDS = {
    "toi", "minh", "giup", "cho", "cua", "voi", "va", "khong",
    "duoc", "hay", "vui", "long", "hom", "ngay", "tuan", "luc", "gio",
    "sang", "chieu", "toi", "lich", "tim", "kiem", "xem", "tao", "doi",
    "xoa", "them", "cai", "nay", "kia", "nhu", "tren", "vay", "di",
    "roi", "chua", "nhung", "cac", "viec", "tra", "loi", "tieng", "viet",
    "anh", "co", "nao", "gap", "ko", "nhe", "nha", "xin", "chao", "cam",
}
_EN_WORDS = {
    "i", "me", "my", "mine", "you", "your", "yours", "we", "our", "the",
    "a", "an", "this", "that", "these", "those", "it", "them", "same",
    "please", "can", "could", "would", "should", "what", "when", "where",
    "how", "why", "with", "from", "about", "for", "and", "or", "not",
    "is", "are", "was", "were", "be", "been", "to", "of", "on", "in",
    "do", "does", "did", "need", "want", "have", "has", "now", "latest",
    "today", "tomorrow", "yesterday", "next", "last", "find", "show",
    "create", "move", "change", "delete", "remove", "summarize", "reply",
    "review", "status", "meeting", "deploy",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
    "read", "unread", "answer", "english", "vietnamese", "sender", "thanks",
}

_EXPLICIT_BILINGUAL = (
    "ca hai ngon ngu",
    "hai ngon ngu",
    "song ngu",
    "tieng viet va tieng anh",
    "tieng anh va tieng viet",
    "tieng viet va english",
    "english va tieng viet",
    "vietnamese va tieng anh",
    "tieng anh va vietnamese",
    "ca tieng viet va english",
    "both languages",
    "in both languages",
    "bilingual",
    "vietnamese and english",
    "english and vietnamese",
)
_EXPLICIT_ENGLISH = (
    "tra loi bang tieng anh",
    "tra loi bang english",
    "viet bang tieng anh",
    "noi tieng anh",
    "chuyen sang tieng anh",
    "answer in english",
    "reply in english",
    "respond in english",
    "in english",
    "english please",
    "switch to english",
)
_EXPLICIT_VIETNAMESE = (
    "tra loi bang tieng viet",
    "tra loi bang vietnamese",
    "viet bang tieng viet",
    "noi tieng viet",
    "chuyen sang tieng viet",
    "answer in vietnamese",
    "reply in vietnamese",
    "respond in vietnamese",
    "in vietnamese",
    "to vietnamese",
    "vietnamese please",
    "switch to vietnamese",
)

_CONTEXTUAL_PHRASES = (
    # Vietnamese references, ellipsis, corrections, and confirmations.
    "cai do", "cai nay", "cai thu hai", "cai dau tien", "cai cuoi cung",
    "lich do", "email do", "mail do", "viec do",
    "nhu tren", "nhu vua noi", "vua noi", "luc nay", "ban nay", "muc nay",
    "nguoi do", "gio do", "ngay do", "doi no", "xoa no", "lam no",
    "lam di", "lam luon di", "tiep tuc di", "cu lam di", "dung roi",
    "xac nhan", "dong y", "vay di", "the di", "con ngay mai", "con cai kia",
    "thay vao do", "thay vi", "doi sang", "chuyen sang", "sua thanh",
    "bo cai", "them vao do",
    # English references, ellipsis, corrections, and confirmations.
    "do it", "go ahead", "proceed", "confirm it", "yes do that",
    "that one", "this one", "the same one", "same one", "same time",
    "as above", "as discussed", "like before", "the previous one",
    "move it", "change it", "delete it", "remove it", "mark it",
    "those emails", "these emails", "that email", "that event",
    "that meeting", "instead", "what about tomorrow", "how about tomorrow",
    "add it", "put it", "drop it", "use that",
)

_SHORT_ACKS = {
    "ok", "okay", "yes", "yeah", "yep", "sure", "correct", "right",
    "fine", "done", "continue", "proceed", "confirm",
    "uh", "uhm", "um", "hmm",
    "duoc", "ok nha", "uh", "u", "vang", "roi", "dung", "dung roi",
    "dong y", "tiep tuc", "xac nhan",
}


def normalize_conversation_text(value):
    """Return lowercase accent-free text suitable for signal matching."""
    normalized = unicodedata.normalize("NFD", str(value or "").lower())
    normalized = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )
    normalized = normalized.replace("đ", "d")
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_phrase(text, phrases):
    return any(
        re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text)
        for phrase in phrases
    )


def detect_language_profile(message, fallback_language=None):
    """Describe the language and requested response style of one user turn.

    ``primary`` is always ``vi`` or ``en``.  A short language-neutral turn
    (for example ``OK``) inherits ``fallback_language`` when supplied.
    ``response_mode`` may additionally be ``bilingual`` when the user
    explicitly asks Bob to answer in both languages.
    """
    raw = str(message or "").strip()
    normalized = normalize_conversation_text(raw)
    tokens = _TOKEN_RE.findall(normalized)

    explicit_bilingual = _contains_phrase(normalized, _EXPLICIT_BILINGUAL)
    explicit_en = _contains_phrase(normalized, _EXPLICIT_ENGLISH)
    explicit_vi = _contains_phrase(normalized, _EXPLICIT_VIETNAMESE)

    vi_hits = sum(1 for token in tokens if token in _VI_WORDS)
    en_hits = sum(1 for token in tokens if token in _EN_WORDS)
    # Vietnamese diacritics are strong evidence, while still allowing a
    # mostly-English sentence containing a Vietnamese proper name to remain
    # English when its function-word signal is much stronger.
    vi_score = vi_hits + (2 if _VIETNAMESE_CHAR_RE.search(raw) else 0)
    en_score = en_hits
    if re.search(
        r"\b(?:ban|mark|move|delete|find|show|summarize)\s+"
        r"(?:this|that|these|those|the)\b",
        normalized,
    ):
        en_score += 2
    if re.search(r"\bco\b.+\bnao\b.+\b(?:ko|khong)\b", normalized):
        vi_score += 2

    fallback = fallback_language if fallback_language in {"vi", "en"} else None
    normalized_ack = normalized.strip(" .,!?:;")
    language_neutral = not raw or normalized_ack in _SHORT_ACKS

    if explicit_en and not explicit_vi:
        primary = "en"
    elif explicit_vi and not explicit_en:
        primary = "vi"
    elif language_neutral and fallback:
        primary = fallback
    elif en_score >= vi_score + 2:
        primary = "en"
    elif vi_score > 0:
        primary = "vi"
    elif en_score > 0 or re.search(r"[a-zA-Z]", raw):
        primary = "en"
    else:
        primary = fallback or "vi"

    mixed = vi_score > 0 and en_score > 0
    signal_total = vi_score + en_score
    if language_neutral and not fallback:
        confidence = 0.0
    elif signal_total:
        confidence = min(1.0, max(vi_score, en_score) / signal_total)
    elif primary == "en" and re.search(r"[a-zA-Z]", raw):
        # A terse ASCII English turn may contain only proper nouns/technical
        # terms. It is still a clearer session-language signal than an ack.
        confidence = 0.5
    else:
        confidence = 0.0
    response_mode = "bilingual" if explicit_bilingual else primary
    return {
        "primary": primary,
        "mixed": mixed,
        "code_switched": mixed,
        "response_mode": response_mode,
        "explicit": bool(explicit_bilingual or explicit_en or explicit_vi),
        "vi_score": vi_score,
        "en_score": en_score,
        "confidence": round(confidence, 3),
        "inherited": bool(language_neutral and fallback),
    }


def is_context_dependent_followup(message):
    """Return True when a turn likely needs earlier turns to make sense.

    This signal does not authorize an action.  It only allows the classifier
    to inspect the current session; existing confirmation gates still apply.
    """
    raw = str(message or "").strip().lower()
    normalized = normalize_conversation_text(message).strip(" .,!?:;")
    if not normalized:
        return False
    tokens = _TOKEN_RE.findall(normalized)
    if normalized in _SHORT_ACKS:
        return True
    if _contains_phrase(normalized, _CONTEXTUAL_PHRASES):
        return True
    # Object references may appear in the middle of an otherwise complete
    # action sentence.  They still need the previous result set to resolve
    # safely (for example, "mark the second one unread").
    if re.search(
        r"\b(?:the\s+)?(?:first|second|third|last|previous)\s+"
        r"(?:one|ones|email|emails|message|messages|event|events|item|items)\b",
        normalized,
    ):
        return True
    if re.search(
        r"\b(?:mark|move|change|delete|remove|archive|open|summarize|reply\s+to)"
        r"\s+(?:this|that|these|those|it|them)\b",
        normalized,
    ):
        return True
    if re.search(
        r"\b(?:danh dau|doi|xoa|bo|luu tru|mo|tom tat|tra loi)\s+"
        r"(?:cai|no|chung|nhung cai|may cai)\b",
        normalized,
    ):
        return True
    if re.search(
        r"\b(?:cai\s+)?thu\s+(?:1|2|3|nhat|hai|ba)\b",
        normalized,
    ):
        return True
    if len(tokens) <= 10 and re.match(
        r"^(?:con|vay|roi|va|and|but|so|what about|how about)\b",
        normalized,
    ):
        return True
    # Keep the Vietnamese discourse marker "thế" without confusing it with
    # the English article "the".
    if len(tokens) <= 10 and re.match(r"^th\u1ebf\b", raw):
        return True
    # Short amendments often omit the original object: "at 3pm instead",
    # "sang 3 giờ nhé", "tomorrow then".
    if len(tokens) <= 8 and (
        re.search(r"\b(?:instead|thay vi|doi sang|chuyen sang|sua thanh)\b", normalized)
        or re.match(r"^(?:at|vao|luc|sang)\s+\d", normalized)
    ):
        return True
    return False


def latest_user_language(records, default="vi"):
    """Infer the last clear user language from newest-first history rows."""
    fallback = default if default in {"vi", "en"} else "vi"
    for record in records or ():
        if record.get("action_type") != "chat":
            continue
        text = str(record.get("user_message") or "").strip()
        if not text:
            continue
        profile = detect_language_profile(text)
        if profile["confidence"] >= 0.45:
            return profile["primary"]
    return fallback
