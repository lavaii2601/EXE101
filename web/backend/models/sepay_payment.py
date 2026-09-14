"""SEPay checkout persistence and idempotent Premium activation.

The payment gateway secret never leaves the backend. Pending checkouts reuse
the provider-neutral ``payment_transactions`` table, while a confirmed IPN
creates or extends the existing personal Premium entitlement atomically.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from models import postgres_db as pg
from models.subscription import ACTIVE_STATUSES, _decorate


PLANS = {
    "premium_monthly": {
        "plan_code": "premium_monthly",
        "plan_name": "FlowMate Premium tháng",
        "billing_interval": "monthly",
        "amount": 49_000,
        "days": 30,
    },
    "premium_yearly": {
        "plan_code": "premium_yearly",
        "plan_name": "FlowMate Premium năm",
        "billing_interval": "yearly",
        "amount": 520_000,
        "days": 365,
    },
}

PAYMENT_METHODS = frozenset({"BANK_TRANSFER", "CARD", "NAPAS_BANK_TRANSFER"})
SIGNED_FIELD_ORDER = (
    "order_amount",
    "merchant",
    "currency",
    "operation",
    "order_description",
    "order_invoice_number",
    "customer_id",
    "payment_method",
    "success_url",
    "error_url",
    "cancel_url",
)


class SepayPaymentError(RuntimeError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def get_plan(plan_code):
    plan = PLANS.get(str(plan_code or "").strip().lower())
    if not plan:
        raise SepayPaymentError("invalid_plan")
    return dict(plan)


def normalize_payment_method(value):
    method = str(value or "BANK_TRANSFER").strip().upper()
    if method not in PAYMENT_METHODS:
        raise SepayPaymentError("invalid_payment_method")
    return method


def sign_checkout_fields(fields, secret_key):
    """Return SEPay's Base64 HMAC-SHA256 signature in documented order."""
    if not secret_key:
        raise SepayPaymentError("sepay_not_configured", status=503)
    signing_text = ",".join(
        f"{name}={fields[name]}"
        for name in SIGNED_FIELD_ORDER
        if fields.get(name) not in (None, "")
    )
    digest = hmac.new(
        secret_key.encode("utf-8"),
        signing_text.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def create_checkout(user_id, plan_code, action, payment_method):
    if not pg.enabled():
        raise SepayPaymentError("payments_require_postgres", status=503)
    plan = get_plan(plan_code)
    method = normalize_payment_method(payment_method)
    requested_action = str(action or "").strip().lower()
    if requested_action not in {"purchase", "renew"}:
        raise SepayPaymentError("invalid_subscription_action")

    pg.ensure_user(user_id)
    invoice = (
        "FM"
        + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
        + secrets.token_hex(5).upper()
    )
    checkout_token = secrets.token_urlsafe(32)
    metadata = {
        **plan,
        "requested_action": requested_action,
        "payment_method": method,
        "checkout_token": checkout_token,
    }
    with pg.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO payment_transactions (
                user_id, provider, provider_payment_id, status, currency,
                gross_amount, description, metadata
            )
            VALUES (%s, 'sepay', %s, 'pending', 'VND', %s, %s, %s)
            RETURNING *
            """,
            (
                user_id,
                invoice,
                plan["amount"],
                plan["plan_name"],
                pg.json_value(metadata),
            ),
        ).fetchone()
    result = pg.normalize_row(row)
    result["checkout_token"] = checkout_token
    return result


def get_checkout_by_token(token):
    if not pg.enabled() or not token:
        return None
    with pg.connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM payment_transactions
            WHERE provider = 'sepay'
              AND metadata ->> 'checkout_token' = %s
            LIMIT 1
            """,
            (token,),
        ).fetchone()
    return pg.normalize_row(row)


