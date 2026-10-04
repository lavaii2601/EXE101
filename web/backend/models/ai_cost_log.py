"""Per-call LLM cost/token/latency observability.

Separate from models/ai_usage.py's ai_usage_daily, which gates the
Free/Premium feature-quota *counts* -- this tracks actual $ cost/tokens/
latency per real provider call, for a future admin cost dashboard. Never
persists API keys, email bodies, or user messages -- call metadata only.

Postgres-only (matching models/ai_usage.py): a no-op in local SQLite dev
since this is an admin-observability concern, not required for feature
correctness. record_call() is best-effort and never raises -- a logging
failure must not break the AI response path it's observing.
"""

import logging

from config import Config
from models import postgres_db as pg

logger = logging.getLogger(__name__)


def record_call(
    user_id=None,
    workspace_id=None,
    task='chat',
    tier='strong',
    provider='demo',
    model=None,
    success=True,
    error_type=None,
    input_tokens=None,
    output_tokens=None,
    estimated_cost_usd=None,
    latency_ms=0,
    cache_hit=False,
):
    if not Config.AI_COST_TRACKING_ENABLED or not pg.enabled():
        return
    try:
        with pg.connection() as conn:
            conn.execute(
                """
                INSERT INTO ai_cost_log (
                    user_id, workspace_id, task, tier, provider, model, success,
                    error_type, input_tokens, output_tokens, estimated_cost_usd,
                    latency_ms, cache_hit
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id, workspace_id, task, tier, provider, model, success,
                    error_type, input_tokens, output_tokens, estimated_cost_usd,
                    latency_ms, cache_hit,
                ),
            )
    except Exception:
        logger.warning("Failed to record ai_cost_log row", exc_info=True)


def get_usage_summary(user_id=None, since=None):
    """Per (task, tier, provider) aggregate, for a future admin dashboard.

    No route calls this yet -- it exists so that dashboard can be added
    later without touching services/ai_service.py again.
    """
    if not pg.enabled():
        return []
    with pg.connection() as conn:
        rows = conn.execute(
            """
            SELECT task, tier, provider, COUNT(*) AS calls,
                   SUM(COALESCE(input_tokens, 0)) AS input_tokens,
                   SUM(COALESCE(output_tokens, 0)) AS output_tokens,
                   SUM(COALESCE(estimated_cost_usd, 0)) AS estimated_cost_usd,
                   AVG(latency_ms) AS avg_latency_ms
            FROM ai_cost_log
            WHERE (%(user_id)s::TEXT IS NULL OR user_id = %(user_id)s)
              AND (%(since)s::TIMESTAMPTZ IS NULL OR created_at >= %(since)s)
            GROUP BY task, tier, provider
            ORDER BY estimated_cost_usd DESC
            """,
            {'user_id': user_id, 'since': since},
        ).fetchall()
        return pg.normalize_rows(rows)
