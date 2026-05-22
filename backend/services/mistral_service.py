import re
import unicodedata


class MistralService:
    """Lightweight email classifier used by the email route.

    The previous implementation imported this service, but the file was
    missing. Keep classification local and deterministic so the inbox works
    even when no Mistral API key is configured.
    """

    CATEGORY_KEYWORDS = {
        "education": [
            "class", "course", "student", "teacher", "school", "lesson",
            "assignment", "exam", "grade", "education", "hoc", "lop",
            "sinh vien", "giao vien", "bai tap", "kiem tra",
        ],
        "work": [
            "work", "task", "project", "deadline", "report", "team",
            "manager", "office", "cong viec", "du an", "bao cao",
        ],
        "meeting": [
            "meeting", "schedule", "appointment", "calendar", "zoom",
            "teams", "google meet", "call", "hop", "lich", "gap",
            "thao luan",
        ],
        "promotion": [
            "sale", "discount", "promotion", "coupon", "offer", "deal",
            "khuyen mai", "giam gia", "uu dai",
        ],
        "finance": [
            "invoice", "payment", "receipt", "bank", "salary", "tax",
            "finance", "bill", "thanh toan", "hoa don", "tai chinh",
        ],
        "personal": [
            "family", "friend", "birthday", "personal", "invite",
            "gia dinh", "ban be", "sinh nhat", "ca nhan",
        ],
        "other": [],
    }

    def batch_classify_emails(self, emails, filter_type="all"):
        if not emails:
            return []

        category = (filter_type or "all").strip().lower()
        if category == "all" or category not in self.CATEGORY_KEYWORDS:
            return emails

        if category == "other":
            known_categories = [key for key in self.CATEGORY_KEYWORDS if key != "other"]
            return [
                email for email in emails
                if not any(self._matches(email, known) for known in known_categories)
            ]

        matched = [email for email in emails if self._matches(email, category)]
        return matched if matched else emails

    def _matches(self, email, category):
        keywords = self.CATEGORY_KEYWORDS.get(category, [])
        if not keywords:
            return False

        text = self._normalize(" ".join([
            str(email.get("subject", "") or ""),
            str(email.get("sender", "") or ""),
            str(email.get("snippet", "") or ""),
            str(email.get("body", "") or ""),
        ]))

        return any(re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in keywords)

    def _normalize(self, value):
        decomposed = unicodedata.normalize("NFD", value.lower())
        without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", without_marks)
