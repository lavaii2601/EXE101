import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta

from models.history import History
from models.schedule import Schedule
from models.user import User
from services.schedule_service import ScheduleService

logger = logging.getLogger(__name__)


class IntentOrchestrator:
    """Normalize user prompts into canonical workspace actions."""

    AI_INTENTS = (
        "email.latest_summary", "email.search", "schedule.create", "schedule.update",
        "schedule.delete", "schedule.list", "email.mark_read", "email.mark_unread",
        "history.list", "settings.update_mode", "chat.freeform",
    )

    WEEKDAY_NAMES_VN = (
        "Thu Hai", "Thu Ba", "Thu Tu", "Thu Nam", "Thu Sau", "Thu Bay", "Chu Nhat",
    )

    MODE_ALIASES = {
        "student": ("student", "sinh vien", "hoc sinh", "di hoc"),
        "worker": ("worker", "nhan vien", "di lam", "cong so", "van phong"),
        "freelancer": ("freelancer", "tu do", "lam freelance", "freelance"),
        "creator": ("creator", "sang tao", "content", "creator"),
        "business": ("business", "kinh doanh", "doanh nghiep", "chu doanh nghiep"),
        "mentor": ("mentor", "co van", "huong dan"),
        "teacher": ("teacher", "giao vien", "giang vien", "day hoc"),
    }

    def detect(self, message):
        text = self.normalize(message)
        entities = {}
        intent = "chat.freeform"
        confidence = 0.35
        requires_confirmation = False
        refresh_targets = []

        if self._is_latest_email_summary(text):
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
        elif self._is_history_lookup(text):
            intent = "history.list"
            confidence = 0.86
            entities["limit"] = self._limit_from_text(text, default=8, maximum=20)
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
        elif self._is_email_mark_read(text):
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
        "- 'Nay minh bao ban lam gi roi nhi' => history.list.\n"
        "- 'Ban nghi gi ve lam viec tu xa' => chat.freeform (khong khop muc nao tren).\n"
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
        "goi lai", "goi cho", "goi dien",
        "email", "mail", "gmail", "hop thu", "inbox", "thu tu",
        "lich su", "hoat dong", "history", "activity",
        "da lam gi", "lam gi roi", "nho lai", "nhac lai", "vua nay", "vua roi",
        "mode", "che do lam viec", "doi che do", "chuyen che do",
    )

    TIME_HINT_PATTERN = re.compile(
        r"(?<!\d)\d{1,2}\s*(?:gio|h)(?::?\d{2})?(?!\d)"
        r"|ngay mai|hom nay|hom qua|sang nay|chieu nay|toi nay|sang mai|chieu mai|toi mai"
        r"|tuan nay|tuan sau|tuan toi|tuan truoc"
        r"|thu hai|thu ba|thu tu|thu nam|thu sau|thu bay|chu nhat"
        r"|\d{1,3}\s*(?:phut|gio|tieng)\s*nua"
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
    )
    TITLE_MARKER_RE = re.compile(
        r"(?:" + "|".join(re.escape(t) for t in sorted(set(_TITLE_MARKER_TERMS), key=len, reverse=True)) + r")"
        r"\s*[:\-]?\s*([^,.;\n]+)",
        re.IGNORECASE,
    )

    # Leading filler ("Hay", "Ban hay", "Giup toi", ...) stripped before
    # falling back to the whole message as the title source, so "Hay tao
    # lich..." doesn't leave "Hay" stuck onto the auto-generated title.
    LEADING_FILLER_RE = re.compile(
        r"^\s*(?:xin\s+)?(?:hãy|hay|bạn hãy|ban hay|làm ơn|lam on|giúp tôi|giup toi|"
        r"giúp mình|giup minh|cho tôi|cho toi|mình muốn|minh muon|tôi muốn|toi muon|"
        r"vui lòng|vui long)\s+",
        re.IGNORECASE,
    )

    def _has_actionable_hint(self, message):
        text = self.normalize(message)
        if any(hint in text for hint in self.ACTIONABLE_HINTS):
            return True
        if any(alias in text for aliases in self.MODE_ALIASES.values() for alias in aliases):
            return True
        return bool(self.TIME_HINT_PATTERN.search(text))

    def detect_with_ai(self, message, ai_service, user_id=None, db_path=None,
                        chat_session_id=None, confidence_threshold=0.6):
        """Run the deterministic rules first; only ask the AI to read the
        message when the rules aren't confident (i.e. it fell through to
        chat.freeform) AND the message at least hints at a recognizable
        domain. This keeps clear-cut requests AND plain chit-chat fast and
        free, while letting paraphrased/indirect action requests -- including
        follow-ups that only make sense given recent chat turns -- still get
        recognized.
        """
        result = self.detect(message)
        if result.get("confidence", 0) >= confidence_threshold or not ai_service:
            return result
        if not self._has_actionable_hint(message):
            return result
        try:
            ai_result = self._detect_via_ai(
                message, ai_service, user_id=user_id, db_path=db_path, chat_session_id=chat_session_id,
            )
        except Exception:
            logger.warning("AI-assisted intent detection failed", exc_info=True)
            ai_result = None
        return ai_result or result

    def _detect_via_ai(self, message, ai_service, user_id=None, db_path=None, chat_session_id=None):
        now = datetime.now()
        recent_turns = self._recent_turns_text(db_path, chat_session_id)
        system_message = {
            "role": "system",
            "content": (
                "Ban la bo phan loai y dinh cho mot tro ly cong viec. Doc cau nhan tu "
                "nguoi dung (va lich su hoi thoai gan day neu co) va TRA VE DUY NHAT mot "
                "JSON object hop le theo dung cau truc duoc yeu cau, khong giai thich them, "
                "khong dung markdown."
            ),
        }
        user_message = {
            "role": "user",
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

    def _recent_turns_text(self, db_path, chat_session_id, limit=3):
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
            user_text = self._squash(record.get("user_message"))[:200]
            assistant_text = self._squash(record.get("assistant_response"))[:200]
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
            f"THOI DIEM HIEN TAI: {now.strftime('%Y-%m-%d %H:%M')} ({weekday}), GMT+7\n\n"
            "Cac loai y dinh hop le (chon dung 1 gia tri cho truong \"intent\"):\n"
            "- schedule.create: muon tao lich hen/su kien/nhac nho moi\n"
            "- schedule.update: muon doi/sua thoi gian hoac thong tin cua lich hen DA CO san "
            "(vi du 'doi gio hop voi sep', 'chuyen lich kham rang sang ngay khac')\n"
            "- schedule.delete: muon xoa/huy lich hen DA CO san "
            "(vi du 'xoa lich hop ngay mai', 'huy cuoc hen voi khach')\n"
            "- schedule.list: muon xem lich/su kien da co\n"
            "- email.latest_summary: muon tom tat (cac) email moi nhat trong hop thu\n"
            "- email.search: muon tim/xem email theo tu khoa hoac nguoi gui\n"
            "- email.mark_read: muon danh dau (cac) email DA DOC "
            "(vi du 'danh dau da xem email tu chi Lan')\n"
            "- email.mark_unread: muon danh dau (cac) email CHUA DOC "
            "(vi du 'danh dau email do la chua xem')\n"
            "- history.list: muon xem lich su hoat dong/da lam gi\n"
            "- settings.update_mode: muon doi che do lam viec "
            "(student, worker, freelancer, creator, business, mentor, teacher)\n"
            "- chat.freeform: tat ca truong hop khac (hoi dap thong thuong)\n\n"
            f"{self.FEW_SHOT_REASONING}\n"
            "Tra ve CHINH XAC mot JSON object theo cau truc:\n"
            "{\n"
            '  "intent": "<mot trong cac gia tri tren>",\n'
            '  "confidence": <so tu 0 den 1>,\n'
            '  "schedule": {"title": "", "description": "", "start_time": "YYYY-MM-DDTHH:MM:SS", '
            '"end_time": "YYYY-MM-DDTHH:MM:SS hoac null", "attendees": [], "location": ""},\n'
            '  "window": {"label": "today|yesterday|this_week|next_week|last_week|custom", '
            '"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},\n'
            '  "email_count": <1-5>,\n'
            '  "email_query": {"sender": "", "keyword": "", "unread_only": false},\n'
            '  "history_limit": <1-20>,\n'
            '  "mode": "<student|worker|freelancer|creator|business|mentor|teacher hoac null>"\n'
            "}\n"
            "Chi dien cac truong lien quan toi intent da chon, cac truong khac de null/bo qua. "
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
            entities["count"] = self._coerce_int(data.get("email_count"), default=1, minimum=1, maximum=5)
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
            entities["limit"] = self._coerce_int(data.get("history_limit"), default=8, minimum=1, maximum=20)
            refresh_targets = ["history"]
        elif intent == "settings.update_mode":
            mode = str(data.get("mode") or "").strip().lower()
            if mode not in self.MODE_ALIASES:
                return None
            entities["mode"] = mode
            refresh_targets = ["settings", "profile", "history"]
        else:
            return {
                "intent": "chat.freeform",
                "confidence": min(confidence, 0.5),
                "entities": {},
                "requires_confirmation": False,
                "refresh_targets": [],
                "ai_assisted": True,
            }

        return {
            "intent": intent,
            "confidence": confidence,
            "entities": entities,
            "requires_confirmation": requires_confirmation,
            "refresh_targets": refresh_targets,
            "ai_assisted": True,
        }

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
        description = str(schedule.get("description") or "").strip() or marked_content or str(message or "").strip()
        title = str(schedule.get("title") or "").strip() or marked_title or self._schedule_title(message, marked_content)
        return {
            "title": title[:150],
            "description": description,
            "start_time": start_time,
            "end_time": end_time,
            "attendees": attendees,
            "location": str(schedule.get("location") or "").strip(),
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
            mode = entities.get("mode")
            if not mode:
                return None
            User.get_or_create(user_id)
            User.update(
                user_id,
                user_mode=mode,
                user_mode_selected_at=datetime.now().isoformat(),
            )
            labels = {
                "student": "Student",
                "worker": "Worker",
                "freelancer": "Freelancer",
                "creator": "Creator",
                "business": "Business",
                "mentor": "Mentor",
                "teacher": "Teacher",
            }
            return {
                "response": f"Da cap nhat che do lam viec sang {labels.get(mode, mode)}.",
                "workspace_sources": ["profile"],
                "refresh_targets": ["settings", "profile", "history"],
                "action_type": "settings_updated",
            }

        if intent == "history.list":
            limit = entities.get("limit") or 8
            records = History.get_recent(limit=limit, db_path=db_path)
            if not records:
                response = "Chua co lich su hoat dong nao."
            else:
                lines = ["Lich su hoat dong gan day:"]
                for index, record in enumerate(records, start=1):
                    created_at = record.get("created_at") or "khong ro thoi gian"
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
                    f"{schedule.get('title') or 'Lich hen'} luc {schedule.get('start_time')}."
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
            "start_time": schedule.get("start_time"),
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
        now = datetime.now()
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
        return {
            "title": marked_title or self._schedule_title(message, marked_content),
            "description": marked_content or message,
            "start_time": start_time,
            "end_time": end_time,
            "attendees": attendees,
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

    def _is_latest_email_summary(self, text):
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
            return max(1, min(int(match.group(1)), 5))
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

    def _is_schedule_create(self, text):
        action = any(term in text for term in ("tao", "dat", "book", "them", "add", "nhac toi", "remind"))
        schedule = any(term in text for term in ("lich", "su kien", "hen", "hop", "meeting", "appointment", "calendar"))
        return action and schedule

    def _is_schedule_update(self, text):
        action = any(term in text for term in ("doi", "sua", "cap nhat", "thay doi", "chuyen"))
        schedule = any(term in text for term in ("lich", "su kien", "hen", "hop", "meeting", "appointment", "calendar"))
        return action and schedule

    def _is_schedule_delete(self, text):
        action = any(term in text for term in ("xoa", "huy", "bo lich", "cancel", "delete"))
        schedule = any(term in text for term in ("lich", "su kien", "hen", "hop", "meeting", "appointment", "calendar"))
        return action and schedule

    def _is_schedule_lookup(self, text):
        return any(term in text for term in (
            "lich tuan", "lich hom", "hom nay co lich", "co lich gi", "calendar",
            "meeting tuan", "su kien tuan", "appointments"
        ))

    def _is_email_mark_read(self, text):
        if not any(term in text for term in ("danh dau", "mark")):
            return False
        return any(term in text for term in ("da doc", "read")) and "chua doc" not in text and "unread" not in text

    def _is_email_mark_unread(self, text):
        if not any(term in text for term in ("danh dau", "mark")):
            return False
        return any(term in text for term in ("chua doc", "unread"))

    def _is_email_lookup(self, text):
        return any(term in text for term in ("email", "gmail", "hop thu", "thu chua doc", "mail"))

    def _is_history_lookup(self, text):
        return any(term in text for term in ("lich su", "hoat dong", "da lam gi", "history", "activity"))

    def _is_mode_update(self, text):
        if not any(term in text for term in ("doi che do", "chuyen che do", "set mode", "mode", "che do lam viec")):
            return False
        return self._mode_from_text(text) is not None

    def _mode_from_text(self, text):
        for mode, aliases in self.MODE_ALIASES.items():
            if any(alias in text for alias in aliases):
                return mode
        return None

    @staticmethod
    def _limit_from_text(text, default=8, maximum=20):
        match = re.search(r"\b(\d{1,2})\b", text)
        if not match:
            return default
        return max(1, min(int(match.group(1)), maximum))

    def _calendar_window(self, text):
        now = datetime.now()
        monday = (now - timedelta(days=now.weekday())).date()
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
        now = datetime.now()
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
        match = re.search(r"\b(\d{1,4})[/-](\d{1,2})[/-](\d{1,4})\b", text)
        if not match:
            return None
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

    def _extract_date(self, text, now):
        explicit = self._explicit_date_from_text(text)
        if explicit:
            return explicit
        if "ngay mai" in text or "tomorrow" in text:
            return (now + timedelta(days=1)).date()
        if "hom nay" in text or "today" in text:
            return now.date()
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

    @classmethod
    def _extract_time(cls, text):
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
            "dat cuoc hop", "nhac toi", "remind me"
        )
        normalized = IntentOrchestrator.normalize(clean)
        for prefix in prefixes:
            if normalized.startswith(prefix):
                clean = clean[len(prefix):].strip(" :,-")
                break
        return (clean[:100] or "Lich hen")
