import base64
import hashlib
import hmac
import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from flask import Flask


BACKEND_DIR = Path(__file__).resolve().parents[1] / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models import sepay_payment  # noqa: E402
from routes import payments as payment_routes  # noqa: E402


class _Result:
    def __init__(self, one=None):
        self.one = one

    def fetchone(self):
        return self.one


class _PaymentConnection:
    def __init__(self, payment, active=None, subscription=None):
        self.payment = payment
        self.active = active
        self.subscription = subscription
        self.calls = []

    def execute(self, statement, params=()):
        sql = " ".join(str(statement).split())
        self.calls.append((sql, tuple(params)))
        if sql.startswith("SELECT * FROM payment_transactions"):
            return _Result(self.payment)
        if sql.startswith("SELECT user_id FROM users"):
            return _Result({"user_id": params[0]})
        if sql.startswith("SELECT * FROM subscriptions"):
            return _Result(self.active)
        if sql.startswith("UPDATE subscriptions SET status = 'canceled'"):
            return _Result()
        if sql.startswith("UPDATE subscriptions SET provider = 'sepay'"):
            return _Result(self.subscription)
        if sql.startswith("INSERT INTO subscriptions"):
            return _Result(self.subscription)
        if sql.startswith("UPDATE payment_transactions"):
            return _Result()
        raise AssertionError(f"Unexpected SQL: {sql}")


@contextmanager
def _connection(value):
    yield value


class SepaySignatureTests(unittest.TestCase):
    def test_checkout_signature_uses_documented_field_order(self):
        fields = {
            "merchant": "SP-TEST",
            "order_amount": "49000",
            "currency": "VND",
            "operation": "PURCHASE",
            "order_description": "FlowMate Premium",
            "order_invoice_number": "FM001",
            "customer_id": "alice",
            "payment_method": "BANK_TRANSFER",
            "success_url": "https://flowmate.pro/success",
            "error_url": "https://flowmate.pro/error",
            "cancel_url": "https://flowmate.pro/cancel",
        }
        expected_text = ",".join(
            f"{name}={fields[name]}" for name in sepay_payment.SIGNED_FIELD_ORDER
        )
        expected = base64.b64encode(
            hmac.new(b"secret", expected_text.encode(), hashlib.sha256).digest()
        ).decode()

        self.assertEqual(
            expected,
            sepay_payment.sign_checkout_fields(fields, "secret"),
        )

    def test_prices_are_server_controlled(self):
        self.assertEqual(49_000, sepay_payment.get_plan("premium_monthly")["amount"])
        self.assertEqual(30, sepay_payment.get_plan("premium_monthly")["days"])
        self.assertEqual(520_000, sepay_payment.get_plan("premium_yearly")["amount"])
        self.assertEqual(365, sepay_payment.get_plan("premium_yearly")["days"])

    def test_invalid_payment_method_is_rejected(self):
        with self.assertRaises(sepay_payment.SepayPaymentError) as raised:
            sepay_payment.normalize_payment_method("momo")
        self.assertEqual("invalid_payment_method", raised.exception.code)


