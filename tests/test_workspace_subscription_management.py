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

from models import workspace_subscription as wsub  # noqa: E402
from routes import workspace as workspace_route  # noqa: E402


class _Result:
    def __init__(self, one=None, many=None, rowcount=0):
        self._one = one
        self._many = many or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class _ScriptedConnection:
    """Replays pre-scripted results in call order, asserting each SQL prefix.

    Mirrors test_workspace_management.py's fake connection."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def execute(self, statement, params=()):
        sql = " ".join(str(statement).split())
        self.calls.append((sql, tuple(params)))
        if not self.script:
            raise AssertionError(f"No more scripted results, got: {sql}")
        expected_prefix, result = self.script.pop(0)
        if expected_prefix and not sql.startswith(expected_prefix):
            raise AssertionError(f"Expected SQL starting with {expected_prefix!r}, got: {sql}")
        return result


@contextmanager
def _connection(connection):
    yield connection


@contextmanager
def _patched_pg(connection):
    with (
        patch.object(wsub.pg, "enabled", return_value=True),
        patch.object(wsub.pg, "connection", side_effect=lambda: _connection(connection)),
        patch.object(wsub.pg, "json_value", side_effect=lambda v: v),
    ):
        yield


class WorkspaceSubscriptionSchemaTests(unittest.TestCase):
    def test_postgres_schema_extends_subscriptions_for_workspaces(self):
        schema = (REPO_ROOT / "database" / "postgres_schema.sql").read_text(encoding="utf-8")
        self.assertIn("workspace_id UUID", schema)
        self.assertIn("subscriptions_subject_check", schema)
        self.assertIn("included_seats INTEGER NOT NULL DEFAULT 0", schema)
        self.assertIn("extra_seats INTEGER NOT NULL DEFAULT 0", schema)
        self.assertIn("grace_period_ends_at TIMESTAMPTZ", schema)
        self.assertIn("'suspended'", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_seat_requests", schema)
        self.assertIn(
            "status IN ('pending_owner', 'payment_pending', 'approved', 'rejected', 'expired')",
            schema,
        )

    def test_migration_file_exists_and_is_idempotent_style(self):
        migration = (
            REPO_ROOT / "database" / "migrations" / "20260829_workspace_subscriptions.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN IF NOT EXISTS workspace_id", migration)
        self.assertIn("ADD COLUMN IF NOT EXISTS included_seats", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_seat_requests", migration)
        self.assertIn("DROP CONSTRAINT IF EXISTS subscriptions_status_check", migration)


class AccessStateTests(unittest.TestCase):
    """Pure-function tests for get_access_state -- no DB involved, matching
    section 6.7's requirement that this must be correct from just the row's
    own fields, independent of any background job having run."""

    def test_no_subscription_is_none(self):
        self.assertEqual(wsub.ACCESS_NONE, wsub.get_access_state(None))

    def test_suspended_is_always_read_only(self):
        row = {
            "status": "suspended",
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
        }
        self.assertEqual(wsub.ACCESS_READ_ONLY, wsub.get_access_state(row))

    def test_revoke_suspends_access_immediately(self):
        connection = _ScriptedConnection([
            ('UPDATE subscriptions SET status = \'suspended\'', _Result(rowcount=1)),
            ('INSERT INTO workspace_audit_events', _Result()),
        ])
        with _patched_pg(connection):
            revoked = wsub.revoke('ws-1', actor_user_id='admin-1')

        self.assertTrue(revoked)
        self.assertIn("status = 'suspended'", connection.calls[0][0])
        self.assertEqual(('ws-1',), connection.calls[0][1])

    def test_within_period_is_active(self):
        row = {"status": "active", "current_period_end": datetime.now(timezone.utc) + timedelta(days=5)}
        self.assertEqual(wsub.ACCESS_ACTIVE, wsub.get_access_state(row))

    def test_no_period_end_is_active(self):
        row = {"status": "active", "current_period_end": None}
        self.assertEqual(wsub.ACCESS_ACTIVE, wsub.get_access_state(row))

    def test_lapsed_within_grace_window_is_grace(self):
        row = {
            "status": "past_due",
            "current_period_end": datetime.now(timezone.utc) - timedelta(days=2),
            "grace_period_ends_at": None,
        }
        # No explicit grace_period_ends_at -- falls back to period_end + 7 days.
        self.assertEqual(wsub.ACCESS_GRACE, wsub.get_access_state(row))

    def test_lapsed_past_grace_window_is_read_only(self):
        row = {
            "status": "past_due",
            "current_period_end": datetime.now(timezone.utc) - timedelta(days=10),
            "grace_period_ends_at": None,
        }
        self.assertEqual(wsub.ACCESS_READ_ONLY, wsub.get_access_state(row))

    def test_canceled_still_follows_period_end_not_immediately_read_only(self):
        row = {
            "status": "canceled",
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=3),
        }
        self.assertEqual(wsub.ACCESS_ACTIVE, wsub.get_access_state(row))

    def test_explicit_grace_period_ends_at_takes_priority(self):
        row = {
            "status": "past_due",
            "current_period_end": datetime.now(timezone.utc) - timedelta(days=1),
            "grace_period_ends_at": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        self.assertEqual(wsub.ACCESS_READ_ONLY, wsub.get_access_state(row))


class SeatCapacityTests(unittest.TestCase):
    def test_check_seat_capacity_locked_reports_room_with_default_capacity(self):
        connection = _ScriptedConnection([
            ("SELECT id FROM workspaces WHERE id", _Result(one={"id": "ws-1"})),
            ("SELECT included_seats, extra_seats FROM subscriptions", _Result(one=None)),
            ("SELECT COUNT(*) AS n FROM workspace_memberships", _Result(one={"n": 3})),
        ])
        active, capacity, has_room = wsub.check_seat_capacity_locked(connection, "ws-1")
        self.assertEqual(3, active)
        self.assertEqual(wsub.DEFAULT_BUSINESS_INCLUDED_SEATS, capacity)
        self.assertTrue(has_room)

    def test_check_seat_capacity_locked_reports_full_at_subscription_capacity(self):
        connection = _ScriptedConnection([
            ("SELECT id FROM workspaces WHERE id", _Result(one={"id": "ws-1"})),
            ("SELECT included_seats, extra_seats FROM subscriptions",
             _Result(one={"included_seats": 10, "extra_seats": 2})),
            ("SELECT COUNT(*) AS n FROM workspace_memberships", _Result(one={"n": 12})),
        ])
        active, capacity, has_room = wsub.check_seat_capacity_locked(connection, "ws-1")
        self.assertEqual(12, capacity)
        self.assertFalse(has_room)

    def test_ensure_seat_request_is_idempotent_for_same_invitation(self):
        existing = {"id": "req-1", "invitation_id": "inv-1", "status": "pending_owner"}
        connection = _ScriptedConnection([
            ("SELECT * FROM workspace_seat_requests", _Result(one=existing)),
        ])
        result = wsub.ensure_seat_request(connection, "ws-1", "inv-1", "bob")
        self.assertEqual("req-1", result["id"])
        # No INSERT issued -- only the existence check ran.
        self.assertEqual(1, len(connection.calls))


class GrantManualTests(unittest.TestCase):
    def test_purchase_when_no_active_subscription(self):
        created_row = {
            "id": 1, "workspace_id": "ws-1", "status": "active",
            "included_seats": 10, "extra_seats": 0,
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
        }
        connection = _ScriptedConnection([
            ("SELECT id FROM workspaces WHERE id", _Result(one={"id": "ws-1"})),
            ("SELECT * FROM subscriptions", _Result(one=None)),
            ("INSERT INTO subscriptions", _Result(one=created_row)),
            ("INSERT INTO workspace_audit_events", _Result(rowcount=1)),
        ])
        with _patched_pg(connection):
            result = wsub.grant_manual("ws-1", "business_monthly", actor_user_id="admin-1")

        self.assertEqual("purchase", result["entitlement_action"])
        self.assertEqual(wsub.ACCESS_ACTIVE, result["access_state"])

    def test_renew_rejected_when_requested_action_mismatches_state(self):
        active_row = {
            "id": 1, "workspace_id": "ws-1", "status": "active",
            "included_seats": 10, "extra_seats": 0,
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
        }
        connection = _ScriptedConnection([
            ("SELECT id FROM workspaces WHERE id", _Result(one={"id": "ws-1"})),
            ("SELECT * FROM subscriptions", _Result(one=active_row)),
        ])
        with _patched_pg(connection):
            with self.assertRaises(wsub.WorkspaceSubscriptionError) as raised:
                wsub.grant_manual("ws-1", "business_monthly", action="purchase")

        self.assertEqual("subscription_already_active", raised.exception.code)
        self.assertEqual("renew", raised.exception.extra["allowed_action"])


class ApproveRejectSeatRequestTests(unittest.TestCase):
    def test_approve_seat_request_increments_extra_seats_and_reopens_invitation(self):
        request_row = {
            "id": "req-1", "workspace_id": "ws-1", "invitation_id": "inv-1",
            "requested_seats": 2, "status": "pending_owner",
        }
        subscription_row = {"id": 5, "workspace_id": "ws-1", "included_seats": 10, "extra_seats": 0}
        approved_row = {**request_row, "status": "approved", "approved_by_user_id": "owner-1"}
        connection = _ScriptedConnection([
            ("SELECT * FROM workspace_seat_requests WHERE id", _Result(one=request_row)),
            ("SELECT * FROM subscriptions", _Result(one=subscription_row)),
            ("UPDATE subscriptions SET extra_seats", _Result(rowcount=1)),
            ("UPDATE workspace_seat_requests", _Result(one=approved_row)),
            ("UPDATE workspace_invitations SET status = 'pending'", _Result(rowcount=1)),
            ("INSERT INTO workspace_audit_events", _Result(rowcount=1)),
        ])
        with _patched_pg(connection):
            result = wsub.approve_seat_request("req-1", "owner-1")

        self.assertEqual("approved", result["status"])
        extra_seats_call = connection.calls[2]
        self.assertEqual((2, 5), extra_seats_call[1])

    def test_approve_seat_request_rejects_already_resolved(self):
        request_row = {"id": "req-1", "workspace_id": "ws-1", "status": "rejected"}
        connection = _ScriptedConnection([
            ("SELECT * FROM workspace_seat_requests WHERE id", _Result(one=request_row)),
        ])
        with _patched_pg(connection):
            with self.assertRaises(wsub.WorkspaceSubscriptionError) as raised:
                wsub.approve_seat_request("req-1", "owner-1")

        self.assertEqual("seat_request_not_pending", raised.exception.code)


class WorkspaceSubscriptionRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="workspace-subscription-test")
        self.app.register_blueprint(workspace_route.workspace_bp)
        self.client = self.app.test_client()

    def test_get_subscription_rejects_non_member(self):
        with (
            patch.object(workspace_route, "get_current_user_id", return_value="mallory"),
            patch.object(workspace_route.workspace_model, "get_membership", return_value=None),
        ):
            response = self.client.get("/api/workspaces/ws-1/subscription")

        self.assertEqual(403, response.status_code)
        self.assertEqual("membership_required", response.get_json()["error"])

    def test_worker_cannot_approve_seat_request(self):
        worker_membership = {"role": "worker", "status": "active"}
        with (
            patch.object(workspace_route, "get_current_user_id", return_value="bob"),
            patch.object(workspace_route.workspace_model, "get_membership", return_value=worker_membership),
        ):
            response = self.client.post("/api/workspaces/ws-1/seat-requests/req-1/approve")

        self.assertEqual(403, response.status_code)
        self.assertEqual("insufficient_role", response.get_json()["error"])

    def test_owner_can_approve_seat_request(self):
        owner_membership = {"role": "owner", "status": "active"}
        approved = {"id": "req-1", "status": "approved"}
        with (
            patch.object(workspace_route, "get_current_user_id", return_value="alice"),
            patch.object(workspace_route.workspace_model, "get_membership", return_value=owner_membership),
            patch.object(workspace_route.workspace_subscription, "approve_seat_request", return_value=approved) as approve,
        ):
            response = self.client.post("/api/workspaces/ws-1/seat-requests/req-1/approve")

        self.assertEqual(200, response.status_code)
        self.assertEqual("approved", response.get_json()["seat_request"]["status"])
        approve.assert_called_once_with("req-1", "alice", added_seats=None)

    def test_member_can_view_subscription_and_access_state(self):
        member_membership = {"role": "worker", "status": "active"}
        subscription = {
            "id": 1, "workspace_id": "ws-1", "status": "active",
            "access_state": "active", "seat_capacity": 10,
        }
        with (
            patch.object(workspace_route, "get_current_user_id", return_value="bob"),
            patch.object(workspace_route.workspace_model, "get_membership", return_value=member_membership),
            patch.object(workspace_route.workspace_subscription, "get_current", return_value=subscription),
            patch.object(workspace_route.workspace_subscription, "get_access_state", return_value="active"),
            patch.object(workspace_route.workspace_subscription, "count_active_seats", return_value=4),
        ):
            response = self.client.get("/api/workspaces/ws-1/subscription")

        body = response.get_json()
        self.assertEqual(200, response.status_code)
        self.assertEqual("active", body["access_state"])
        self.assertEqual(10, body["seat_capacity"])
        self.assertEqual(4, body["active_seats"])


if __name__ == "__main__":
    unittest.main()
