"""Persistent runtime controls and privacy-safe operations telemetry.

This module deliberately stores metadata only. It never accepts request
bodies, OAuth credentials, prompts, email content, provider keys or secrets.
Every writer is best-effort so observability cannot take the product down.
"""

import copy
import logging
from datetime import datetime, timezone

from flask import current_app, has_app_context

from models import postgres_db as pg


logger = logging.getLogger(__name__)

CONTROLS_KEY = "ai_controls_v1"
DEFAULT_CONTROLS = {
    "quotas": {
        "free": {
            "bob_chat": 30,
            "email_summary": 10,
            "daily_overview": 3,
            "claude": 5,
            "study_summary": 5,
        },
        "plus": {
            "bob_chat": 300,
            "email_summary": 100,
            "daily_overview": 30,
            "claude": 50,
            "study_summary": 50,
        },
    },
    "budgets": {
        "monthly_usd": 20.0,
        "openai_usd": 12.0,
        "claude_usd": 8.0,
        "warning_usd": 10.0,
        "warning_high_usd": 15.0,
        "critical_usd": 18.0,
        "hard_limit_usd": 20.0,
        "hard_stop_enabled": True,
    },
}


def _skip_best_effort_writes():
    """Keep unrelated route tests from opening a real telemetry connection."""
    return has_app_context() and current_app.testing


def _deep_merge(base, override):
    result = copy.deepcopy(base)
    if not isinstance(override, dict):
        return result
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_controls():
    if not pg.enabled():
        return copy.deepcopy(DEFAULT_CONTROLS)
    try:
        with pg.connection() as conn:
            row = conn.execute(
                "SELECT value FROM admin_settings WHERE key = %s",
                (CONTROLS_KEY,),
            ).fetchone()
        value = pg.normalize_row(row).get("value") if row else None
        return _deep_merge(DEFAULT_CONTROLS, value)
    except Exception:
        logger.warning("Could not load admin AI controls", exc_info=True)
        return copy.deepcopy(DEFAULT_CONTROLS)


def validate_controls(value):
    merged = _deep_merge(DEFAULT_CONTROLS, value)
    quotas = merged.get("quotas") or {}
    for plan in ("free", "plus"):
        plan_values = quotas.get(plan)
        if not isinstance(plan_values, dict):
            raise ValueError(f"invalid_{plan}_quotas")
        for action in DEFAULT_CONTROLS["quotas"][plan]:
            try:
                limit = int(plan_values.get(action))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid_quota_{plan}_{action}") from exc
            if limit < 0 or limit > 1_000_000:
                raise ValueError(f"invalid_quota_{plan}_{action}")
            plan_values[action] = limit

    budgets = merged.get("budgets") or {}
    numeric_keys = (
        "monthly_usd", "openai_usd", "claude_usd", "warning_usd",
        "warning_high_usd", "critical_usd", "hard_limit_usd",
    )
    for key in numeric_keys:
        try:
            budgets[key] = round(float(budgets.get(key)), 6)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid_budget_{key}") from exc
        if budgets[key] < 0 or budgets[key] > 10_000_000:
            raise ValueError(f"invalid_budget_{key}")
    if not (
        budgets["warning_usd"] <= budgets["warning_high_usd"]
        <= budgets["critical_usd"] <= budgets["hard_limit_usd"]
        <= budgets["monthly_usd"]
    ):
        raise ValueError("invalid_budget_threshold_order")
    budgets["hard_stop_enabled"] = bool(budgets.get("hard_stop_enabled"))
    merged["budgets"] = budgets
    return merged


def save_controls(value, admin_user_id):
    controls = validate_controls(value)
    if not pg.enabled():
        return controls
    with pg.connection() as conn:
        conn.execute(
            """
            INSERT INTO admin_settings (key, value, updated_by_user_id, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = NOW()
            """,
            (CONTROLS_KEY, pg.json_value(controls), admin_user_id),
        )
    return controls


def quota_limit(plan, action):
    controls = get_controls()
    return int(controls["quotas"].get(plan, {}).get(action, 0))