def get_payment_status(invoice, user_id=None):
    if not pg.enabled() or not invoice:
        return None
    params = [invoice]
    user_clause = ""
    if user_id:
        user_clause = " AND user_id = %s"
        params.append(user_id)
    with pg.connection() as conn:
        row = conn.execute(
            f"""
            SELECT provider_payment_id, status, currency, gross_amount,
                   paid_at, created_at
            FROM payment_transactions
            WHERE provider = 'sepay' AND provider_payment_id = %s
            {user_clause}
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
    return pg.normalize_row(row)


def checkout_fields(payment, merchant_id, secret_key, callback_urls):
    metadata = payment.get("metadata") or {}
    fields = {
        "order_amount": str(payment["gross_amount"]),
        "merchant": merchant_id,
        "currency": payment["currency"],
        "operation": "PURCHASE",
        "order_description": f"{metadata.get('plan_name', 'FlowMate Premium')} - {payment['provider_payment_id']}",
        "order_invoice_number": payment["provider_payment_id"],
        "customer_id": payment["user_id"],
        "payment_method": metadata.get("payment_method", "BANK_TRANSFER"),
        "success_url": callback_urls["success"],
        "error_url": callback_urls["error"],
        "cancel_url": callback_urls["cancel"],
    }
    if not merchant_id:
        raise SepayPaymentError("sepay_not_configured", status=503)
    fields["signature"] = sign_checkout_fields(fields, secret_key)
    return fields


def _as_vnd_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise SepayPaymentError("invalid_payment_amount")
    if amount < 0 or amount != amount.to_integral_value():
        raise SepayPaymentError("invalid_payment_amount")
    return int(amount)


def process_order_paid(payload):
    """Validate an ORDER_PAID IPN and grant exactly one entitlement."""
    if not pg.enabled():
        raise SepayPaymentError("payments_require_postgres", status=503)
    order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
    transaction = (
        payload.get("transaction")
        if isinstance(payload.get("transaction"), dict)
        else {}
    )
    invoice = str(order.get("order_invoice_number") or "").strip()
    if not invoice:
        raise SepayPaymentError("missing_invoice")
    if str(order.get("order_status") or "").upper() != "CAPTURED":
        raise SepayPaymentError("order_not_captured")
    if str(transaction.get("transaction_status") or "").upper() != "APPROVED":
        raise SepayPaymentError("transaction_not_approved")
    if str(transaction.get("transaction_type") or "").upper() != "PAYMENT":
        raise SepayPaymentError("invalid_transaction_type")

    with pg.connection() as conn:
        payment = conn.execute(
            """
            SELECT * FROM payment_transactions
            WHERE provider = 'sepay' AND provider_payment_id = %s
            LIMIT 1 FOR UPDATE
            """,
            (invoice,),
        ).fetchone()
        if not payment:
            raise SepayPaymentError("payment_not_found", status=404)
        if payment["status"] == "paid":
            return {
                "duplicate": True,
                "user_id": payment["user_id"],
                "subscription_id": payment.get("subscription_id"),
            }
        if payment["status"] != "pending":
            raise SepayPaymentError("payment_not_pending", status=409)

        expected_amount = int(payment["gross_amount"])
        order_amount = _as_vnd_amount(order.get("order_amount"))
        transaction_amount = _as_vnd_amount(transaction.get("transaction_amount"))
        if order_amount != expected_amount or transaction_amount != expected_amount:
            raise SepayPaymentError("payment_amount_mismatch")
        order_currency = str(order.get("order_currency") or "").upper()
        transaction_currency = str(transaction.get("transaction_currency") or "").upper()
        if order_currency != payment["currency"] or transaction_currency != payment["currency"]:
            raise SepayPaymentError("payment_currency_mismatch")

        user_id = payment["user_id"]
        metadata = payment.get("metadata") or {}
        plan = get_plan(metadata.get("plan_code"))
        conn.execute("SELECT user_id FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
        active = conn.execute(
            """
            SELECT * FROM subscriptions
            WHERE user_id = %s
              AND status = ANY(%s)
              AND (current_period_end IS NULL OR current_period_end > NOW())
            ORDER BY current_period_end DESC NULLS LAST
            LIMIT 1 FOR UPDATE
            """,
            (user_id, list(ACTIVE_STATUSES)),
        ).fetchone()

        entitlement_action = "renew" if active else "purchase"
        subscription_metadata = pg.json_value({
            "last_sepay_invoice": invoice,
            "last_sepay_transaction_id": str(transaction.get("transaction_id") or ""),
        })
        if active:
            conn.execute(
                """
                UPDATE subscriptions
                SET status = 'canceled', canceled_at = COALESCE(canceled_at, NOW())
                WHERE user_id = %s AND status = ANY(%s) AND id <> %s
                """,
                (user_id, list(ACTIVE_STATUSES), active["id"]),
            )
            subscription = conn.execute(
                """
                UPDATE subscriptions
                SET provider = 'sepay', provider_subscription_id = %s,
                    plan_code = %s, plan_name = %s, status = 'active',
                    billing_interval = %s, currency = 'VND', unit_amount = %s,
                    current_period_end =
                        GREATEST(COALESCE(current_period_end, NOW()), NOW())
                        + (%s || ' days')::INTERVAL,
                    cancel_at_period_end = FALSE, canceled_at = NULL,
                    metadata = metadata || %s
                WHERE id = %s AND user_id = %s
                RETURNING *
                """,
                (
                    invoice,
                    plan["plan_code"],
                    plan["plan_name"],
                    plan["billing_interval"],
                    plan["amount"],
                    plan["days"],
                    subscription_metadata,
                    active["id"],
                    user_id,
                ),
            ).fetchone()
        else:
            subscription = conn.execute(
                """
                INSERT INTO subscriptions (
                    user_id, provider, provider_subscription_id, plan_code,
                    plan_name, status, billing_interval, currency, unit_amount,
                    current_period_start, current_period_end, metadata
                )
                VALUES (
                    %s, 'sepay', %s, %s, %s, 'active', %s, 'VND', %s,
                    NOW(), NOW() + (%s || ' days')::INTERVAL, %s
                )
                RETURNING *
                """,
                (
                    user_id,
                    invoice,
                    plan["plan_code"],
                    plan["plan_name"],
                    plan["billing_interval"],
                    plan["amount"],
                    plan["days"],
                    subscription_metadata,
                ),
            ).fetchone()

        payment_metadata = pg.json_value({
            "confirmed_action": entitlement_action,
            "sepay_transaction_id": str(transaction.get("transaction_id") or ""),
            "sepay_notification_type": "ORDER_PAID",
        })
        conn.execute(
            """
            UPDATE payment_transactions
            SET subscription_id = %s, status = 'paid', paid_at = NOW(),
                metadata = metadata || %s
            WHERE id = %s
            """,
            (subscription["id"], payment_metadata, payment["id"]),
        )

    result = _decorate(subscription)
    result["entitlement_action"] = entitlement_action
    return {
        "duplicate": False,
        "user_id": user_id,
        "subscription_id": subscription["id"],
        "subscription": result,
    }


def process_transaction_void(payload):
    order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
    invoice = str(order.get("order_invoice_number") or "").strip()
    if not invoice:
        raise SepayPaymentError("missing_invoice")
    if not pg.enabled():
        raise SepayPaymentError("payments_require_postgres", status=503)
    with pg.connection() as conn:
        row = conn.execute(
            """
            UPDATE payment_transactions
            SET status = 'failed', metadata = metadata || %s
            WHERE provider = 'sepay' AND provider_payment_id = %s
              AND status = 'pending'
            RETURNING user_id
            """,
            (pg.json_value({"sepay_notification_type": "TRANSACTION_VOID"}), invoice),
        ).fetchone()
    return {"user_id": row["user_id"] if row else None}
