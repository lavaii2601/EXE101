import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta

from models.history import History
from models.schedule import LOCAL_TZ, Schedule
from models.user import User
from services import tool_catalog
from services.conversation_context import is_context_dependent_followup
from services.schedule_service import ScheduleService

logger = logging.getLogger(__name__)


def _format_user_datetime(value, fallback="khong ro thoi gian"):
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return fallback
    return parsed.strftime("%d/%m/%Y. %H:%M")


class IntentOrchestrator:
    """Normalize user prompts into canonical workspace actions."""

    # Sourced from services/tool_catalog.py -- the single place that lists
    # every capability Bob supports. See that module for how to add a new one.
    AI_INTENTS = tool_catalog.TOOL_NAMES + ("chat.freeform",)

    # Intents safe for the AI-classification cache (services/
    # intent_pattern_cache.py) to short-circuit: every one of these always
    # shows the user a suggestion/confirmation before anything is written.
    # A wrong cache hit here can then only ever produce a rejectable
    # suggestion, never a silent wrong write -- unlike an intent that would
    # write immediately, which must always go through the AI when rules are
    # unsure, never the cache. See tool_catalog.Tool.cacheable.
    CACHEABLE_INTENTS = tool_catalog.CACHEABLE_INTENTS

    WEEKDAY_NAMES_VN = (
        "Thu Hai", "Thu Ba", "Thu Tu", "Thu Nam", "Thu Sau", "Thu Bay", "Chu Nhat",
    )

    @staticmethod
    def _local_now():
        """Naive Vietnam-local time used by existing schedule ISO contracts."""
        return datetime.now(LOCAL_TZ).replace(tzinfo=None)

    MODE_ALIASES = {
        "student": ("student", "sinh vien", "hoc sinh", "di hoc", "college student", "university student"),
        "worker": ("worker", "nhan vien", "di lam", "cong so", "van phong", "office worker", "employee"),
        "freelancer": ("freelancer", "tu do", "lam freelance", "freelance", "contractor", "independent worker"),
        "creator": ("creator", "sang tao", "content", "creator", "content creator", "influencer"),
        "business": ("business", "kinh doanh", "doanh nghiep", "chu doanh nghiep", "entrepreneur", "founder", "owner"),
        "mentor": ("mentor", "co van", "huong dan", "coach", "advisor"),
        "teacher": ("teacher", "giao vien", "giang vien", "day hoc", "lecturer", "instructor", "professor"),
    }

    MODE_LABELS = {
        "student": "Student",
        "worker": "Worker",
        "freelancer": "Freelancer",
        "creator": "Creator",
        "business": "Business",
        "mentor": "Mentor",
        "teacher": "Teacher",
    }

    _KNOWLEDGE_QUESTION_RE = re.compile(
        r"^(?:ai\s+(?:la|so huu|sang lap|tao ra|dieu hanh)|"
        r"(?:chu|nguoi sang lap|nha sang lap|ceo)\s+(?:cua\s+)?|"
        r"lich su\s+(?:cua\s+)?|"
        r"who\s+(?:is|owns|owned|founded|created|runs|leads)|"
        r"what\s+is\s+the\s+(?:owner|founder|history)\s+of)",
        re.IGNORECASE,
    )
    _EXPLICIT_WORKSPACE_COMMANDS = (
        "tao lich", "dat lich", "them lich", "xep lich", "nhac toi",
        "schedule", "book a meeting", "book an appointment", "remind me",
        "them vao checklist", "dua vao checklist", "create a checklist",
        "tim email", "kiem email", "search email", "find email",
        "danh dau email", "mark email", "doi che do", "change mode",
    )

    def detect(self, message):
        text = self.normalize(message)
        entities = {}
        intent = "chat.freeform"
        confidence = 0.35
        requires_confirmation = False
        refresh_targets = []

        # General knowledge questions must be resolved before keyword-based
        # workspace routing. This blocks names such as Facebook (contains
        # "book"), Eventbrite (contains "event") or Gmail from becoming a
        # calendar/email action when the user merely asks who owns/founded it.
        if self.is_general_knowledge_question(message):
            return {
                "intent": intent,
                "confidence": 0.98,
                "entities": entities,
                "requires_confirmation": requires_confirmation,
                "refresh_targets": refresh_targets,
                "knowledge_question": True,
            }

        # Explicit state-changing email verbs take precedence over modifiers
        # such as "latest"; "mark the latest 3 emails unread" is not a
        # request to summarize those emails.
        if self._is_email_mark_read(text):
            intent = "email.mark_read"
            confidence = 0.8
            date_window = self._email_date_window(text)
            if date_window:
                entities["date_window"] = date_window
            refresh_targets = ["email", "overview", "history"]
        elif self._is_email_mark_unread(text):
            intent = "email.mark_unread"
            confidence = 0.8
            date_window = self._email_date_window(text)
            if date_window:
                entities["date_window"] = date_window
            refresh_targets = ["email", "overview", "history"]
        elif self._is_latest_email_summary(text):
            intent = "email.latest_summary"
            confidence = 0.93
            entities["count"] = self._latest_email_count(text)
            date_window = self._email_date_window(text)
            if date_window:
                entities["date_window"] = date_window
            refresh_targets = ["email", "overview", "history"]
        elif self._is_mode_update(text):
            intent = "settings.update_mode"
            confidence = 0.9
            entities["mode"] = self._mode_from_text(text)
            refresh_targets = ["settings", "profile", "history"]
        elif self._is_day_plan_request(text):
            intent = "schedule.suggest_plan"
            # No entity extraction here on purpose -- the agent re-runs the
            # same day-plan engine (_build_suggested_day_plan) against the
            # raw message itself, which needs db access (busy-slot lookup)
            # this orchestrator doesn't have. This is just the routing
            # decision: "the user wants time-slotted calendar suggestions
            # for a list of activities", not "a flat checklist".
            confidence = 0.82
            refresh_targets = ["schedule", "calendar", "overview", "history"]
        elif self._is_checklist_request(text):
            intent = "checklist.create"
            # Kept just below the AI-assist threshold on purpose: detecting
            # "this is a checklist request" from keywords is reliable, but
            # splitting the actual item list out of a messy chat sentence
            # (leading "hom nay minh co...", trailing "giup minh nhe") is
            # not -- so we always let the AI pass re-extract clean items
            # rather than trusting the regex split here as final.
            confidence = 0.55
            entities["items"] = self._checklist_items_from_text(message)
            refresh_targets = ["overview", "history"]
        elif self._is_history_lookup(text):
            intent = "history.list"
            confidence = 0.86
            entities["limit"] = self._limit_from_text(text, default=8, maximum=100)
            refresh_targets = ["history"]
        elif self._is_schedule_create(text):
            intent = "schedule.create"
            confidence = 0.88
            entities["schedule"] = self.extract_schedule(message)
            requires_confirmation = True
            refresh_targets = ["schedule", "calendar", "overview", "history"]
        elif self._is_schedule_update(text):
            intent = "schedule.update"
            confidence = 0.8
            entities["new_values"] = self.extract_schedule(message)
            requires_confirmation = True
            refresh_targets = ["schedule", "calendar", "overview", "history"]
        elif self._is_schedule_delete(text):
            intent = "schedule.delete"
            confidence = 0.8
            requires_confirmation = True
            refresh_targets = ["schedule", "calendar", "overview", "history"]
        elif self._is_schedule_lookup(text):
            intent = "schedule.list"
            confidence = 0.82
            entities["window"] = self._calendar_window(text)
            refresh_targets = ["schedule", "calendar", "overview", "history"]
        elif self._is_email_lookup(text):
            intent = "email.search"
            confidence = 0.74
            date_window = self._email_date_window(text)
            if date_window:
                entities["date_window"] = date_window
            refresh_targets = ["email", "overview", "history"]

        return {
            "intent": intent,
            "confidence": confidence,
            "entities": entities,
            "requires_confirmation": requires_confirmation,
            "refresh_targets": refresh_targets,
        }

    FEW_SHOT_REASONING = (
        "Vi du cach lap luan (KHONG dung ngay/gio trong vi du, chi hoc CACH suy luan "
        "tu THOI DIEM HIEN TAI thuc te o tren):\n"
        "- 'Nhac minh hop voi sep luc 3 gio chieu mai' => schedule.create; "
        "start_time = (ngay ke tiep THOI DIEM HIEN TAI) luc 15:00.\n"
        "- 'Dat lich kham rang thu 5 tuan sau 9 gio sang' => schedule.create; "
        "start_time = (Thu Nam cua tuan ke tiep tuan chua THOI DIEM HIEN TAI) luc 09:00.\n"
        "- 'Trong 2 tieng nua goi lai cho khach' => schedule.create; "
        "start_time = THOI DIEM HIEN TAI + 2 gio.\n"
        "- 'Hay tao lich hen hom nay luc 3 gio chieu voi noi dung la: Hop voi khach hang ban ve "
        "hop dong quy 3' => schedule.create; description='Hop voi khach hang ban ve hop dong quy "
        "3' (CHI lay phan sau 'noi dung la:', bo qua 'Hay tao lich hen hom nay luc 3 gio chieu voi'); "
        "vi khong co 'tieu de la...' rieng, title tu dat = 'Hop voi khach hang ban hop dong quy 3' "
        "(tom tat noi dung, khong copy nguyen ca cau).\n"
        "- 'Tuan sau minh co lich gi khong' => schedule.list; window.label=next_week.\n"
        "- 'Tim email tu chi Lan noi ve hop dong' => email.search; "
        "email_query.keyword='hop dong', email_query.sender='chi Lan' "
        "(vi 'chi Lan' khong phai dia chi email hop le nen coi la tu khoa, khong dat vao truong sender dang email).\n"
        "- 'Tu nay minh lam freelance roi, doi giup minh' => settings.update_mode; mode=freelancer.\n"
        "- 'Nay minh bao ban lam gi roi nhi' => history.list (hoi VIEC DA LAM trong qua khu).\n"
        "- 'Hom nay minh co cac hoat dong nhu yoga, cham meo, don nha. Dua vao checklist giup minh' "
        "=> checklist.create; checklist_items=[{title:'Yoga',priority:'normal'},"
        "{title:'Cham meo',priority:'normal'},{title:'Don nha',priority:'normal'}] (day la cac VIEC "
        "SAP lam, KHONG phai history.list dau cau co chua tu 'hoat dong').\n"
        "- 'Minh can nop bao cao gap truoc 5 gio chieu nay, ngoai ra ranh thi don ban lam viec, "
        "dua vao checklist giup minh' => checklist.create; checklist_items=[{title:'Nop bao cao',"
        "priority:'high'},{title:'Don ban lam viec',priority:'low'}] (tung viec mang muc do gap "
        "rieng, khong dung chung 1 priority cho ca danh sach).\n"
        "- 'Hom nay toi co cac hoat dong nhu: tap yoga, cham meo cung, lam viec nha. Hay sap xep "
        "hoac goi y lich cho toi' => schedule.suggest_plan (KHONG phai checklist.create, vi nguoi "
        "dung noi ro 'goi y lich' -- ho muon AI xep gio cu the cho tung hoat dong, khong chi liet "
        "ke thanh danh sach viec).\n"
        "- 'Ban nghi gi ve lam viec tu xa' => chat.freeform (khong khop muc nao tren).\n"
        "- 'Hom nay toi co gym luc 7:30 sang, nau an luc 9:00 sang, lam bai tap luc 11:00 "
        "sang. Them vao checklist theo thu tu gio' => checklist.create; checklist_items="
        "[{title:'07:30 - Gym',priority:'normal'},{title:'09:00 - Nau an',priority:'normal'},"
        "{title:'11:00 - Lam bai tap',priority:'normal'}] (dau ':' trong 7:30 la mot phan cua "
        "GIO, TUYET DOI khong dung no de tach cau; giu du ten hoat dong va sap tang dan theo gio).\n"
        "- 'Nguoi sang lap Facebook la ai?' => chat.freeform (day la cau hoi kien thuc; "
        "chuoi 'book' nam ben trong ten rieng 'Facebook' KHONG co nghia la dat lich).\n"
        "- 'Ai la chu cua Amazon?' => chat.freeform (hoi kien thuc ve cong ty, KHONG phai "
        "email, checklist hay lich).\n"
        "- 'Who owns Booking.com?' => chat.freeform (Booking.com la ten rieng; 'book' ben "
        "trong ten KHONG phai lenh dat lich).\n"
        "- 'Ai sang lap Gmail?' => chat.freeform (Gmail la doi tuong cua cau hoi kien thuc, "
        "KHONG phai yeu cau tim email).\n"
        "- 'Book a meeting tomorrow at 3pm' => schedule.create (o day 'book' la dong tu hanh "
        "dong va co doi tuong meeting + thoi gian ro rang).\n"
        "- (Vi du bang TIENG ANH, ap dung CACH suy luan giong het cac vi du tieng Viet o tren) "
        "'Schedule a call with the client tomorrow at 3pm' => schedule.create; "
        "start_time = (ngay ke tiep THOI DIEM HIEN TAI) luc 15:00, title='Call with the client'.\n"
        "- 'What's on my calendar next week' => schedule.list; window.label=next_week.\n"
        "- 'I have a lot of things to do today: gym, laundry, finish the report (urgent)' "
        "=> checklist.create; checklist_items=[{title:'Gym',priority:'normal'},"
        "{title:'Laundry',priority:'normal'},{title:'Finish the report',priority:'high'}].\n"
    )

    # Domain words for any of the recognizable intents. If a message has none
    # of these (and no time/date signal either -- schedule requests almost
    # always carry one even without saying "lich"), it is overwhelmingly
    # likely to be plain chat, so we skip the extra AI classification
    # round-trip entirely instead of paying its latency just to confirm
    # "chat.freeform" -- the main chat reply already handles that message
    # right after.
    ACTIONABLE_HINTS = (
        "lich", "hen", "hop", "su kien", "gap mat", "gap nhau", "nhac", "remind",
        "meeting", "appointment", "calendar", "book", "dat lich", "dat cho",
        "schedule", "reschedule", "cancel", "postpone", "move", "set up", "set a reminder",
        "goi lai", "goi cho", "goi dien", "call back",
        "email", "mail", "gmail", "hop thu", "inbox", "thu tu", "message", "draft",
        "reply", "respond", "summarize", "summary", "find", "search", "mark as read", "mark unread",
        "lich su", "hoat dong", "history", "activity",
        "da lam gi", "lam gi roi", "nho lai", "nhac lai", "vua nay", "vua roi",
        "mode", "che do lam viec", "doi che do", "chuyen che do", "switch mode", "change mode",
        "checklist", "to-do", "todo", "danh sach cong viec", "danh sach viec",
        "task", "tasks", "assignment", "homework", "deadline", "due", "exam", "quiz", "class",
        "plan my day", "plan my week",
    )

    # Signals that the message is asking to turn a list of upcoming
    # activities into a checklist/to-do list -- distinct from
    # _is_history_lookup's signals, which are about *past* activity.
    CHECKLIST_LIST_SIGNAL = (
        "checklist", "to-do", "todo", "danh sach cong viec", "danh sach viec",
        "viec can lam", "cac hoat dong", "hoat dong sau", "nhung viec",
        "cac viec can", "list cong viec",
        "things to do", "my tasks", "task list", "list of tasks",
        "today's activities", "todays activities", "things i need to do",
        "stuff i need to do",
    )

    TIME_HINT_PATTERN = re.compile(
        r"(?<!\d)\d{1,2}\s*(?:gio|h)(?::?\d{2})?(?!\d)"
        r"|(?<!\d)\d{1,2}(?::\d{2})?\s*(?:am|pm)\b"
        r"|ngay mai|hom nay|hom qua|sang nay|chieu nay|toi nay|sang mai|chieu mai|toi mai"
        r"|tuan nay|tuan sau|tuan toi|tuan truoc"
        r"|thu hai|thu ba|thu tu|thu nam|thu sau|thu bay|chu nhat"
        r"|\d{1,3}\s*(?:phut|gio|tieng)\s*nua"
        r"|\btomorrow\b|\btoday\b|\byesterday\b|\btonight\b"
        r"|\blater today\b|\btomorrow night\b|\bthis weekend\b|\bnext weekend\b"
        r"|\bthis morning\b|\bthis afternoon\b|\bthis evening\b|\btomorrow morning\b|\btomorrow afternoon\b"
        r"|\bthis week\b|\bnext week\b|\blast week\b"
        r"|\bnext monday\b|\bnext tuesday\b|\bnext wednesday\b|\bnext thursday\b|\bnext friday\b|\bnext saturday\b|\bnext sunday\b"
        r"|\bmonday\b|\btuesday\b|\bwednesday\b|\bthursday\b|\bfriday\b|\bsaturday\b|\bsunday\b"
        r"|\bnoon\b|\bmidnight\b|\bend of day\b|\beod\b"
        r"|\bby monday\b|\bby tuesday\b|\bby wednesday\b|\bby thursday\b|\bby friday\b|\bby saturday\b|\bby sunday\b"
        r"|\bin \d{1,3}\s*(?:minutes?|mins?|hours?)\b"
    )

    # Explicit "content marker" phrases (e.g. "voi noi dung la: xxx") that mark
    # exactly which part of a scheduling request is the actual event content
    # -- everything after the marker, and ONLY that, becomes the description,
    # so a sentence like "Hay tao lich hen hom nay luc 3 gio voi noi dung la: X"
    # doesn't end up with the whole command text as its content. Matched
    # directly against the original (accented) message, longest phrase first
    # so "voi noi dung" doesn't shadow "voi noi dung la".
    _CONTENT_MARKER_TERMS = (
        "với nội dung là", "voi noi dung la",
        "với nội dung", "voi noi dung",
        "nội dung là", "noi dung la",
        "nội dung", "noi dung",
        "ghi chú là", "ghi chu la",
        "ghi chú", "ghi chu",
        "mô tả là", "mo ta la",
        "mô tả", "mo ta",
        "with description", "description is", "description:",
        "with note", "note is", "note:",
        "details are", "details:",
    )
    CONTENT_MARKER_RE = re.compile(
        r"(?:" + "|".join(re.escape(t) for t in sorted(set(_CONTENT_MARKER_TERMS), key=len, reverse=True)) + r")"
        r"\s*[:\-]?\s*(.+)$",
        re.IGNORECASE | re.DOTALL,
    )

    # Same idea but for an explicit title, e.g. "tieu de la Hop nhom".
    _TITLE_MARKER_TERMS = (
        "tiêu đề là", "tieu de la",
        "tiêu đề", "tieu de",
        "tên sự kiện là", "ten su kien la",
        "tên sự kiện", "ten su kien",
        "tên lịch là", "ten lich la",
        "tên lịch", "ten lich",
        "tựa đề là", "tua de la",
        "tựa đề", "tua de",
        "title is", "title:",
        "event title is", "event title:",
        "name it", "call it",
    )
    TITLE_MARKER_RE = re.compile(
        r"(?:" + "|".join(re.escape(t) for t in sorted(set(_TITLE_MARKER_TERMS), key=len, reverse=True)) + r")"
        r"\s*[:\-]?\s*([^,.;\n]+)",
        re.IGNORECASE,
    )

    # Same idea but for an explicit location, e.g. "dia diem la 123 Le Loi".
    # Deliberately limited to unambiguous markers -- bare "tai"/"o" are too
    # common as ordinary prepositions ("tai vi", "o day") to use as a signal.
    _LOCATION_MARKER_TERMS = (
        "địa điểm là", "dia diem la",
        "địa điểm", "dia diem",
        "tại địa chỉ", "tai dia chi",
        "địa chỉ là", "dia chi la",
        "địa chỉ", "dia chi",
        "location la", "location:",
        "location is", "at location",
        "address is", "address:",
        "venue is", "venue:",
    )
    LOCATION_MARKER_RE = re.compile(
        r"(?:" + "|".join(re.escape(t) for t in sorted(set(_LOCATION_MARKER_TERMS), key=len, reverse=True)) + r")"
        r"\s*[:\-]?\s*([^,.;\n]+)",
        re.IGNORECASE,
    )

    # Urgency words used to score checklist items pulled out of a chat
    # message -- items the user explicitly flags as urgent/low-priority sort
    # to the top/bottom of the checklist instead of all landing at the same
    # flat priority.
    CHECKLIST_URGENCY_HIGH = (
        "gap", "khan cap", "uu tien cao", "quan trong", "can ngay",
        "ngay lap tuc", "urgent", "asap", "deadline", "important",
        "high priority", "right away", "immediately", "as soon as possible",
    )
    CHECKLIST_URGENCY_LOW = (
        "khong gap", "ranh thi", "khi nao ranh", "khong uu tien",
        "khong qua gap", "thong thuong", "low priority",
        "not urgent", "no rush", "whenever i'm free", "whenever im free",
        "not a priority", "when i have time",
    )

    # Leading filler ("Hay", "Ban hay", "Giup toi", ...) stripped before
    # falling back to the whole message as the title source, so "Hay tao
    # lich..." doesn't leave "Hay" stuck onto the auto-generated title.
    LEADING_FILLER_RE = re.compile(
        r"^\s*(?:xin\s+)?(?:hãy|hay|bạn hãy|ban hay|làm ơn|lam on|giúp tôi|giup toi|"
        r"giúp mình|giup minh|cho tôi|cho toi|mình muốn|minh muon|tôi muốn|toi muon|"
        r"vui lòng|vui long|"
        r"please|can you|could you|would you|i want to|i need to|i'd like to|i would like to)\s+",
        re.IGNORECASE,
    )

    def has_actionable_hint(self, message):
        if self.is_general_knowledge_question(message):
            return False
        text = self.normalize(message)
        # Match complete words/phrases. A substring check makes English action
        # hints dangerously noisy: for example, ``book`` also occurs inside
        # ``Facebook``, so "Nguoi sang lap Facebook la ai?" used to enter the
        # calendar-intent pipeline instead of remaining a knowledge question.
        if self._contains_word(text, self.ACTIONABLE_HINTS):
            return True
        if self._contains_word(
            text,
            tuple(alias for aliases in self.MODE_ALIASES.values() for alias in aliases),
        ):
            return True
        return bool(self.TIME_HINT_PATTERN.search(text))

    def is_general_knowledge_question(self, message):
        text = self.normalize(message).strip(" .?!,;:")
        text = re.sub(
            r"^(?:(?:could|can|would)\s+you\s+(?:please\s+)?(?:tell\s+me|explain)|"
            r"please\s+(?:tell\s+me|explain)|"
            r"(?:ban\s+co\s+the|lam\s+on|vui\s+long)\s+(?:cho\s+toi\s+biet|"
            r"cho\s+minh\s+biet|giai\s+thich))\s+",
            "",
            text,
            count=1,
        )
        if not self._KNOWLEDGE_QUESTION_RE.search(text):
            return False
        return not self._contains_word(text, self._EXPLICIT_WORKSPACE_COMMANDS)

    def has_explicit_workspace_command(self, message):
        """True only for an actual command, not a question that merely
        mentions words such as email, calendar, book, event or history."""
        text = self.normalize(message)
        return self._contains_word(text, self._EXPLICIT_WORKSPACE_COMMANDS)

    def detect_with_ai(self, message, ai_service, user_id=None, db_path=None,
                        chat_session_id=None, confidence_threshold=0.6):
        """Run the deterministic rules first; only ask the AI to read the
        message when the rules aren't confident (i.e. it fell through to
        chat.freeform) AND the message at least hints at a recognizable
        domain. This keeps clear-cut requests AND plain chit-chat fast and
        free, while letting paraphrased/indirect action requests -- including
        follow-ups that only make sense given recent chat turns -- still get
        recognized.

        Before paying for that AI call, check the intent-pattern cache for a
        phrasing similar enough to one already TRUSTED (the AI agreed on the
        same intent IntentPattern.CONFIRM_THRESHOLD times before) -- if
        found, skip the AI call entirely and reuse that classification
        (with entities re-extracted fresh by the same rule-based extractor
        that intent already has, never the old message's entities). A brand
        new phrasing the AI just resolved does NOT skip future AI calls
        immediately -- it starts as an unproven 'candidate' that still goes
        through the AI every time until it has been confirmed enough times,
        spending quota deliberately up front so only well-proven patterns
        ever get to answer on their own later.
        """
        result = self.detect(message)
        contextual_followup = is_context_dependent_followup(message)
        recent_turns = (
            self._recent_turns_text(db_path, chat_session_id)
            if contextual_followup else ""
        )
        if result.get("confidence", 0) >= confidence_threshold and not (
            contextual_followup and recent_turns
        ):
            return result
        if not self.has_actionable_hint(message) and not (
            contextual_followup and recent_turns
        ):
            return result

        # Context-dependent phrases such as "do it" and "đổi nó sang 3 giờ"
        # are intentionally never cached or classified in isolation: their
        # meaning changes from one session to another.
        if not contextual_followup:
            cached = self._lookup_cached_intent(message)
            if cached:
                return cached

        # The reviewed 500-case-per-tool corpus is an actual offline
        # classifier fallback, not merely RAG documentation.  Use it only
        # when the deterministic rules fell through and its lead is clear;
        # otherwise keep the AI/self-correction path below.  Entity values
        # are always extracted from the current message, never copied from a
        # training example.
        if not contextual_followup:
            trained = self._detect_via_training(message)
            if trained:
                return trained

        if not ai_service:
            return result

        try:
            ai_result = self._detect_via_ai(
                message, ai_service, user_id=user_id, db_path=db_path, chat_session_id=chat_session_id,
            )
        except Exception:
            logger.warning("AI-assisted intent detection failed", exc_info=True)
            ai_result = None

        if ai_result and contextual_followup and recent_turns:
            ai_result["context_assisted"] = True

        if (
            ai_result
            and not contextual_followup
            and ai_result.get("intent") in self.CACHEABLE_INTENTS
        ):
            try:
                from services.intent_pattern_cache import intent_pattern_cache
                intent_pattern_cache.observe(
                    message, ai_result["intent"], confidence=ai_result.get("confidence", 0.6),
                )
            except Exception:
                logger.warning("Failed to record intent pattern cache entry", exc_info=True)

        return ai_result or result

    _WORKFLOW_SPLIT_RE = re.compile(
        r"\s*(?:;|\n+|\b(?:rồi|roi|sau đó|sau do|đồng thời|dong thoi|"
        r"tiếp theo|tiep theo|then|and then)\b)\s*",
        re.IGNORECASE,
    )
    _WORKFLOW_AND_RE = re.compile(
        r"\s+(?:và|va|and)\s+(?=(?:tạo|tao|đặt|dat|thêm|them|xóa|xoa|hủy|huy|"
        r"đổi|doi|sửa|sua|tìm|tim|kiểm|kiem|xem|tóm tắt|tom tat|đánh dấu|danh dau|"
        r"chuyển|chuyen|sắp xếp|sap xep|gợi ý|goi y|create|schedule|book|add|"
        r"delete|remove|cancel|move|change|update|find|search|show|summarize|"
        r"mark|plan|suggest)\b)",
        re.IGNORECASE,
    )

    def detect_workflow_with_ai(self, message, ai_service, user_id=None, db_path=None,
                                chat_session_id=None):
        """Detect explicit multi-step requests while preserving safe writes.

        Plain ``va/and`` inside a task list is deliberately not a split.  We
        split only explicit sequencing words, semicolons/newlines, or ``va``
        followed by another strong action verb.
        """
        parts = [
            part.strip(" ,.")
            for part in self._WORKFLOW_SPLIT_RE.split(str(message or ""))
            if part.strip(" ,.")
        ]
        expanded = []
        for part in parts:
            expanded.extend(
                piece.strip(" ,.") for piece in self._WORKFLOW_AND_RE.split(part) if piece.strip(" ,.")
            )
        if len(expanded) < 2:
            return self.detect_with_ai(
                message, ai_service, user_id=user_id, db_path=db_path,
                chat_session_id=chat_session_id,
            )

        steps = []
        for part in expanded[:8]:
            result = self.detect_with_ai(
                part, ai_service, user_id=user_id, db_path=db_path,
                chat_session_id=chat_session_id,
            )
            steps.append({**result, "message": part})
        actionable_steps = [
            step for step in steps if step.get("intent") != "chat.freeform"
        ]
        if len(steps) < 2 or not actionable_steps:
            return self.detect_with_ai(
                message, ai_service, user_id=user_id, db_path=db_path,
                chat_session_id=chat_session_id,
            )

        refresh_targets = sorted({
            target for step in steps for target in step.get("refresh_targets", [])
        })
        return {
            "intent": "workflow.multi",
            "confidence": round(min(step.get("confidence", 0.5) for step in steps), 4),
            "entities": {},
            "steps": steps,
            "requires_confirmation": any(step.get("requires_confirmation") for step in steps),
            "refresh_targets": refresh_targets,
            "workflow_assisted": True,
        }

    def _detect_via_training(self, message, min_confidence=0.65):
        try:
            from services.training_intent_classifier import training_intent_classifier
            match = training_intent_classifier.classify(message)
        except Exception:
            logger.warning("Offline training classifier failed", exc_info=True)
            return None
        if not match or match.get("confidence", 0) < min_confidence:
            return None
        result = self._result_for_known_intent(
            match.get("intent"), message, confidence=match["confidence"],
        )
        if result:
            result["training_assisted"] = True
        return result

    def _result_for_known_intent(self, intent, message, confidence=0.7):
        """Re-extract current-message entities for a known intent label."""
        text = self.normalize(message)
        base = {
            "intent": intent,
            "confidence": confidence,
            "entities": {},
            "requires_confirmation": intent in self.CACHEABLE_INTENTS,
            "refresh_targets": [],
        }
        if intent == "schedule.create":
            schedule = self.extract_schedule(message)
            if not schedule.get("start_time"):
                return None
            base["entities"] = {"schedule": schedule}
            base["refresh_targets"] = ["schedule", "calendar", "overview", "history"]
        elif intent == "schedule.update":
            new_values = self.extract_schedule(message)
            if not (new_values.get("start_time") or new_values.get("end_time") or new_values.get("location")):
                return None
            base["entities"] = {"new_values": new_values}
            base["refresh_targets"] = ["schedule", "calendar", "overview", "history"]
        elif intent == "schedule.delete":
            base["refresh_targets"] = ["schedule", "calendar", "overview", "history"]
        elif intent == "schedule.list":
            base["requires_confirmation"] = False
            base["entities"] = {"window": self._calendar_window(text)}
            base["refresh_targets"] = ["schedule", "calendar", "overview", "history"]
        elif intent == "schedule.suggest_plan":
            base["requires_confirmation"] = False
            base["refresh_targets"] = ["schedule", "calendar", "overview", "history"]
        elif intent == "email.latest_summary":
            base["requires_confirmation"] = False
            base["entities"] = {"count": self._latest_email_count(text)}
            date_window = self._email_date_window(text)
            if date_window:
                base["entities"]["date_window"] = date_window
            base["refresh_targets"] = ["email", "overview", "history"]
        elif intent == "email.search":
            base["requires_confirmation"] = False
            date_window = self._email_date_window(text)
            if date_window:
                base["entities"]["date_window"] = date_window
            base["refresh_targets"] = ["email", "overview", "history"]
        elif intent in ("email.mark_read", "email.mark_unread"):
            date_window = self._email_date_window(text)
            if date_window:
                base["entities"]["date_window"] = date_window
            base["refresh_targets"] = ["email", "overview", "history"]
        elif intent == "history.list":
            base["requires_confirmation"] = False
            base["entities"] = {"limit": self._limit_from_text(text, default=8, maximum=100)}
            base["refresh_targets"] = ["history"]
        elif intent == "settings.update_mode":
            mode = self._mode_from_text(text)
            if not mode:
                return None
            base["entities"] = {"mode": mode}
            base["refresh_targets"] = ["settings", "profile", "history"]
        elif intent == "checklist.create":
            items = self._checklist_items_from_text(message)
            if not items:
                return None
            base["entities"] = {"items": items[:50]}
            base["refresh_targets"] = ["overview", "history"]
        else:
            return None
        return base

    def _lookup_cached_intent(self, message):
        """Reuse a previously AI-confirmed phrasing->intent match. Entities
        are always re-extracted fresh via the rule-based extractor for that
        intent (dates/titles/etc differ on every message) -- the cache only
        ever supplies the intent label, never borrowed entity values. If
        extraction comes up empty, returns None so the caller falls through
        to actually calling the AI rather than forcing a thin/wrong result."""
        try:
            from services.intent_pattern_cache import intent_pattern_cache
            hit = intent_pattern_cache.lookup(message, min_score=0.6)
        except Exception:
            logger.warning("Intent pattern cache lookup failed", exc_info=True)
            return None
        if not hit or hit["intent"] not in self.CACHEABLE_INTENTS:
            return None

        intent = hit["intent"]
        base = self._result_for_known_intent(intent, message, confidence=0.7)
        if not base:
            return None
        base["cache_assisted"] = True
        return base

    def _detect_via_ai(self, message, ai_service, user_id=None, db_path=None, chat_session_id=None):
        now = self._local_now()
        recent_turns = self._recent_turns_text(db_path, chat_session_id)
        system_message = {
            "role": "system",
            "content": (
                "Ban la bo phan loai y dinh cho mot tro ly cong viec. Doc cau nhan tu "
                "nguoi dung (va lich su hoi thoai gan day neu co) va TRA VE DUY NHAT mot "
                "JSON object hop le theo dung cau truc duoc yeu cau, khong giai thich them, "
                "khong dung markdown. Nguoi dung co the viet bang TIENG VIET hoac TIENG ANH "
                "(hoac lan ca hai) -- hieu va phan loai dung y dinh bat ke ngon ngu nao, "
                "khong chi dua vao tu khoa tieng Viet."
            ),
        }
        user_message = {
            "role": "user",
            "preserve_context": True,
            "content": self._build_ai_classification_prompt(message, now, recent_turns),
        }
        raw = ai_service.generate_response(
            [system_message, user_message],
            max_tokens=320,
            task="intent_classification",
            user_id=user_id,
        )
        data = self._parse_ai_json(raw)
        result = self._coerce_ai_result(data, message) if data else None
        if result:
            return result

        # Self-correction retry: ask once more, pointing at what came back, in
        # case the first reply broke JSON formatting or skipped a required field.
        retry_message = {
            "role": "user",
            "content": (
                "Phan hoi truoc khong dung dinh dang JSON yeu cau hoac thieu du lieu bat buoc:\n"
                f"{str(raw or '')[:400]}\n\n"
                "Hay tra ve LAI CHINH XAC mot JSON object hop le dung cau truc da neu o tren, "
                "khong giai thich, khong dung markdown."
            ),
        }
        raw2 = ai_service.generate_response(
            [system_message, user_message, retry_message],
            max_tokens=320,
            task="intent_classification",
            user_id=user_id,
        )
        data2 = self._parse_ai_json(raw2)
        return self._coerce_ai_result(data2, message) if data2 else None

    def _recent_turns_text(self, db_path, chat_session_id, limit=5):
        if not db_path or not chat_session_id:
            return ""
        try:
            records = History.get_recent(limit=limit, db_path=db_path, chat_session_id=chat_session_id)
        except Exception:
            return ""
        if not records:
            return ""
        lines = []
        for record in reversed(records):
            if record.get("action_type") != "chat":
                continue
            user_text = self._squash(record.get("user_message"))[:320]
            assistant_text = self._squash(record.get("assistant_response"))[:320]
            if user_text:
                lines.append(f"Nguoi dung: {user_text}")
            if assistant_text:
                lines.append(f"Tro ly: {assistant_text}")
        return "\n".join(lines)

    def _build_ai_classification_prompt(self, message, now, recent_turns=""):
        weekday = self.WEEKDAY_NAMES_VN[now.weekday()]
        history_block = (
            f"LICH SU HOI THOAI GAN DAY (chi de hieu ngu canh / cau tham chieu nhu "
            f"'doi gio do', 'vay tao lich luon', KHONG phai cau can phan loai):\n{recent_turns}\n\n"
            if recent_turns else ""
        )
        return (
            "CAU CAN PHAN LOAI - DAY LA LENH DUY NHAT CUA LUOT HIEN TAI:\n"
            f"<current_user_turn>{message}</current_user_turn>\n\n"
            "THU TU UU TIEN NGU CANH:\n"
            "1. Menh de sua doi/phu dinh va yeu cau ngon ngu trong current_user_turn la cao nhat.\n"
            "2. Lich su chi dung de giai 'no/it/cai do/the second one'; khong bien cau cu "
            "thanh lenh moi va khong khoi phuc muc tieu user da huy.\n"
            "3. Neu co hon mot doi tuong tham chieu hop ly, chon chat.freeform de hoi mot "
            "cau lam ro; khong tu chon cho thao tac ghi.\n"
            "4. Hieu code-switch Viet-Anh theo nghia toan cau; giu nguyen ten rieng, subject, "
            "email, ID, ngay gio va cac rang buoc phu dinh.\n\n"
            f"THOI DIEM HIEN TAI: {now.strftime('%Y-%m-%d %H:%M')} ({weekday}), GMT+7\n\n"
            "Cac loai y dinh hop le (chon dung 1 gia tri cho truong \"intent\"):\n"
            f"{tool_catalog.build_catalog_prompt_block()}\n\n"
            f"{self.FEW_SHOT_REASONING}\n"
            "Tra ve CHINH XAC mot JSON object theo cau truc:\n"
            "{\n"
            '  "intent": "<mot trong cac gia tri tren>",\n'
            '  "confidence": <so tu 0 den 1>,\n'
            '  "schedule": {"title": "", "description": "", "start_time": "YYYY-MM-DDTHH:MM:SS", '
            '"end_time": "YYYY-MM-DDTHH:MM:SS hoac null", "attendees": [], "location": ""},\n'
            '  "window": {"label": "today|yesterday|this_week|next_week|last_week|custom", '
            '"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},\n'
            '  "email_count": <1-50>,\n'
            '  "email_query": {"sender": "", "keyword": "", "unread_only": false},\n'
            '  "history_limit": <1-100>,\n'
            '  "mode": "<student|worker|freelancer|creator|business|mentor|teacher hoac null>",\n'
            '  "standalone_message": "<viet lai cau hien tai day du bang cach giai tham chieu '
            'tu lich su; de null neu khong can>",\n'
            '  "checklist_items": [{"title": "<viec 1>", "time": "HH:MM hoac null", "priority": "high|normal|low"}, "..."]\n'
            "}\n"
            "Chi dien cac truong lien quan toi intent da chon, cac truong khac de null/bo qua. "
            "Neu intent la checklist.create, BAT BUOC dien checklist_items la danh sach NGAN GON "
            "tung viec/hoat dong nguoi dung da liet ke (giu nguyen y chinh, KHONG bia them, KHONG "
            "gop nhieu viec vao chung mot phan tu, bo qua cac cum tu mo dau/ket thuc nhu 'hom nay "
            "minh co', 'dua vao checklist giup minh'). Voi moi viec, dat priority='high' neu nguoi "
            "dung noi viec do gap/khan cap/quan trong/co han gan, priority='low' neu nguoi dung noi "
            "khong gap/ranh thi lam/khong uu tien, con lai dung priority='normal'.\n"
            "Neu tung viec co gio cu the, BAT BUOC giu gio trong truong time theo HH:MM, KHONG tach "
            "dau hai cham trong 7:30/09:00 nhu dau phan cach. Sap checklist_items tang dan theo time.\n"
            "Neu intent la schedule.create, BAT BUOC tinh start_time tuyet doi (ngay+gio cu the) "
            "dua vao THOI DIEM HIEN TAI o tren khi cau co nhac thoi gian (vd 'chieu mai', "
            "'thu 5 tuan sau', 'trong 2 tieng nua'). Voi schedule.create, neu cau nhan co danh "
            "dau noi dung ro rang (vd 'noi dung la:', 'voi noi dung:', 'ghi chu:', 'mo ta:'), "
            "truong schedule.description CHI duoc lay PHAN VAN BAN SAU danh dau do, KHONG duoc "
            "lay nguyen ca cau lenh (bao gom cum tu yeu cau tao lich va phan ngay/gio). Neu cau "
            "khong co danh dau nhu vay, dien schedule.description bang noi dung chinh cua su kien "
            "(bo qua cac cum tu mo dau nhu 'hay', 'ban hay', 'giup toi'). Neu nguoi dung KHONG "
            "neu ten/tieu de rieng cho lich hen (vd khong co 'tieu de la...', 'ten su kien la...'), "
            "TU DAT schedule.title bang cach DOC VA HIEU noi dung do roi tom tat thanh mot cum tu "
            "ngan gon (toi da khoang 8-10 tu), KHONG duoc copy nguyen van ca cau lenh lam tieu de.\n"
            "Neu intent la email.search, email.latest_summary, email.mark_read hoac "
            "email.mark_unread VA cau nhan co nhac mot khoang thoi gian cu the ve khi email "
            "duoc gui/nhan (vd 'hom nay', 'hom qua', 'tuan nay', mot ngay cu the), BAT BUOC dien "
            "truong \"window\" voi start/end la NGAY (YYYY-MM-DD) bao trum dung khoang do, de ket "
            "qua chi lay email trong dung khoang thoi gian nguoi dung hoi, khong lay email cu hon "
            "hoac moi hon. Khong bia dat thong tin ma nguoi dung khong cung cap. Dung lich su hoi "
            "thoai (neu co) de hieu cau tham chieu/sua doi, nhung chi phan loai cau nhan moi nhat.\n\n"
            f"{history_block}"
            f"CAU NHAN TU NGUOI DUNG: \"{message}\""
        )

    @staticmethod
    def _parse_ai_json(raw):
        if not raw:
            return None
        cleaned = str(raw).strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
        try:
            data = json.loads(cleaned)
        except (TypeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _coerce_ai_result(self, data, message):
        intent = str(data.get("intent") or "").strip()
        if intent not in self.AI_INTENTS:
            return None

        # Safety net against an over-eager provider returning schedule.create
        # for a factual question whose company/product name resembles a tool
        # keyword. Knowledge questions never produce confirmation cards.
        if self.is_general_knowledge_question(message):
            return {
                "intent": "chat.freeform",
                "confidence": 0.98,
                "entities": {},
                "requires_confirmation": False,
                "refresh_targets": [],
                "ai_assisted": True,
                "knowledge_question": True,
            }

        try:
            confidence = float(data.get("confidence", 0.6))
        except (TypeError, ValueError):
            confidence = 0.6
        confidence = max(0.5, min(confidence, 0.97))

        entities = {}
        requires_confirmation = False
        refresh_targets = []

        if intent == "schedule.create":
            schedule = self._coerce_ai_schedule(data.get("schedule") or {}, message)
            if not schedule.get("start_time"):
                return None
            entities["schedule"] = schedule
            requires_confirmation = True
            refresh_targets = ["schedule", "calendar", "overview", "history"]
        elif intent == "schedule.list":
            window = self._coerce_ai_window(data.get("window") or {})
            if not window:
                return None
            entities["window"] = window
            refresh_targets = ["schedule", "calendar", "overview", "history"]
        elif intent == "email.latest_summary":
            entities["count"] = self._coerce_int(data.get("email_count"), default=1, minimum=1, maximum=50)
            date_window = self._coerce_ai_date_window(data.get("window") or {})
            if date_window:
                entities["date_window"] = date_window
            refresh_targets = ["email", "overview", "history"]
        elif intent == "email.search":
            query = data.get("email_query")
            if isinstance(query, dict):
                entities["query"] = {
                    "sender": str(query.get("sender") or "").strip(),
                    "keyword": str(query.get("keyword") or "").strip(),
                    "unread_only": bool(query.get("unread_only")),
                }
            date_window = self._coerce_ai_date_window(data.get("window") or {})
            if date_window:
                entities["date_window"] = date_window
            refresh_targets = ["email", "overview", "history"]
        elif intent == "schedule.update":
            entities["new_values"] = self._coerce_ai_schedule(data.get("schedule") or {}, message)
            requires_confirmation = True
            refresh_targets = ["schedule", "calendar", "overview", "history"]
        elif intent == "schedule.delete":
            requires_confirmation = True
            refresh_targets = ["schedule", "calendar", "overview", "history"]
        elif intent in ("email.mark_read", "email.mark_unread"):
            query = data.get("email_query")
            if isinstance(query, dict):
                entities["query"] = {
                    "sender": str(query.get("sender") or "").strip(),
                    "keyword": str(query.get("keyword") or "").strip(),
                    "unread_only": False,
                }
            date_window = self._coerce_ai_date_window(data.get("window") or {})
            if date_window:
                entities["date_window"] = date_window
            refresh_targets = ["email", "overview", "history"]
        elif intent == "history.list":
            entities["limit"] = self._coerce_int(data.get("history_limit"), default=8, minimum=1, maximum=100)
            refresh_targets = ["history"]
        elif intent == "settings.update_mode":
            mode = str(data.get("mode") or "").strip().lower()
            if mode not in self.MODE_ALIASES:
                return None
            entities["mode"] = mode
            refresh_targets = ["settings", "profile", "history"]
        elif intent == "checklist.create":
            raw_items = data.get("checklist_items")
            items = []
            if isinstance(raw_items, list):
                for raw_item in raw_items:
                    if isinstance(raw_item, dict):
                        title = str(raw_item.get("title") or "").strip()[:240]
                        priority = str(raw_item.get("priority") or "normal").strip().lower()
                        time_value = str(raw_item.get("time") or "").strip()
                    else:
                        title = str(raw_item or "").strip()[:240]
                        priority = "normal"
                        time_value = ""
                    if not title:
                        continue
                    if priority not in ("high", "normal", "low"):
                        priority = "normal"
                    time_match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", time_value)
                    normalized_time = (
                        f"{int(time_match.group(1)):02d}:{int(time_match.group(2)):02d}"
                        if time_match else ""
                    )
                    if normalized_time and not title.startswith(normalized_time):
                        title = f"{normalized_time} - {title}"
                    items.append({"title": title, "priority": priority, "time": normalized_time})
            if not items:
                return None
            items.sort(key=lambda item: (item["time"] == "", item["time"] or "99:99"))
            entities["items"] = items[:50]
            refresh_targets = ["overview", "history"]
        elif intent == "schedule.suggest_plan":
            # No entities to coerce -- the agent rebuilds the suggestion
            # straight from the raw message via the day-plan engine, same
            # as the rule-based path.
            refresh_targets = ["schedule", "calendar", "overview", "history"]
        else:
            return {
                "intent": "chat.freeform",
                "confidence": min(confidence, 0.5),
                "entities": {},
                "requires_confirmation": False,
                "refresh_targets": [],
                "ai_assisted": True,
            }

        result = {
            "intent": intent,
            "confidence": confidence,
            "entities": entities,
            "requires_confirmation": requires_confirmation,
            "refresh_targets": refresh_targets,
            "ai_assisted": True,
        }
        standalone_message = self._squash(data.get("standalone_message"))[:2000]
        if (
            standalone_message
            and is_context_dependent_followup(message)
            and standalone_message.casefold() != str(message or "").strip().casefold()
        ):
            # Executors receive this resolved form, while History still stores
            # the user's exact original turn.  Write intents remain behind
            # their normal confirmation gates.
            result["resolved_message"] = standalone_message
        return result

    def _coerce_ai_schedule(self, schedule, message):
        if not isinstance(schedule, dict):
            schedule = {}
        start_time = self._coerce_ai_datetime(schedule.get("start_time"))
        end_time = self._coerce_ai_datetime(schedule.get("end_time"))
        if start_time and end_time and end_time <= start_time:
            end_time = None

        attendees = schedule.get("attendees")
        if not isinstance(attendees, list):
            attendees = []
        attendees = sorted({str(item).strip() for item in attendees if str(item or "").strip()})
        if not attendees:
            attendees = sorted(set(re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", message or "")))

        # Fall back to the same marker-based extraction the rule-based path
        # uses, in case the AI left title/description blank or just echoed
        # the raw message back.
        marked_content = self._extract_marked_content(message)
        marked_title = self._extract_marked_title(message)
        marked_location = self._extract_marked_location(message)
        description = str(schedule.get("description") or "").strip() or marked_content or str(message or "").strip()
        title = str(schedule.get("title") or "").strip() or marked_title or self._schedule_title(message, marked_content)
        location = str(schedule.get("location") or "").strip() or marked_location
        return {
            "title": title[:150],
            "description": description,
            "start_time": start_time,
            "end_time": end_time,
            "attendees": attendees,
            "location": location[:150],
        }

    @staticmethod
    def _coerce_ai_datetime(value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed.isoformat()

    @staticmethod
    def _coerce_ai_window(window):
        if not isinstance(window, dict):
            return None
        try:
            start = datetime.fromisoformat(str(window.get("start"))).date()
            end = datetime.fromisoformat(str(window.get("end"))).date()
        except (TypeError, ValueError):
            return None
        if end < start:
            return None
        label = str(window.get("label") or "custom").strip() or "custom"
        return {
            "label": label,
            "start": datetime.combine(start, datetime.min.time()).isoformat(),
            "end": datetime.combine(end + timedelta(days=1), datetime.min.time()).isoformat(),
        }

    @staticmethod
    def _coerce_ai_date_window(window):
        if not isinstance(window, dict):
            return None
        try:
            start = datetime.fromisoformat(str(window.get("start"))).date()
            end = datetime.fromisoformat(str(window.get("end"))).date()
        except (TypeError, ValueError):
            return None
        if end < start:
            return None
        return {"start": start.isoformat(), "end": end.isoformat()}

    @staticmethod
    def _coerce_int(value, default, minimum, maximum):
        try:
            return max(minimum, min(int(value), maximum))
        except (TypeError, ValueError):
            return default

    def execute_direct(self, intent_result, user_id, db_path):
        intent = intent_result.get("intent")
        entities = intent_result.get("entities") or {}

        if intent == "settings.update_mode":
            # Deliberately does NOT write here -- settings.update_mode is a
            # write tool per tool_catalog, so it must only propose. The
            # actual User.update() call happens in
            # SettingsUpdateModeAgent._handle_confirmed() once the user
            # has explicitly confirmed.
            mode = entities.get("mode")
            if not mode:
                return None
            return {
                "response": (
                    f"Ban muon doi che do lam viec sang {self.MODE_LABELS.get(mode, mode)}, "
                    "dung khong? Xac nhan de minh ap dung."
                ),
                "pending_action": {"tool": "settings.update_mode", "arguments": {"mode": mode}},
                "workspace_sources": ["profile"],
                "refresh_targets": ["settings", "profile", "history"],
                "action_type": "chat",
            }

        if intent == "history.list":
            limit = entities.get("limit") or 8
            records = History.get_recent(limit=limit, db_path=db_path)
            if not records:
                response = "Chua co lich su hoat dong nao."
            else:
                lines = ["Lich su hoat dong gan day:"]
                for index, record in enumerate(records, start=1):
                    created_at = _format_user_datetime(record.get("created_at"))
                    action_type = record.get("action_type") or "activity"
                    user_text = self._squash(record.get("user_message"))[:140] or "(khong co noi dung)"
                    lines.append(f"{index}. [{action_type}] {created_at}: {user_text}")
                response = "\n".join(lines)
            return {
                "response": response,
                "workspace_sources": ["history"],
                "refresh_targets": ["history"],
                "action_type": "chat",
            }

        if intent == "schedule.create":
            schedule = entities.get("schedule") or {}
            if not schedule.get("start_time"):
                return {
                    "response": "Minh co the tao lich, nhung ban cho minh them ngay/gio cu the nhe.",
                    "schedule_suggestion": schedule,
                    "workspace_sources": ["calendar"],
                    "refresh_targets": ["schedule", "calendar", "overview", "history"],
                    "action_type": "chat",
                }
            return {
                "response": (
                    "Minh da hieu ban muon tao lich. Hay xac nhan neu thong tin nay dung: "
                    f"{schedule.get('title') or 'Lich hen'} luc {_format_user_datetime(schedule.get('start_time'))}."
                ),
                "schedule_suggestion": schedule,
                "workspace_sources": ["calendar"],
                "refresh_targets": ["schedule", "calendar", "overview", "history"],
                "action_type": "chat",
            }

        return None

    def create_schedule_from_intent(self, intent_result, override, db_path):
        schedule = ((intent_result.get("entities") or {}).get("schedule") or {}).copy()
        schedule.update({k: v for k, v in (override or {}).items() if v})
        if not schedule.get("title") or not schedule.get("start_time"):
            return None

        schedule_id = ScheduleService.create_schedule(
            title=schedule.get("title"),
            description=schedule.get("description") or "",
            start_time=schedule.get("start_time"),
            end_time=schedule.get("end_time"),
            attendees=schedule.get("attendees") or [],
            location=schedule.get("location") or None,
            db_path=db_path,
        )
        return {
            "id": schedule_id,
            "title": schedule.get("title"),
            "description": schedule.get("description") or "",
            "start_time": schedule.get("start_time"),
            "end_time": schedule.get("end_time"),
            "attendees": schedule.get("attendees") or [],
            "location": schedule.get("location") or "",
        }

    @classmethod
    def _extract_marked_content(cls, message):
        """Return the text after an explicit content marker ('noi dung la:',
        'ghi chu:', 'mo ta:' ...), or '' if the message doesn't have one."""
        if not message:
            return ""
        match = cls.CONTENT_MARKER_RE.search(message)
        if not match:
            return ""
        return match.group(1).strip(" .,;:-\"'")

    @classmethod
    def _extract_marked_title(cls, message):
        """Return an explicitly given title ('tieu de la:', 'ten su kien:' ...),
        or '' if the message doesn't name one."""
        if not message:
            return ""
        match = cls.TITLE_MARKER_RE.search(message)
        if not match:
            return ""
        return match.group(1).strip(" .,;:-\"'")[:100]

    @classmethod
    def _extract_marked_location(cls, message):
        """Return an explicitly given location ('dia diem la:', 'dia chi:' ...),
        or '' if the message doesn't name one."""
        if not message:
            return ""
        match = cls.LOCATION_MARKER_RE.search(message)
        if not match:
            return ""
        return match.group(1).strip(" .,;:-\"'")[:150]

    def _checklist_item_priority(self, text):
        """Score a single checklist item/message by urgency wording, or
        'normal' if it carries none."""
        normalized = self.normalize(text)
        if any(term in normalized for term in self.CHECKLIST_URGENCY_HIGH):
            return "high"
        if any(term in normalized for term in self.CHECKLIST_URGENCY_LOW):
            return "low"
        return "normal"

    @staticmethod
    def _summarize_for_title(text, max_len=70):
        """Best-effort 'read and understand' for when no explicit title is
        given: take the content's first clause (it's almost always the gist of
        the event) and trim it to a short, title-sized phrase."""
        text = re.sub(r"\s+", " ", text or "").strip(" .,;:-\"'")
        if not text:
            return ""
        first_clause = re.split(r"[.\n;]", text, maxsplit=1)[0].strip()
        if len(first_clause) > max_len:
            truncated = first_clause[:max_len].rsplit(" ", 1)[0]
            first_clause = truncated or first_clause[:max_len]
        return first_clause[:1].upper() + first_clause[1:] if first_clause else ""

    def extract_schedule(self, message):
        text = self.normalize(message)
        now = self._local_now()
        date_value = self._extract_date(text, now)
        time_value = self._extract_time(text)

        start_time = None
        if date_value and time_value:
            start_time = datetime.combine(date_value, time_value).isoformat()
        elif date_value:
            start_time = datetime.combine(date_value, datetime.strptime("09:00", "%H:%M").time()).isoformat()
        elif time_value:
            start_time = datetime.combine(now.date(), time_value)
            if start_time < now:
                start_time += timedelta(days=1)
            start_time = start_time.isoformat()

        duration = self._extract_duration(text)
        end_time = None
        if start_time and duration:
            end_time = (datetime.fromisoformat(start_time) + timedelta(minutes=duration)).isoformat()

        attendees = sorted(set(re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", message or "")))
        marked_content = self._extract_marked_content(message)
        marked_title = self._extract_marked_title(message)
        marked_location = self._extract_marked_location(message)
        return {
            "title": marked_title or self._schedule_title(message, marked_content),
            "description": marked_content or message,
            "start_time": start_time,
            "end_time": end_time,
            "attendees": attendees,
            "location": marked_location,
        }

    @staticmethod
    def normalize(value):
        value = unicodedata.normalize("NFD", str(value or "").lower())
        value = "".join(char for char in value if unicodedata.category(char) != "Mn")
        value = value.replace("đ", "d").replace("Ä‘", "d")
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _squash(value):
        return re.sub(r"\s+", " ", str(value or "")).strip()

    _EMAIL_SUMMARY_ACTIONS = ("tom tat", "doc", "xem", "summarize", "read", "show")

    def _is_latest_email_summary(self, text):
        if self._is_negated_action(text, self._EMAIL_SUMMARY_ACTIONS):
            return False
        email_word = r"(?:e-?mails?|gmails?|mails?|thu|hop thu|inbox)"
        has_email = re.search(rf"\b{email_word}\b", text) is not None
        has_latest = (
            any(term in text for term in (
                "moi nhat", "gan nhat", "gan day", "vua nhan", "moi nhan",
                "latest", "newest", "most recent", "recent",
                "just received", "newly received", "last received"
            ))
            or re.search(r"\blast\s+(?:e-?mails?|mails?|message|messages)\b", text) is not None
        )
        # State-changing mark/read rules run before this predicate, so bare
        # requests such as "show latest email" can retain the established
        # latest-summary behavior without stealing "mark latest unread".
        return has_email and has_latest

    def _latest_email_count(self, text):
        email_word = r"(?:e-?mails?|gmails?|mails?|thu|hop thu)"
        latest_word = (
            r"(?:moi nhat|gan nhat|gan day|vua nhan|moi nhan|latest|newest|"
            r"most recent|recent|just received|newly received|last)"
        )
        match = (
            re.search(rf"\b(\d{{1,2}})\s*(?:{latest_word}\s*)?{email_word}\b", text)
            or re.search(rf"\b{latest_word}\s*(\d{{1,2}})\s*{email_word}\b", text)
            or re.search(rf"\b{email_word}\s*{latest_word}\s*(\d{{1,2}})\b", text)
        )
        if match:
            return max(1, min(int(match.group(1)), 50))
        words = {
            "mot": 1, "một": 1, "one": 1,
            "hai": 2, "two": 2,
            "ba": 3, "three": 3,
            "bon": 4, "bốn": 4, "tu": 4, "four": 4,
            "nam": 5, "năm": 5, "five": 5,
        }
        for word, count in words.items():
            if (
                re.search(rf"\b{word}\s+(?:{latest_word}\s+)?{email_word}\b", text)
                or re.search(rf"\b{latest_word}\s+{word}\s+{email_word}\b", text)
            ):
                return count
        return 1

    # Short keywords like "hop" or "call" need a word boundary -- a plain
    # substring check also matches "hop" inside "shopping"/"workshop" or
    # "call" inside "recall"/"called", which would wrongly fire schedule
    # detection on unrelated English sentences. Multi-word phrases work
    # fine through the same helper since \b only needs to anchor the outer
    # edges, not every internal space.
    @staticmethod
    def _contains_word(text, words):
        return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)

    # Negation markers this bypasses AI review for (see detect_with_ai's
    # confidence_threshold): a bare keyword rule fires at high confidence
    # regardless of surrounding words, so "khong can tim email" would
    # otherwise still route to email.search just like "tim email" does.
    _NEGATION_MARKERS_VI = ("khong", "dung", "chua", "khoi")
    _NEGATION_FILLERS_VI = ("can", "muon", "phai", "duoc", "nen")
    _NEGATION_MARKERS_EN = ("do not", "don't", "never", "no need to", "stop", "cannot", "can't")

    def _is_negated_action(self, text, action_words):
        """True when a word/phrase from action_words is immediately
        preceded (allowing up to 2 Vietnamese filler words) by an explicit
        negation marker -- 'khong tao', 'chua can xoa', "don't mark",
        'never send'. Keeps a rule from firing on an explicit refusal just
        because the bare action keyword is present, which would otherwise
        lock detect_with_ai's confidence above threshold and skip AI review
        entirely. Deliberately conservative: only the marker-immediately-
        before-verb pattern counts, not a loose whole-sentence negation
        scan that could suppress an unrelated valid request elsewhere in
        the same message.
        """
        if not action_words:
            return False
        action_alt = "|".join(sorted((re.escape(w) for w in action_words), key=len, reverse=True))
        vi_marker_alt = "|".join(self._NEGATION_MARKERS_VI)
        filler_alt = "|".join(self._NEGATION_FILLERS_VI)
        vi_pattern = rf"\b(?:{vi_marker_alt})\s+(?:(?:{filler_alt})\s+){{0,2}}(?:{action_alt})\b"
        if re.search(vi_pattern, text):
            return True
        en_marker_alt = "|".join(re.escape(w) for w in self._NEGATION_MARKERS_EN)
        en_pattern = rf"\b(?:{en_marker_alt})\s+(?:to\s+)?(?:{action_alt})\b"
        return re.search(en_pattern, text) is not None

    _SCHEDULE_WORDS = ("lich", "su kien", "hen", "hop", "meeting", "appointment", "calendar", "call", "event")
    _SCHEDULE_CREATE_ACTIONS = (
        "tao", "dat", "book", "them", "add", "create", "nhac toi", "remind",
        "set up", "arrange", "plan", "schedule",
    )
    # Negation-only: "xep" ("khong xep lich") is worth catching as a refusal
    # even though it isn't itself one of the positive-match action words
    # above (it belongs to _is_day_plan_request's DAY_PLAN_SIGNAL instead).
    _SCHEDULE_CREATE_NEGATION_ACTIONS = _SCHEDULE_CREATE_ACTIONS + ("xep",)
    _SCHEDULE_UPDATE_ACTIONS = (
        "doi", "sua", "cap nhat", "thay doi", "chuyen",
        "change", "update", "reschedule", "move", "postpone", "shift",
    )
    _SCHEDULE_DELETE_ACTIONS = ("xoa", "huy", "bo lich", "cancel", "delete")

    def _is_schedule_create(self, text):
        # "schedule" needs a word boundary -- a plain substring check would
        # also match inside "reschedule", which should go to
        # _is_schedule_update instead (checked right after this).
        if self._is_negated_action(text, self._SCHEDULE_CREATE_NEGATION_ACTIONS):
            return False
        action = self._contains_word(text, self._SCHEDULE_CREATE_ACTIONS)
        schedule = self._contains_word(text, self._SCHEDULE_WORDS)
        # In English, "schedule" can itself be the imperative verb, so the
        # object need not repeat "meeting/event": "Schedule maintenance
        # tomorrow" and "Schedule a review on January 5" are create requests.
        # Exclude common noun-style lookups such as "my schedule tomorrow".
        imperative_schedule = re.match(
            r"^(?:please\s+)?schedule\s+"
            r"(?!(?:my|the|for|on|today|tomorrow|this|next)\b)",
            text,
        ) is not None
        return action and (schedule or imperative_schedule)

    def _is_schedule_update(self, text):
        if self._is_negated_action(text, self._SCHEDULE_UPDATE_ACTIONS):
            return False
        action = self._contains_word(text, self._SCHEDULE_UPDATE_ACTIONS)
        schedule = self._contains_word(text, self._SCHEDULE_WORDS)
        return action and schedule

    def _is_schedule_delete(self, text):
        if self._is_negated_action(text, self._SCHEDULE_DELETE_ACTIONS):
            return False
        action = self._contains_word(text, self._SCHEDULE_DELETE_ACTIONS)
        schedule = self._contains_word(text, self._SCHEDULE_WORDS)
        return action and schedule

    def _is_schedule_lookup(self, text):
        if self._is_negated_action(text, self._SCHEDULE_CREATE_NEGATION_ACTIONS):
            return False
        if self._contains_word(text, (
            "lich tuan", "lich hom", "hom nay co lich", "co lich gi", "calendar",
            "meeting tuan", "su kien tuan", "appointments",
            "my schedule", "my calendar", "my meetings",
            "upcoming meetings", "upcoming events",
        )):
            return True
        # "do i have"/"what's on my" are too generic on their own (could be
        # about email, weather, anything) -- only count them when paired
        # with an explicit schedule word, same pattern as _is_schedule_create.
        has_question = self._contains_word(text, (
            "do i have", "what's on my", "whats on my", "what do i have",
        ))
        has_schedule_word = self._contains_word(text, self._SCHEDULE_WORDS + ("schedule",))
        if has_question and has_schedule_word:
            return True
        # A schedule word paired with an explicit date ("lich va su kien
        # 20/7", "lich hen ngay 20 thang 7") is a lookup -- create/update/
        # delete already matched earlier in detect()'s cascade and return
        # before this rule runs, so an action verb can't be present here.
        return has_schedule_word and self._explicit_date_from_text(text) is not None

    _EMAIL_MARK_ACTIONS = ("danh dau", "mark")

    def _is_email_mark_read(self, text):
        if self._is_negated_action(text, self._EMAIL_MARK_ACTIONS):
            return False
        if not self._contains_word(text, self._EMAIL_MARK_ACTIONS):
            return False
        has_read = self._contains_word(text, ("da doc", "read"))
        has_unread = self._contains_word(text, ("chua doc", "unread"))
        return has_read and not has_unread

    def _is_email_mark_unread(self, text):
        if self._is_negated_action(text, self._EMAIL_MARK_ACTIONS):
            return False
        if not self._contains_word(text, self._EMAIL_MARK_ACTIONS):
            return False
        return self._contains_word(text, ("chua doc", "unread"))

    _EMAIL_LOOKUP_ACTIONS = ("tim", "kiem", "check", "find", "search")

    def _is_email_lookup(self, text):
        if self._is_negated_action(text, self._EMAIL_LOOKUP_ACTIONS):
            return False
        return any(term in text for term in ("email", "gmail", "hop thu", "thu chua doc", "mail"))

    _HISTORY_LOOKUP_ACTIONS = ("xem", "cho xem", "check", "show")

    def _is_history_lookup(self, text):
        # Deliberately does NOT match bare "hoat dong"/"activity" -- those
        # words show up just as often in forward-looking requests ("hom nay
        # co cac hoat dong nhu...") as in actual history lookups, so they'd
        # misfire on checklist/day-plan messages. "lich su"/"history" are
        # unambiguous; the rest require an explicit retrospective phrase.
        if self._is_negated_action(text, self._HISTORY_LOOKUP_ACTIONS):
            return False
        if "lich su" in text or "history" in text:
            return True
        return any(term in text for term in (
            "da lam gi", "lam gi roi", "vua lam gi", "nhung gi da lam",
            "what did i do", "what have i done", "what i did",
        ))

    DAY_PLAN_SIGNAL = (
        "goi y lich", "sap xep lich", "xep lich", "len lich cho",
        "tao lich tu cac hoat dong", "xep gium lich", "xep giup lich",
        "suggest a schedule", "suggest times", "plan my day", "schedule my day",
        "arrange my day", "plan out my day", "organize my day",
    )

    _DAY_PLAN_ACTIONS = ("goi y", "sap xep", "xep", "suggest", "arrange", "plan", "organize")

    def _is_day_plan_request(self, text):
        """A list of activities the user wants slotted onto the CALENDAR
        (specific times, conflict-aware) -- distinct from
        _is_checklist_request, which just wants a flat to-do list with no
        time slots. Checked first in detect() so a message like 'cac hoat
        dong nhu X, Y, Z... goi y lich giup minh' (which also contains
        checklist.create's 'cac hoat dong' signal) routes to the calendar
        suggestion the user explicitly asked for, not a checklist."""
        if self._is_negated_action(text, self._DAY_PLAN_ACTIONS):
            return False
        if not any(term in text for term in self.DAY_PLAN_SIGNAL):
            has_arrange_word = any(term in text for term in (
                "sap xep", "xep", "arrange", "plan", "organize",
            ))
            has_schedule_word = any(term in text for term in ("lich", "calendar", "schedule"))
            if not (has_arrange_word and has_schedule_word):
                return False
        from routes.schedule import _split_day_plan_entries
        return len(_split_day_plan_entries(text)) >= 2

    _CHECKLIST_ACTIONS = ("them", "tao", "add", "create")

    def _is_checklist_request(self, text):
        if self._is_negated_action(text, self._CHECKLIST_ACTIONS):
            return False
        if not any(term in text for term in self.CHECKLIST_LIST_SIGNAL):
            return False
        from routes.schedule import _split_day_plan_entries
        return len(_split_day_plan_entries(text)) >= 2

    def _checklist_items_from_text(self, message):
        """Split the message into items and score each one's urgency. If no
        item carries its own urgency wording, fall back to the whole
        message's urgency applied uniformly (covers 'hom nay co may viec
        gap: X, Y, Z', where it's stated once for the whole list) -- but
        never let a message-wide 'gap' override an item that explicitly
        said it's low priority, or vice versa."""
        from routes.schedule import _extract_quick_time, _split_day_plan_entries
        entries = _split_day_plan_entries(message)
        priorities = [self._checklist_item_priority(entry["title"]) for entry in entries]
        if entries and all(priority == "normal" for priority in priorities):
            message_priority = self._checklist_item_priority(message)
            if message_priority != "normal":
                priorities = [message_priority] * len(entries)
        items = []
        for index, (entry, priority) in enumerate(zip(entries, priorities)):
            clock, explicit_time = _extract_quick_time(entry.get("raw") or entry["title"])
            time_value = clock.strftime("%H:%M") if explicit_time and clock else ""
            title = entry["title"]
            if time_value:
                title = f"{time_value} - {title}"
            items.append({
                "title": title,
                "priority": priority,
                "time": time_value,
                "_input_order": index,
            })
        items.sort(key=lambda item: (item["time"] == "", item["time"] or "99:99", item["_input_order"]))
        for item in items:
            item.pop("_input_order", None)
        return items

    _MODE_UPDATE_ACTIONS = ("doi che do", "chuyen che do", "set mode", "change mode")

    def _is_mode_update(self, text):
        if self._is_negated_action(text, self._MODE_UPDATE_ACTIONS):
            return False
        if not any(term in text for term in ("doi che do", "chuyen che do", "set mode", "mode", "che do lam viec")):
            return False
        return self._mode_from_text(text) is not None

    def _mode_from_text(self, text):
        for mode, aliases in self.MODE_ALIASES.items():
            if any(alias in text for alias in aliases):
                return mode
        return None

    @staticmethod
    def _limit_from_text(text, default=8, maximum=100):
        match = re.search(r"\b(\d{1,3})\b", text)
        if not match:
            return default
        return max(1, min(int(match.group(1)), maximum))

    def _calendar_window(self, text):
        now = self._local_now()
        monday = (now - timedelta(days=now.weekday())).date()
        explicit = self._explicit_date_from_text(text)
        if explicit:
            return {"label": "specific_date", "start": explicit.isoformat(), "end": explicit.isoformat()}
        if "tuan toi" in text or "tuan sau" in text or "next week" in text:
            start = monday + timedelta(days=7)
            end = start + timedelta(days=6)
            return {"label": "next_week", "start": start.isoformat(), "end": end.isoformat()}
        if "hom nay" in text or "today" in text:
            today = now.date()
            return {"label": "today", "start": today.isoformat(), "end": today.isoformat()}
        start = monday
        end = start + timedelta(days=6)
        return {"label": "this_week", "start": start.isoformat(), "end": end.isoformat()}

    def _email_date_window(self, text):
        """Detect an explicit day/week reference in an email-related message
        (e.g. 'hom nay', 'hom qua', a dd/mm/yyyy date) so email lookups can be
        scoped to exactly that range -- start/end are inclusive calendar dates
        in 'YYYY-MM-DD' form -- instead of just returning the most recent mail
        regardless of when it arrived."""
        now = self._local_now()
        explicit = self._explicit_date_from_text(text)
        if explicit:
            return {"start": explicit.isoformat(), "end": explicit.isoformat()}
        if "hom qua" in text or "yesterday" in text:
            day = (now - timedelta(days=1)).date()
            return {"start": day.isoformat(), "end": day.isoformat()}
        if "hom nay" in text or "today" in text:
            day = now.date()
            return {"start": day.isoformat(), "end": day.isoformat()}
        if "tuan truoc" in text or "last week" in text:
            monday = (now - timedelta(days=now.weekday() + 7)).date()
            return {"start": monday.isoformat(), "end": (monday + timedelta(days=6)).isoformat()}
        if "tuan nay" in text or "this week" in text:
            monday = (now - timedelta(days=now.weekday())).date()
            return {"start": monday.isoformat(), "end": (monday + timedelta(days=6)).isoformat()}
        if "tuan sau" in text or "tuan toi" in text or "next week" in text:
            monday = (now - timedelta(days=now.weekday()) + timedelta(days=7)).date()
            return {"start": monday.isoformat(), "end": (monday + timedelta(days=6)).isoformat()}
        return None

    @staticmethod
    def _explicit_date_from_text(text):
        def build_date(day, month, year_text=None):
            start_year = (
                int(year_text)
                if year_text
                else IntentOrchestrator._local_now().year
            )
            candidate_years = (
                (start_year,)
                if year_text
                else range(start_year, start_year + 8)
            )
            for candidate_year in candidate_years:
                try:
                    return datetime(candidate_year, month, day).date()
                except ValueError:
                    continue
            return None

        # Vietnamese natural date ("ngay 20 thang 7", optionally "nam 2026")
        # checked first -- it has its own unambiguous keywords, so it can't
        # collide with the numeric patterns below.
        match = re.search(r"\bngay\s+(\d{1,2})\s+thang\s+(\d{1,2})(?:\s+nam\s+(\d{4}))?\b", text)
        if match:
            day, month = int(match.group(1)), int(match.group(2))
            return build_date(day, month, match.group(3))

        match = re.search(r"\b(\d{1,4})[/-](\d{1,2})[/-](\d{1,4})\b", text)
        if match:
            first, second, third = match.groups()
            try:
                if len(first) == 4:
                    year, month, day = int(first), int(second), int(third)
                else:
                    day, month, year = int(first), int(second), int(third)
                    if year < 100:
                        year += 2000
                return datetime(year, month, day).date()
            except ValueError:
                return None

        # Bare "D/M" with no year (e.g. "su kien 20/7") -- very common in
        # casual Vietnamese phrasing. Assumes the current year. Slash only
        # (not hyphen) on purpose: a hyphenated "N-M" is far more often a
        # range in this domain's chat text ("2-3 ngay nua", "9-11 gio") than
        # a date, so allowing "-" here would misfire constantly. Only matches
        # when NOT already part of a longer D/M/Y run, so it never fires on a
        # 3-part date that merely failed the stricter check above.
        match = re.search(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])", text)
        if match:
            day, month = int(match.group(1)), int(match.group(2))
            return build_date(day, month)

        # English named dates: "July 30", "July 30, 2026", or
        # "30 July 2026".  Code-switched scheduling uses these frequently.
        month_numbers = {
            "january": 1, "jan": 1, "february": 2, "feb": 2,
            "march": 3, "mar": 3, "april": 4, "apr": 4,
            "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
            "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
            "october": 10, "oct": 10, "november": 11, "nov": 11,
            "december": 12, "dec": 12,
        }
        month_pattern = "|".join(
            sorted(month_numbers, key=len, reverse=True)
        )
        named = re.search(
            rf"\b({month_pattern})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?"
            rf"(?:,\s*|\s+)?(\d{{4}})?\b",
            text,
        )
        day_first = re.search(
            rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_pattern})\.?"
            rf"(?:,\s*|\s+)?(\d{{4}})?\b",
            text,
        )
        if named or day_first:
            if named:
                month_name, day_text, year_text = named.groups()
            else:
                day_text, month_name, year_text = day_first.groups()
            return build_date(
                int(day_text),
                month_numbers[month_name],
                year_text,
            )

        return None

    def _extract_date(self, text, now):
        explicit = self._explicit_date_from_text(text)
        if explicit:
            has_explicit_year = bool(
                re.search(r"\b\d{4}\b", text)
                or re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)
            )
            if explicit < now.date() and not has_explicit_year:
                try:
                    return explicit.replace(year=explicit.year + 1)
                except ValueError:
                    # 29 February without a year: use the next valid leap year.
                    for year in range(explicit.year + 1, explicit.year + 5):
                        try:
                            return explicit.replace(year=year)
                        except ValueError:
                            continue
            return explicit
        if "ngay mai" in text or "tomorrow" in text:
            return (now + timedelta(days=1)).date()
        if "hom nay" in text or "today" in text:
            return now.date()
        weekday_phrases = (
            (0, ("thu hai", "thu 2", "monday")),
            (1, ("thu ba", "thu 3", "tuesday")),
            (2, ("thu tu", "thu 4", "wednesday")),
            (3, ("thu nam", "thu 5", "thursday")),
            (4, ("thu sau", "thu 6", "friday")),
            (5, ("thu bay", "thu 7", "saturday")),
            (6, ("chu nhat", "sunday")),
        )
        target_weekday = next(
            (
                weekday
                for weekday, phrases in weekday_phrases
                if self._contains_word(text, phrases)
            ),
            None,
        )
        if target_weekday is not None:
            explicitly_next_week = any(term in text for term in (
                "tuan sau", "tuan toi", "next week",
            ))
            if explicitly_next_week:
                monday_next_week = (
                    now.date()
                    - timedelta(days=now.weekday())
                    + timedelta(days=7)
                )
                return monday_next_week + timedelta(days=target_weekday)
            delta = (target_weekday - now.weekday()) % 7
            # "next Friday" means the next occurrence of Friday. When today
            # is already Friday, that is seven days away; otherwise retain the
            # actual weekday delta instead of replacing it with a flat +7.
            if delta == 0:
                delta = 7
            return (now + timedelta(days=delta)).date()
        if "tuan sau" in text or "tuan toi" in text or "next week" in text:
            return (now + timedelta(days=7)).date()
        return None

    @staticmethod
    def _apply_period_of_day(hour, text):
        """Vietnamese times often skip am/pm and say "chieu"/"toi"/"trua"
        instead -- without this, "5 gio chieu" parses as 05:00 instead of
        the intended 17:00."""
        if 1 <= hour <= 11 and any(term in text for term in ("chieu", "toi", "trua")):
            return hour + 12
        return hour

    @staticmethod
    def _apply_am_pm(hour, period):
        if period == "pm" and 1 <= hour <= 11:
            return hour + 12
        if period == "am" and hour == 12:
            return 0
        return hour

    @classmethod
    def _extract_time(cls, text):
        if re.search(r"\b(?:noon|midday)\b", text):
            return datetime.strptime("12:00", "%H:%M").time()
        if re.search(r"\bmidnight\b", text):
            return datetime.strptime("00:00", "%H:%M").time()
        # English 12-hour formats ("3pm", "3:30 pm") first -- these are the
        # most common way English speakers write times, and don't overlap
        # with the Vietnamese "Ngio"/"N:MM" patterns below.
        match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})\s*(am|pm)\b", text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            hour = cls._apply_am_pm(hour, match.group(3))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
        match = re.search(r"(?<!\d)(\d{1,2})\s*(am|pm)\b", text)
        if match:
            hour = cls._apply_am_pm(int(match.group(1)), match.group(2))
            if 0 <= hour <= 23:
                return datetime.strptime(f"{hour:02d}:00", "%H:%M").time()
        match = re.search(r"(?<!\d)(\d{1,2})[:h](\d{2})(?!\d)", text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            hour = cls._apply_period_of_day(hour, text)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
        match = re.search(r"(?<!\d)(\d{1,2})\s*(?:gio|h)(?!\d)", text)
        if match:
            hour = cls._apply_period_of_day(int(match.group(1)), text)
            if 0 <= hour <= 23:
                return datetime.strptime(f"{hour:02d}:00", "%H:%M").time()
        return None

    @staticmethod
    def _extract_duration(text):
        match = re.search(r"\b(\d{1,3})\s*(?:phut|minute|minutes|min)\b", text)
        if match:
            return max(5, min(int(match.group(1)), 12 * 60))
        match = re.search(r"\b(\d{1,2})\s*(?:gio|hour|hours)\b", text)
        if match and any(term in text for term in ("keo dai", "duration", "trong vong")):
            return max(1, min(int(match.group(1)), 12)) * 60
        return None

    @staticmethod
    def _schedule_title(message, content=None):
        # If we already isolated the event's actual content (e.g. via a
        # "noi dung la:" marker), summarize THAT instead of the whole command
        # sentence -- this is what lets "Hay tao lich ... voi noi dung la: Hop
        # khach hang ban hop dong" produce the title "Hop khach hang ban hop
        # dong" instead of the entire instruction.
        if content:
            summarized = IntentOrchestrator._summarize_for_title(content)
            if summarized:
                return summarized

        clean = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "", message or "")
        clean = re.sub(r"\s+", " ", clean).strip(" .,")
        for _ in range(3):
            stripped = IntentOrchestrator.LEADING_FILLER_RE.sub("", clean, count=1)
            if stripped == clean:
                break
            clean = stripped.strip(" .,")

        prefixes = (
            "tao lich", "dat lich", "them lich", "book lich", "tao su kien",
            "dat cuoc hop", "nhac toi", "remind me",
            "schedule a", "schedule an", "schedule", "book a", "book an",
            "set up a", "set up an", "arrange a", "arrange an",
            "plan a", "plan an", "create a meeting", "add a meeting",
        )
        normalized = IntentOrchestrator.normalize(clean)
        for prefix in prefixes:
            if normalized.startswith(prefix):
                clean = clean[len(prefix):].strip(" :,-")
                break
        return (clean[:100] or "Lich hen")
