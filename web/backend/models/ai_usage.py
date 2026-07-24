"""Daily usage counters for AI-costing actions, gating the free tier of the
Freemium/Premium split. Backed by the dedicated ai_usage_daily table (not the
generic Cache model, which only supports overwrite-set and would race under
concurrent requests) -- a single atomic
INSERT ... ON CONFLICT ... DO UPDATE SET count = count + 1 RETURNING count
keeps this race-free and shared across gunicorn workers/restarts.

Postgres-only, matching models/subscription.py.
"""

from models import postgres_db as pg

FREE_LIMITS = {
    "email_summary": 10,
}


def check_and_increment(user_id, action):
    """Atomically bump today's counter for (user_id, action) and report
    whether this call is still within the free-tier limit.

    Returns (allowed: bool, used: int, limit: int). If Postgres isn't
    configured (local SQLite dev), usage tracking is a no-op and everything
    is allowed -- gating only matters in production.
    """
    limit = FREE_LIMITS.get(action, 0)
    if not pg.enabled():
        return True, 0, limit
    if not user_id:
        return True, 0, limit
    with pg.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO ai_usage_daily (user_id, action, usage_date, count, updated_at)
            VALUES (%s, %s, CURRENT_DATE, 1, NOW())
            ON CONFLICT (user_id, action, usage_date)
            DO UPDATE SET count = ai_usage_daily.count + 1, updated_at = NOW()
            RETURNING count
            """,
            (user_id, action),
        ).fetchone()
        used = row["count"] if row else 1
        return used <= limit, used, limit


def get_usage_snapshot(user_id):
    """Today's usage per action, without incrementing anything. Used to
    surface "X/limit lượt hôm nay" on the profile/status payload."""
    snapshot = {action: {"used": 0, "limit": limit} for action, limit in FREE_LIMITS.items()}
    if not pg.enabled() or not user_id:
        return snapshot
    with pg.connection() as conn:
        rows = conn.execute(
            """
            SELECT action, count FROM ai_usage_daily
            WHERE user_id = %s AND usage_date = CURRENT_DATE
            """,
            (user_id,),
        ).fetchall()
        for row in rows:
            action = row["action"]
            if action in snapshot:
                snapshot[action]["used"] = row["count"]
    return snapshot
