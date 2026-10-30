"""Shared runtime AI-usage gate for the Free/Plus split.

Call enforce_ai_quota(user_id, action) at the top of any route that makes a
real AI-provider call. Limits for both plans are editable from the admin
dashboard and each allowed call increments the daily counter atomically.
"""

from models.ai_usage import check_and_increment
from models import admin_ops
from models.subscription import is_premium


def enforce_ai_quota(user_id, action):
    """Always returns {"allowed": bool, "used": int, "limit": int,
    "remaining": int}. check_and_increment already computes used/limit on
    every call (one atomic DB round trip) -- previously this discarded them
    on the allowed path and returned bare None, so a caller had no way to
    tell the user how many uses of a Premium-gated action they have left
    today without a second query."""
    plan = 'plus' if is_premium(user_id) else 'free'
    limit = admin_ops.quota_limit(plan, action)
    allowed, used, limit = check_and_increment(user_id, action, limit=limit)
    return {"allowed": allowed, "used": used, "limit": limit, "remaining": max(0, limit - used)}
