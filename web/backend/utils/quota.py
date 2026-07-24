"""Shared free-tier AI-usage gate for the Freemium/Premium split.

Call enforce_ai_quota(user_id, action) at the top of any route that makes a
real AI-provider call. Premium users (models.subscription.is_premium) always
pass. Free users are checked against models.ai_usage.FREE_LIMITS and get one
daily-counter increment per allowed call.
"""

from models.ai_usage import check_and_increment
from models.subscription import is_premium


def enforce_ai_quota(user_id, action):
    """Returns None if the call may proceed, or a dict with 'used'/'limit'
    keys (for the caller to turn into a 403 ai_limit_reached response) if the
    free-tier daily limit for `action` has been reached."""
    if is_premium(user_id):
        return None
    allowed, used, limit = check_and_increment(user_id, action)
    if allowed:
        return None
    return {"used": used, "limit": limit}
