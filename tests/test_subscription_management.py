import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from flask import Flask


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models import subscription  # noqa: E402
from routes import admin as admin_route  # noqa: E402
from routes import user as user_route  # noqa: E402


class _Result:
    def __init__(self, one=None, rowcount=0):
        self._one = one
        self.rowcount = rowcount

    def fetchone(self):
        return self._one


class _SubscriptionConnection:
    def __init__(self, active=None, purchased=None, renewed=None):
        self.active = active
        self.purchased = purchased
        self.renewed = renewed
        self.calls = []

    def execute(self, statement, params=()):
        sql = " ".join(str(statement).split())
        self.calls.append((sql, tuple(params)))
        if sql.startswith("SELECT user_id FROM users"):
            return _Result(one={"user_id": params[0]})
        if sql.startswith("SELECT * FROM subscriptions") and "FOR UPDATE" in sql:
            return _Result(one=self.active)
        if sql.startswith("INSERT INTO subscriptions"):
            return _Result(one=self.purchased)
        if sql.startswith("UPDATE subscriptions SET provider = 'manual'"):
            return _Result(one=self.renewed)
        if sql.startswith("UPDATE subscriptions SET status = 'canceled'"):
            return _Result(rowcount=1)
        raise AssertionError(f"Unexpected SQL: {sql}")


@contextmanager
def _connection(connection):
    yield connection


class SubscriptionModelTests(unittest.TestCase):
    def test_postgres_schema_accepts_premium_chat_retention(self):
        schema = (REPO_ROOT / "database" / "postgres_schema.sql").read_text(
            encoding="utf-8"
        )
        migration = (
            REPO_ROOT
            / "database"
            / "migrations"
            / "20260726_chat_retention_premium.sql"
        ).read_text(encoding="utf-8")

        self.assertNotIn("retention_days BETWEEN 30 AND 93", schema)
        self.assertIn("retention_days BETWEEN 30 AND 365", schema)
        self.assertIn(
            "DROP CONSTRAINT IF EXISTS chat_sessions_retention_days_check",
            migration,
        )
        self.assertIn("retention_days BETWEEN 30 AND 365", migration)

    def _grant(self, connection, **kwargs):
        with (
            patch.object(subscription.pg, "enabled", return_value=True),
            patch.object(subscription.pg, "ensure_user"),
            patch.object(
                subscription.pg,
                "connection",
                side_effect=lambda: _connection(connection),
            ),
        ):
            return subscription.grant_manual(
                "alice",
                "premium_monthly",
                plan_name="Premium",
                billing_interval="monthly",
                unit_amount=49000,
                days=30,
                **kwargs,
            )

    def test_free_account_purchase_creates_one_active_subscription(self):
        end = datetime.now(timezone.utc) + timedelta(days=30)
        connection = _SubscriptionConnection(
            purchased={
                "id": 1,
                "user_id": "alice",
                "plan_code": "premium_monthly",
                "plan_name": "Premium",
                "billing_interval": "monthly",
                "current_period_end": end,
            }
        )

        result = self._grant(connection, action="purchase")

        self.assertEqual("purchase", result["entitlement_action"])
        self.assertGreater(result["remaining_seconds"], 0)
        self.assertEqual(
            1,
            sum(sql.startswith("INSERT INTO subscriptions") for sql, _ in connection.calls),
        )

    def test_active_account_cannot_purchase_a_second_plan(self):
        active = {
            "id": 7,
            "user_id": "alice",
            "plan_code": "premium_monthly",
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=10),
        }
        connection = _SubscriptionConnection(active=active)

        with self.assertRaises(subscription.SubscriptionStateError) as raised:
            self._grant(connection, action="purchase")

        self.assertEqual("premium_already_active", raised.exception.code)
        self.assertEqual("renew", raised.exception.allowed_action)
        self.assertFalse(any(
            sql.startswith("INSERT INTO subscriptions")
            for sql, _ in connection.calls
        ))

    def test_free_account_cannot_use_renewal_action(self):
        connection = _SubscriptionConnection(active=None)

        with self.assertRaises(subscription.SubscriptionStateError) as raised:
            self._grant(connection, action="renew")

        self.assertEqual("no_active_premium", raised.exception.code)
        self.assertEqual("purchase", raised.exception.allowed_action)
        self.assertFalse(any(
            sql.startswith("INSERT INTO subscriptions")
            for sql, _ in connection.calls
        ))

    def test_renewal_extends_the_existing_entitlement(self):
        active_end = datetime.now(timezone.utc) + timedelta(days=10)
        renewed_end = active_end + timedelta(days=30)
        active = {
            "id": 7,
            "user_id": "alice",
            "plan_code": "premium_monthly",
            "current_period_end": active_end,
        }
        connection = _SubscriptionConnection(
            active=active,
            renewed={
                **active,
                "plan_name": "Premium",
                "billing_interval": "monthly",
                "current_period_end": renewed_end,
            },
        )

        result = self._grant(connection, action="renew")

        self.assertEqual("renew", result["entitlement_action"])
        renewal_sql = next(
            sql for sql, _ in connection.calls
            if sql.startswith("UPDATE subscriptions SET provider = 'manual'")
        )
        self.assertIn(
            "GREATEST(COALESCE(current_period_end, NOW()), NOW())",
            renewal_sql,
        )
        self.assertFalse(any(
            sql.startswith("INSERT INTO subscriptions")
            for sql, _ in connection.calls
        ))

    def test_entitlement_exposes_remaining_time_and_allowed_action(self):
        active = {
            "plan_code": "premium_monthly",
            "plan_name": "Premium",
            "billing_interval": "monthly",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=4),
        }
        with patch.object(subscription, "get_active", return_value=subscription._decorate(active)):
            state = subscription.get_entitlement("alice")

        self.assertEqual("premium", state["tier"])
        self.assertFalse(state["can_purchase"])
        self.assertTrue(state["can_renew"])
        self.assertEqual("renew", state["allowed_action"])
        self.assertGreater(state["remaining_seconds"], 0)


class SubscriptionRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="subscription-test")
        self.app.register_blueprint(user_route.user_bp)
        self.app.register_blueprint(admin_route.admin_bp)
        self.client = self.app.test_client()

    def test_user_purchase_intent_is_rejected_when_premium_is_active(self):
        state = {
            "tier": "premium",
            "is_premium": True,
            "allowed_action": "renew",
            "eligible": False,
            "remaining_seconds": 3600,
        }
        with (
            patch.object(user_route, "get_current_user_id", return_value="alice"),
            patch.object(
                user_route.subscription_model,
                "validate_action",
                return_value=state,
            ),
        ):
            response = self.client.post(
                "/api/user/subscription/intent",
                json={"action": "purchase"},
            )

        self.assertEqual(409, response.status_code)
        self.assertEqual("premium_already_active", response.get_json()["error"])
        self.assertEqual("renew", response.get_json()["allowed_action"])

    def test_user_renewal_intent_is_rejected_after_premium_expires(self):
        state = {
            "tier": "free",
            "is_premium": False,
            "allowed_action": "purchase",
            "eligible": False,
            "remaining_seconds": 0,
        }
        with (
            patch.object(user_route, "get_current_user_id", return_value="alice"),
            patch.object(
                user_route.subscription_model,
                "validate_action",
                return_value=state,
            ),
        ):
            response = self.client.post(
                "/api/user/subscription/intent",
                json={"action": "renew"},
            )

        self.assertEqual(409, response.status_code)
        self.assertEqual("no_active_premium", response.get_json()["error"])
        self.assertEqual("purchase", response.get_json()["allowed_action"])

    def test_admin_can_renew_and_revoke_with_target_profile_sync(self):
        renewed = {
            "id": 9,
            "entitlement_action": "renew",
            "remaining_seconds": 86400,
            "current_period_end": "2026-08-24T00:00:00+00:00",
        }
        with (
            patch.object(
                admin_route,
                "_require_admin",
                return_value=("admin@example.com", None),
            ),
            patch.object(admin_route.pg, "enabled", return_value=True),
            patch.object(
                admin_route.subscription_model,
                "grant_manual",
                return_value=renewed,
            ) as grant,
            patch.object(admin_route.WorkspaceSync, "bump") as bump,
        ):
            response = self.client.post(
                "/api/admin/users/alice/subscription",
                json={
                    "action": "renew",
                    "billing_interval": "monthly",
                    "days": 30,
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("renew", response.get_json()["action"])
        self.assertEqual("renew", grant.call_args.kwargs["action"])
        bump.assert_called_once_with(
            "alice",
            ("profile", "settings", "overview"),
        )

        with (
            patch.object(
                admin_route,
                "_require_admin",
                return_value=("admin@example.com", None),
            ),
            patch.object(admin_route.pg, "enabled", return_value=True),
            patch.object(
                admin_route.subscription_model,
                "revoke",
                return_value=True,
            ),
            patch.object(admin_route.WorkspaceSync, "bump") as revoke_bump,
        ):
            revoked = self.client.post(
                "/api/admin/users/alice/subscription/revoke",
                json={},
            )

        self.assertEqual(200, revoked.status_code)
        self.assertTrue(revoked.get_json()["revoked"])
        revoke_bump.assert_called_once_with(
            "alice",
            ("profile", "settings", "overview"),
        )


if __name__ == "__main__":
    unittest.main()
