"""Freemium/Premium subscription lookups and admin-granted upgrades.

Reads/writes the provider-neutral `subscriptions` table already defined in
database/postgres_schema.sql (added for the admin finance dashboard, but
previously nothing wrote to it). `provider` stays 'manual' for admin-granted
premium until a real payment processor (Google Play Billing / RevenueCat) is
wired up -- at that point a webhook would insert rows the same shape as
`grant_manual` produces here, so gating code never has to change.

Postgres-only: subscriptions are a Railway/production concern, no SQLite
parity needed (matches routes/admin.py, which is Postgres-only already).
"""

import math
from datetime import datetime, timezone

from models import postgres_db as pg

ACTIVE_STATUSES = ("trialing", "active")
PURCHASE_ACTIONS = ("purchase", "renew")


class SubscriptionStateError(RuntimeError):
    """Raised when purchase/renew does not match the current entitlement."""

    def __init__(self, code, allowed_action, subscription=None):
        super().__init__(code)
        self.code = code
        self.allowed_action = allowed_action
        self.subscription = subscription


def _remaining_seconds(period_end):
    if not period_end:
        return None
    if isinstance(period_end, str):
        try:
            period_end = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
        except ValueError:
            return 0
    if period_end.tzinfo is None:
        period_end = period_end.replace(tzinfo=timezone.utc)
    return max(0, int((period_end - datetime.now(timezone.utc)).total_seconds()))


def _decorate(row):
    normalized = pg.normalize_row(row)
    if not normalized:
        return None
    seconds = _remaining_seconds(normalized.get("current_period_end"))
    normalized["remaining_seconds"] = seconds
    normalized["remaining_days"] = (
        math.ceil(seconds / 86400)
        if seconds is not None
        else None
    )
    return normalized


def get_active(user_id):
    """Return the current active/trialing subscription row for user_id, or None."""
    if not user_id or not pg.enabled():
        return None
    with pg.connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM subscriptions
            WHERE user_id = %s
              AND status = ANY(%s)
              AND (current_period_end IS NULL OR current_period_end > NOW())
            ORDER BY current_period_end DESC NULLS LAST
            LIMIT 1
            """,
            (user_id, list(ACTIVE_STATUSES)),
        ).fetchone()
        return _decorate(row)


def is_premium(user_id):
    return get_active(user_id) is not None


def get_entitlement(user_id):
    """Return the purchase/renew state shared by web, APK and payment flows."""
    active = get_active(user_id)
    return {
        "tier": "premium" if active else "free",
        "is_premium": bool(active),
        "can_purchase": not active,
        "can_renew": bool(active),
        "allowed_action": "renew" if active else "purchase",
        "plan_code": active.get("plan_code") if active else None,
        "plan_name": active.get("plan_name") if active else None,
        "billing_interval": active.get("billing_interval") if active else None,
        "current_period_start": active.get("current_period_start") if active else None,
        "current_period_end": active.get("current_period_end") if active else None,
        "remaining_seconds": active.get("remaining_seconds") if active else 0,
        "remaining_days": active.get("remaining_days") if active else 0,
    }


def validate_action(user_id, requested_action):
    requested_action = str(requested_action or "").strip().lower()
    if requested_action not in PURCHASE_ACTIONS:
        raise ValueError("invalid_subscription_action")
    entitlement = get_entitlement(user_id)
    allowed_action = entitlement["allowed_action"]
    return {
        **entitlement,
        "requested_action": requested_action,
        "eligible": requested_action == allowed_action,
    }


def grant_manual(user_id, plan_code, plan_name=None, billing_interval="monthly",
                  unit_amount=0, currency="VND", days=30, action=None):
    """Purchase or renew an admin-managed Premium entitlement atomically.

    A user with active Premium cannot create another purchase row; the only
    valid operation is renewal, which extends the existing period from its
    current end. No payment transaction is created because no gateway-confirmed
    money movement happened here.
    """
    if not pg.enabled():
        raise RuntimeError("Subscriptions require Postgres (DATABASE_URL)")
    requested_action = str(action or "").strip().lower() or None
    if requested_action and requested_action not in PURCHASE_ACTIONS:
        raise ValueError("invalid_subscription_action")

    pg.ensure_user(user_id)
    with pg.connection() as conn:
        # The user row is the per-account transaction lock. It serializes two
        # payment/admin requests that arrive before either creates a row.
        conn.execute(
            "SELECT user_id FROM users WHERE user_id = %s FOR UPDATE",
            (user_id,),
        )
        active = conn.execute(
            """
            SELECT *
            FROM subscriptions
            WHERE user_id = %s
              AND status = ANY(%s)
              AND (current_period_end IS NULL OR current_period_end > NOW())
            ORDER BY current_period_end DESC NULLS LAST
            LIMIT 1
            FOR UPDATE
            """,
            (user_id, list(ACTIVE_STATUSES)),
        ).fetchone()

        allowed_action = "renew" if active else "purchase"
        if requested_action and requested_action != allowed_action:
            code = (
                "premium_already_active"
                if allowed_action == "renew"
                else "no_active_premium"
            )
            raise SubscriptionStateError(
                code,
                allowed_action,
                subscription=_decorate(active),
            )

        if active:
            # Old manual grants could leave more than one active row. Keep the
            # newest entitlement canonical and close the others before renewal.
            conn.execute(
                """
                UPDATE subscriptions
                SET status = 'canceled',
                    canceled_at = COALESCE(canceled_at, NOW()),
                    cancel_at_period_end = FALSE
                WHERE user_id = %s
                  AND status = ANY(%s)
                  AND id <> %s
                """,
                (user_id, list(ACTIVE_STATUSES), active["id"]),
            )
            row = conn.execute(
                """
                UPDATE subscriptions
                SET provider = 'manual',
                    plan_code = %s,
                    plan_name = %s,
                    status = 'active',
                    billing_interval = %s,
                    currency = %s,
                    unit_amount = %s,
                    current_period_end =
                        GREATEST(COALESCE(current_period_end, NOW()), NOW())
                        + (%s || ' days')::INTERVAL,
                    cancel_at_period_end = FALSE,
                    canceled_at = NULL
                WHERE id = %s AND user_id = %s
                RETURNING *
                """,
                (
                    plan_code,
                    plan_name,
                    billing_interval,
                    currency,
                    unit_amount,
                    days,
                    active["id"],
                    user_id,
                ),
            ).fetchone()
            result = _decorate(row)
            result["entitlement_action"] = "renew"
            return result

        row = conn.execute(
            """
            INSERT INTO subscriptions (
                user_id, provider, plan_code, plan_name, status,
                billing_interval, currency, unit_amount,
                current_period_start, current_period_end
            )
            VALUES (
                %s, 'manual', %s, %s, 'active',
                %s, %s, %s,
                NOW(), NOW() + (%s || ' days')::INTERVAL
            )
            RETURNING *
            """,
            (
                user_id,
                plan_code,
                plan_name,
                billing_interval,
                currency,
                unit_amount,
                days,
            ),
        ).fetchone()
        result = _decorate(row)
        result["entitlement_action"] = "purchase"
        return result


def revoke(user_id):
    """Cancel the user's current active/trialing subscription, if any."""
    if not pg.enabled():
        return False
    with pg.connection() as conn:
        cur = conn.execute(
            """
            UPDATE subscriptions
            SET status = 'canceled', canceled_at = NOW()
            WHERE user_id = %s AND status = ANY(%s)
            """,
            (user_id, list(ACTIVE_STATUSES)),
        )
        return cur.rowcount > 0