def current_budget_state(provider=None):
    controls = get_controls()
    budgets = controls["budgets"]
    total = 0.0
    provider_total = 0.0
    if pg.enabled():
        try:
            with pg.connection() as conn:
                row = conn.execute(
                    """
                    SELECT
                        COALESCE(SUM(estimated_cost_usd), 0) AS total,
                        COALESCE(SUM(estimated_cost_usd) FILTER (WHERE provider = %s), 0) AS provider_total
                    FROM ai_cost_log
                    WHERE created_at >= DATE_TRUNC('month', NOW())
                    """,
                    (provider or "",),
                ).fetchone()
            normalized = pg.normalize_row(row)
            total = float(normalized.get("total") or 0)
            provider_total = float(normalized.get("provider_total") or 0)
        except Exception:
            logger.warning("Could not read current AI budget state", exc_info=True)
    provider_limit = budgets.get(f"{provider}_usd") if provider in {"openai", "claude"} else None
    hard_stop = bool(budgets.get("hard_stop_enabled"))
    allowed = not hard_stop or (
        total < float(budgets["hard_limit_usd"])
        and (provider_limit is None or provider_total < float(provider_limit))
    )
    return {
        "allowed": allowed,
        "month_cost_usd": total,
        "provider_cost_usd": provider_total,
        "provider_limit_usd": provider_limit,
        "controls": controls,
    }


def record_admin_audit(admin_user_id, action, target_type, target_id=None,
                       before=None, after=None, request_id=None):
    if _skip_best_effort_writes() or not pg.enabled():
        return
    try:
        with pg.connection() as conn:
            conn.execute(
                """
                INSERT INTO admin_audit_events (
                    admin_user_id, action, target_type, target_id,
                    before_state, after_state, request_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    admin_user_id, action, target_type, target_id,
                    pg.json_value(before) if before is not None else None,
                    pg.json_value(after) if after is not None else None,
                    request_id,
                ),
            )
    except Exception:
        logger.warning("Could not write admin audit event", exc_info=True)


def touch_user(user_id, login=False):
    if _skip_best_effort_writes() or not pg.enabled() or not user_id:
        return
    try:
        with pg.connection() as conn:
            if login:
                conn.execute(
                    """
                    UPDATE users SET last_login_at = NOW(), last_active_at = NOW()
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
            else:
                conn.execute(
                    """
                    UPDATE users SET last_active_at = NOW()
                    WHERE user_id = %s
                      AND (last_active_at IS NULL OR last_active_at < NOW() - INTERVAL '5 minutes')
                    """,
                    (user_id,),
                )
    except Exception:
        logger.warning("Could not update user activity", exc_info=True)


def record_request_metric(status_code, latency_ms):
    if _skip_best_effort_writes() or not pg.enabled():
        return
    try:
        with pg.connection() as conn:
            conn.execute(
                """
                INSERT INTO api_metrics_daily (
                    metric_date, request_count, error_count, total_latency_ms, updated_at
                ) VALUES (CURRENT_DATE, 1, %s, %s, NOW())
                ON CONFLICT (metric_date) DO UPDATE
                SET request_count = api_metrics_daily.request_count + 1,
                    error_count = api_metrics_daily.error_count + EXCLUDED.error_count,
                    total_latency_ms = api_metrics_daily.total_latency_ms + EXCLUDED.total_latency_ms,
                    updated_at = NOW()
                """,
                (1 if int(status_code) >= 500 else 0, max(0, int(latency_ms or 0))),
            )
    except Exception:
        logger.warning("Could not update API metrics", exc_info=True)


def record_event(event_type, status, user_id=None, feature=None, provider=None,
                 model=None, latency_ms=0, error_message=None, request_id=None,
                 metadata=None):
    if _skip_best_effort_writes() or not pg.enabled():
        return
    try:
        with pg.connection() as conn:
            conn.execute(
                """
                INSERT INTO operational_events (
                    event_type, user_id, feature, provider, model, status,
                    latency_ms, error_message, request_id, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(event_type)[:80], user_id, str(feature or "")[:120] or None,
                    str(provider or "")[:80] or None, str(model or "")[:160] or None,
                    str(status)[:40], max(0, int(latency_ms or 0)),
                    str(error_message or "")[:500] or None,
                    str(request_id or "")[:100] or None,
                    pg.json_value(metadata or {}),
                ),
            )
    except Exception:
        logger.warning("Could not write operational event", exc_info=True)


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()
