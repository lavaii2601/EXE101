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

from models import postgres_db as pg

ACTIVE_STATUSES = ("trialing", "active")


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
        return pg.normalize_row(row)


def is_premium(user_id):
    return get_active(user_id) is not None


def grant_manual(user_id, plan_code, plan_name=None, billing_interval="monthly",
                  unit_amount=0, currency="VND", days=30):
    """Admin-granted premium: insert an active 'manual' subscription that
    expires in `days` days. No payment_transactions row -- that ledger is
    reserved for real money movement, and none happened here."""
    if not pg.enabled():
        raise RuntimeError("Subscriptions require Postgres (DATABASE_URL)")
    pg.ensure_user(user_id)
    with pg.connection() as conn:
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
            (user_id, plan_code, plan_name, billing_interval, currency, unit_amount, days),
        ).fetchone()
        return pg.normalize_row(row)


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