class SepayPaymentModelTests(unittest.TestCase):
    def _payload(self, amount="49000"):
        return {
            "timestamp": 1757058220,
            "notification_type": "ORDER_PAID",
            "order": {
                "order_status": "CAPTURED",
                "order_currency": "VND",
                "order_amount": amount,
                "order_invoice_number": "FM001",
            },
            "transaction": {
                "transaction_id": "TX001",
                "transaction_type": "PAYMENT",
                "transaction_status": "APPROVED",
                "transaction_amount": amount,
                "transaction_currency": "VND",
            },
        }

    def test_paid_checkout_creates_subscription_atomically(self):
        end = datetime.now(timezone.utc) + timedelta(days=30)
        connection = _PaymentConnection(
            payment={
                "id": 10,
                "user_id": "alice",
                "status": "pending",
                "currency": "VND",
                "gross_amount": 49_000,
                "subscription_id": None,
                "metadata": {"plan_code": "premium_monthly"},
            },
            subscription={
                "id": 20,
                "user_id": "alice",
                "plan_code": "premium_monthly",
                "current_period_end": end,
            },
        )
        with (
            patch.object(sepay_payment.pg, "enabled", return_value=True),
            patch.object(sepay_payment.pg, "json_value", side_effect=lambda value: value),
            patch.object(sepay_payment.pg, "connection", return_value=_connection(connection)),
        ):
            result = sepay_payment.process_order_paid(self._payload())

        self.assertFalse(result["duplicate"])
        self.assertEqual("purchase", result["subscription"]["entitlement_action"])
        self.assertTrue(any(sql.startswith("INSERT INTO subscriptions") for sql, _ in connection.calls))
        self.assertTrue(any(sql.startswith("UPDATE payment_transactions") for sql, _ in connection.calls))

    def test_paid_checkout_rejects_amount_tampering(self):
        connection = _PaymentConnection(payment={
            "id": 10,
            "user_id": "alice",
            "status": "pending",
            "currency": "VND",
            "gross_amount": 49_000,
            "subscription_id": None,
            "metadata": {"plan_code": "premium_monthly"},
        })
        with (
            patch.object(sepay_payment.pg, "enabled", return_value=True),
            patch.object(sepay_payment.pg, "connection", return_value=_connection(connection)),
            self.assertRaises(sepay_payment.SepayPaymentError) as raised,
        ):
            sepay_payment.process_order_paid(self._payload(amount="1000"))
        self.assertEqual("payment_amount_mismatch", raised.exception.code)

    def test_duplicate_paid_ipn_is_idempotent(self):
        connection = _PaymentConnection(payment={
            "id": 10,
            "user_id": "alice",
            "status": "paid",
            "subscription_id": 20,
        })
        with (
            patch.object(sepay_payment.pg, "enabled", return_value=True),
            patch.object(sepay_payment.pg, "connection", return_value=_connection(connection)),
        ):
            result = sepay_payment.process_order_paid(self._payload())
        self.assertTrue(result["duplicate"])
        self.assertEqual(1, len(connection.calls))


class SepayRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test",
            SEPAY_ENV="sandbox",
            SEPAY_MERCHANT_ID="SP-TEST",
            SEPAY_SECRET_KEY="checkout-secret",
            SEPAY_IPN_SECRET_KEY="ipn-secret",
            SEPAY_CHECKOUT_URL="https://pay-sandbox.sepay.vn/v1/checkout/init",
        )
        self.app.register_blueprint(payment_routes.payments_bp)
        self.client = self.app.test_client()

    def test_checkout_returns_opaque_backend_start_url(self):
        entitlement = {"eligible": True, "allowed_action": "purchase"}
        payment = {
            "checkout_token": "opaque-token",
            "provider_payment_id": "FM001",
        }
        with (
            patch.object(payment_routes, "get_current_user_id", return_value="alice"),
            patch.object(payment_routes.subscription_model, "validate_action", return_value=entitlement),
            patch.object(payment_routes.sepay_payment, "create_checkout", return_value=payment) as create,
        ):
            response = self.client.post(
                "/api/payments/sepay/checkout",
                json={
                    "action": "purchase",
                    "plan_code": "premium_monthly",
                    "payment_method": "BANK_TRANSFER",
                },
            )

        self.assertEqual(201, response.status_code)
        body = response.get_json()
        self.assertTrue(body["checkout_url"].endswith("/api/payments/sepay/start/opaque-token"))
        self.assertNotIn("checkout-secret", response.get_data(as_text=True))
        create.assert_called_once_with("alice", "premium_monthly", "purchase", "BANK_TRANSFER")

    def test_checkout_fails_before_insert_when_ipn_secret_is_missing(self):
        self.app.config["SEPAY_IPN_SECRET_KEY"] = ""
        with (
            patch.object(payment_routes, "get_current_user_id", return_value="alice"),
            patch.object(payment_routes.sepay_payment, "create_checkout") as create,
        ):
            response = self.client.post(
                "/api/payments/sepay/checkout",
                json={"action": "purchase", "plan_code": "premium_monthly"},
            )
        self.assertEqual(503, response.status_code)
        self.assertEqual("sepay_not_configured", response.get_json()["error"])
        create.assert_not_called()

    def test_start_page_posts_signed_fields_to_sepay(self):
        payment = {
            "status": "pending",
            "provider_payment_id": "FM001",
            "gross_amount": 49_000,
            "currency": "VND",
            "user_id": "alice",
            "metadata": {"plan_name": "Premium", "payment_method": "BANK_TRANSFER"},
        }
        with patch.object(payment_routes.sepay_payment, "get_checkout_by_token", return_value=payment):
            response = self.client.get("/api/payments/sepay/start/opaque-token")

        text = response.get_data(as_text=True)
        self.assertEqual(200, response.status_code)
        self.assertIn('method="post"', text)
        self.assertIn("https://pay-sandbox.sepay.vn/v1/checkout/init", text)
        self.assertIn('name="signature"', text)
        self.assertNotIn("checkout-secret", text)

    def test_ipn_requires_matching_secret_header(self):
        response = self.client.post(
            "/api/payments/sepay/ipn",
            headers={"X-Secret-Key": "wrong"},
            json={"notification_type": "ORDER_PAID"},
        )
        self.assertEqual(401, response.status_code)
        self.assertEqual("invalid_ipn_secret", response.get_json()["error"])

    def test_ipn_accepts_sepay_authorization_apikey_header(self):
        # SePay's actual "API Key" webhook auth (confirmed against its
        # dashboard: Khong xac thuc / API Key / HMAC-SHA256 / OAuth 2.0 --
        # there is no separate "secret key" scheme) sends the key via
        # `Authorization: Apikey <key>`, not a custom header.
        result = {"duplicate": False, "user_id": "alice", "subscription_id": 7}
        with (
            patch.object(payment_routes.sepay_payment, "process_order_paid", return_value=result),
            patch.object(payment_routes.WorkspaceSync, "bump") as bump,
        ):
            response = self.client.post(
                "/api/payments/sepay/ipn",
                headers={"Authorization": "Apikey ipn-secret"},
                json={"timestamp": 1757058220, "notification_type": "ORDER_PAID"},
            )
        self.assertEqual(200, response.status_code)
        bump.assert_called_once_with("alice", ("profile", "settings", "overview"))

    def test_ipn_rejects_wrong_apikey_in_authorization_header(self):
        response = self.client.post(
            "/api/payments/sepay/ipn",
            headers={"Authorization": "Apikey wrong"},
            json={"notification_type": "ORDER_PAID"},
        )
        self.assertEqual(401, response.status_code)
        self.assertEqual("invalid_ipn_secret", response.get_json()["error"])

    def test_paid_ipn_is_processed_and_profile_sync_is_bumped(self):
        result = {"duplicate": False, "user_id": "alice", "subscription_id": 7}
        with (
            patch.object(payment_routes.sepay_payment, "process_order_paid", return_value=result) as process,
            patch.object(payment_routes.WorkspaceSync, "bump") as bump,
        ):
            response = self.client.post(
                "/api/payments/sepay/ipn",
                headers={"X-Secret-Key": "ipn-secret"},
                json={"timestamp": 1757058220, "notification_type": "ORDER_PAID"},
            )

        self.assertEqual(200, response.status_code)
        process.assert_called_once()
        bump.assert_called_once_with("alice", ("profile", "settings", "overview"))

    def test_duplicate_ipn_does_not_bump_sync_again(self):
        result = {"duplicate": True, "user_id": "alice", "subscription_id": 7}
        with (
            patch.object(payment_routes.sepay_payment, "process_order_paid", return_value=result),
            patch.object(payment_routes.WorkspaceSync, "bump") as bump,
        ):
            response = self.client.post(
                "/api/payments/sepay/ipn",
                headers={"X-Secret-Key": "ipn-secret"},
                json={"timestamp": 1757058220, "notification_type": "ORDER_PAID"},
            )
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["duplicate"])
        bump.assert_not_called()

    def test_ipn_requires_timestamp(self):
        response = self.client.post(
            "/api/payments/sepay/ipn",
            headers={"X-Secret-Key": "ipn-secret"},
            json={"notification_type": "ORDER_PAID"},
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual("invalid_ipn_timestamp", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
