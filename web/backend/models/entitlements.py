"""Canonical Freemium/Premium feature limits and comparison copy.

models/subscription.py answers "is this user premium"; this module answers
"what does that tier actually get". Routes/services read the *_LIMITS dicts
to gate behavior, and routes/user.py serializes FEATURE_TABLE so web and
mobile render the plan-comparison table from here instead of hardcoding
their own copies -- those had already drifted (93-day backend clamp vs a
"365 days" vs "unlimited" marketing claim for the same feature).
"""

FREE_LIMITS = {
    "email_summary_daily": 10,
    "chat_retention_days": 30,
    "analytics_unlocked": False,
    "multi_step_tools": False,
}

PREMIUM_LIMITS = {
    "email_summary_daily": None,  # None = unlimited
    "chat_retention_days": 365,
    "analytics_unlocked": True,
    "multi_step_tools": True,
}


def limits_for(is_premium):
    return PREMIUM_LIMITS if is_premium else FREE_LIMITS


# Student-mode-only features (see routes/course.py, routes/chat.py's
# summarize-study, overview_service.py's upcoming_deadlines, and
# routes/schedule.py's checklist subject grouping). These don't exist for
# any other user_mode at all -- callers must check user_mode == 'student'
# first; is_premium only decides the depth within that mode, mirroring the
# global FREE_LIMITS/PREMIUM_LIMITS split above but scoped to Student.
STUDENT_FREE_LIMITS = {
    "study_summary_daily": 5,
    "gpa_persist": False,
    "checklist_subject_grouping": False,
    "deadline_countdown_full_list": False,
}

STUDENT_PREMIUM_LIMITS = {
    "study_summary_daily": None,  # None = unlimited
    "gpa_persist": True,
    "checklist_subject_grouping": True,
    "deadline_countdown_full_list": True,
}


def student_limits_for(is_premium):
    return STUDENT_PREMIUM_LIMITS if is_premium else STUDENT_FREE_LIMITS


def student_context(user_id):
    """Resolve (is_student, is_premium) for a user in one place, since every
    student-only route needs both checks: user_mode == 'student' decides
    whether the feature exists at all, is_premium then decides free vs
    premium depth within it (student_limits_for)."""
    from models.user import User
    from models import subscription as subscription_model

    user = User.get(user_id) or {}
    is_student = (user.get('user_mode') or '').strip().lower() == 'student'
    return is_student, subscription_model.is_premium(user_id)


FEATURE_TABLE = [
    {
        "key": "chat",
        "label": "Chat với Bob (AI)",
        "free": "Không giới hạn",
        "premium": "Không giới hạn",
    },
    {
        "key": "compose",
        "label": "Soạn trả lời AI",
        "free": "Không giới hạn",
        "premium": "Không giới hạn",
    },
    {
        "key": "email_summary",
        "label": "Tóm tắt email AI",
        "free": "10 lượt/ngày",
        "premium": "Không giới hạn",
    },
    {
        "key": "multi_step",
        "label": "Xử lý nhiều bước trong 1 câu hỏi",
        "free": "Chưa hỗ trợ",
        "premium": "Có",
        "free_locked": True,
    },
    {
        "key": "ai_quality",
        "label": "Chất lượng phản hồi AI",
        "free": "Tiêu chuẩn",
        "premium": "Nâng cao (ưu tiên mô hình tốt hơn, phản hồi chi tiết hơn)",
    },
    {
        "key": "chat_retention",
        "label": "Lưu trữ đoạn chat",
        "free": "30 ngày",
        "premium": "365 ngày",
    },
    {
        "key": "analytics",
        "label": "Phân tích tuần",
        "free": "Khóa",
        "premium": "Mở khóa",
        "free_locked": True,
    },
]
