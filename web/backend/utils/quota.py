"""Shared runtime AI-usage gate for the Free/Plus split.

Call enforce_ai_quota(user_id, action) at the top of any route that makes a
real AI-provider call. Limits for both plans are editable from the admin
dashboard and each allowed call increments the daily counter atomically.
"""

from models.ai_usage import check_and_increment
from models import admin_ops
from models.subscription import is_premium


def enforce_ai_quota(user_id, action):
    """Returns None if the call may proceed, or a dict with 'used'/'limit'
    keys (for the caller to turn into a 403 ai_limit_reached response) if the
    plan's daily limit for `action` has been reached."""
    plan = 'plus' if is_premium(user_id) else 'free'
    limit = admin_ops.quota_limit(plan, action)
    allowed, used, limit = check_and_increment(user_id, action, limit=limit)
    if allowed:
        return None
    return {"used": used, "limit": limit}
