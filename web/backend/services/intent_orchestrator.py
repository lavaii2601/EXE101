import re
import unicodedata
from datetime import datetime, timedelta

from models.history import History
from models.schedule import Schedule
from models.user import User
from services.schedule_service import ScheduleService


class IntentOrchestrator:
    """Normalize user prompts into canonical workspace actions."""

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
            refresh_targets = ["email", "history"]
        elif self._is_mode_update(text):
            intent = "settings.update_mode"
            confidence = 0.9
            entities["mode"] = self._mode_from_text(text)
            refresh_targets = ["settings", "history"]
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
            refresh_targets = ["schedule", "history"]
        elif self._is_schedule_lookup(text):
            intent = "schedule.list"
            confidence = 0.82
            entities["window"] = self._calendar_window(text)
            refresh_targets = ["schedule", "history"]
        elif self._is_email_lookup(text):
            intent = "email.search"
            confidence = 0.74
            refresh_targets = ["email", "history"]

        return {
            "intent": intent,
            "confidence": confidence,
            "entities": entities,
            "requires_confirmation": requires_confirmation,
            "refresh_targets": refresh_targets,
        }

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
                "refresh_targets": ["settings", "history"],
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
                "action_type": "history_lookup",
            }

        if intent == "schedule.create":
            schedule = entities.get("schedule") or {}
            if not schedule.get("start_time"):
                return {
                    "response": "Minh co the tao lich, nhung ban cho minh them ngay/gio cu the nhe.",
                    "schedule_suggestion": schedule,
                    "workspace_sources": ["calendar"],
                    "refresh_targets": ["schedule", "history"],
                    "action_type": "chat",
                }
            return {
                "response": (
                    "Minh da hieu ban muon tao lich. Hay xac nhan neu thong tin nay dung: "
                    f"{schedule.get('title') or 'Lich hen'} luc {schedule.get('start_time')}."
                ),
                "schedule_suggestion": schedule,
                "workspace_sources": ["calendar"],
                "refresh_targets": ["schedule", "history"],
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
            db_path=db_path,
        )
        return {
            "id": schedule_id,
            "title": schedule.get("title"),
            "start_time": schedule.get("start_time"),
        }

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
        title = self._schedule_title(message)
        return {
            "title": title,
            "description": message,
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

    def _is_schedule_lookup(self, text):
        return any(term in text for term in (
            "lich tuan", "lich hom", "hom nay co lich", "co lich gi", "calendar",
            "meeting tuan", "su kien tuan", "appointments"
        ))

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

    def _extract_date(self, text, now):
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
        if "ngay mai" in text or "tomorrow" in text:
            return (now + timedelta(days=1)).date()
        if "hom nay" in text or "today" in text:
            return now.date()
        if "tuan sau" in text or "tuan toi" in text or "next week" in text:
            return (now + timedelta(days=7)).date()
        return None

    @staticmethod
    def _extract_time(text):
        match = re.search(r"(?<!\d)(\d{1,2})[:h](\d{2})(?!\d)", text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
        match = re.search(r"(?<!\d)(\d{1,2})\s*(?:gio|h)(?!\d)", text)
        if match:
            hour = int(match.group(1))
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
    def _schedule_title(message):
        clean = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "", message or "")
        clean = re.sub(r"\s+", " ", clean).strip(" .,")
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
