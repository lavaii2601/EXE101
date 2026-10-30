import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, session


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models import admin_ops
from utils import quota, security


class AdminControlsTests(unittest.TestCase):
    def test_default_controls_cover_both_plans_and_budget_thresholds(self):
        controls = admin_ops.validate_controls({})

        self.assertIn("bob_chat", controls["quotas"]["free"])
        self.assertIn("claude", controls["quotas"]["plus"])
        self.assertLessEqual(
            controls["budgets"]["critical_usd"],
            controls["budgets"]["hard_limit_usd"],
        )

    def test_invalid_budget_threshold_order_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_budget_threshold_order"):
            admin_ops.validate_controls({
                "budgets": {"warning_usd": 19, "critical_usd": 10},
            })

    def test_quota_gate_applies_runtime_plus_limit(self):
        with (
            patch.object(quota, "is_premium", return_value=True),
            patch.object(quota.admin_ops, "quota_limit", return_value=50) as limit,
            patch.object(quota, "check_and_increment", return_value=(True, 1, 50)) as increment,
        ):
            result = quota.enforce_ai_quota("user-1", "claude")

        self.assertEqual(
            {"allowed": True, "used": 1, "limit": 50, "remaining": 49}, result,
        )
        limit.assert_called_once_with("plus", "claude")
        increment.assert_called_once_with("user-1", "claude", limit=50)

    def test_budget_state_fails_closed_when_cost_read_fails(self):
        # A real incident: this read silently failed for 9+ days (same root
        # cause that stopped ai_cost_log inserts entirely) while the old code
        # treated the failure as "$0 spent this month", so hard_stop_enabled
        # never actually blocked anything no matter how much was really
        # being spent. It must now refuse to allow instead of guessing $0.
        with (
            patch.object(admin_ops.pg, "enabled", return_value=True),
            patch.object(admin_ops.pg, "connection", side_effect=RuntimeError("pool exhausted")),
        ):
            state = admin_ops.current_budget_state("openai")

        self.assertFalse(state["allowed"])
        self.assertTrue(state["query_failed"])

    def test_budget_state_allows_when_cost_read_succeeds_and_under_limit(self):
        class _FakeConn:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc_info):
                return False

            def execute(self_inner, *args, **kwargs):
                class _Row:
                    def fetchone(self_row):
                        return {"total": 1.0, "provider_total": 0.5}

                return _Row()

        with (
            patch.object(admin_ops.pg, "enabled", return_value=True),
            patch.object(admin_ops.pg, "connection", return_value=_FakeConn()),
            patch.object(admin_ops.pg, "normalize_row", side_effect=lambda row: row),
        ):
            state = admin_ops.current_budget_state("openai")

        self.assertTrue(state["allowed"])
        self.assertFalse(state["query_failed"])


class AccountLifecycleSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "test-only"

    def test_local_user_id_takes_precedence_over_linked_gmail_identity(self):
        with self.app.test_request_context("/"):
            session["user_id"] = "local-user-id"
            session["gmail_user_email"] = "linked@example.com"
            self.assertEqual("local-user-id", security.authenticated_user_id())

    def test_suspended_account_is_not_an_active_identity(self):
        with self.app.test_request_context("/"):
            session["user_id"] = "suspended-user"
            with patch("models.user.User.get", return_value={
                "user_id": "suspended-user",
                "account_status": "suspended",
            }):
                self.assertIsNone(security.active_authenticated_user_id())


class AdminOperationsContractTests(unittest.TestCase):
    def test_migration_has_required_operations_tables(self):
        migration = (
            PROJECT_ROOT / "database" / "migrations" /
            "20261004_admin_operations.sql"
        ).read_text(encoding="utf-8")
        for table in (
            "admin_settings", "admin_audit_events", "operational_events",
            "api_metrics_daily",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", migration)
        self.assertIn("account_status", migration)

    def test_frontend_exposes_all_operations_sections_and_api_routes(self):
        html = (PROJECT_ROOT / "web" / "frontend" / "admin.html").read_text(
            encoding="utf-8"
        )
        javascript = (
            PROJECT_ROOT / "web" / "frontend" / "js" / "admin.js"
        ).read_text(encoding="utf-8")

        for tab in (
            "overview", "users", "finance", "ai", "controls",
            "integrations", "health", "security",
        ):
            self.assertIn(f'data-dashboard-tab="{tab}"', html)
            self.assertIn(f'data-dashboard-panel="{tab}"', html)
        for endpoint in (
            "/api/admin/users", "/api/admin/ai-usage",
            "/api/admin/ai-controls", "/api/admin/integrations",
            "/api/admin/system-health", "/api/admin/security",
        ):
            self.assertIn(endpoint, javascript)


if __name__ == "__main__":
    unittest.main()
