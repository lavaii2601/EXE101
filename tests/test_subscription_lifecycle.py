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

from models import notification as notification_model  # noqa: E402
from models import subscription as subscription_model  # noqa: E402
from models import workspace_subscription as workspace_subscription_model  # noqa: E402
from routes import notifications as notifications_route  # noqa: E402
from services import subscription_lifecycle_scheduler as scheduler  # noqa: E402


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
    """Replays pre-scripted results in call order, asserting each SQL prefix."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def commit(self):
        pass

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
def _patched_pg(module, connection):
    with (
        patch.object(module.pg, "enabled", return_value=True),
        patch.object(module.pg, "connection", side_effect=lambda: _connection(connection)),
    ):
        yield


class NotificationModelTests(unittest.TestCase):
    def test_create_uses_on_conflict_do_nothing_for_idempotency(self):
        connection = _ScriptedConnection([("INSERT INTO notifications", _Result())])
        with _patched_pg(notification_model, connection):
            notification_model.create(
                recipient_user_id="alice",
                dedupe_key="sub_reminder:1:2026-09-10",
                type_="subscription_renewal_reminder",
                title="Test",
            )
        sql, params = connection.calls[0]
        self.assertIn("ON CONFLICT (recipient_user_id, dedupe_key) DO NOTHING", sql)
        self.assertEqual("alice", params[0])
        self.assertEqual("sub_reminder:1:2026-09-10", params[7])

    def test_create_falls_back_to_info_severity_when_invalid(self):
        connection = _ScriptedConnection([("INSERT INTO notifications", _Result())])
        with _patched_pg(notification_model, connection):
            notification_model.create(
                recipient_user_id="alice", dedupe_key="k", type_="t", title="T",
                severity="not_a_real_severity",
            )
        _, params = connection.calls[0]
        self.assertEqual("info", params[3])

    def test_list_for_user_orders_unread_first(self):
        connection = _ScriptedConnection([("SELECT * FROM notifications", _Result(many=[]))])
        with _patched_pg(notification_model, connection):
            notification_model.list_for_user("alice")
        sql, params = connection.calls[0]
        self.assertIn("ORDER BY (read_at IS NULL) DESC, created_at DESC", sql)
        self.assertEqual(("alice", 50), params)

    def test_mark_read_is_scoped_to_recipient(self):
        connection = _ScriptedConnection([
            ("UPDATE notifications SET read_at", _Result(one={"id": "n1"})),
        ])
        with _patched_pg(notification_model, connection):
            updated = notification_model.mark_read("alice", "n1")
        self.assertTrue(updated)
        sql, params = connection.calls[0]
        self.assertIn("WHERE id = %s AND recipient_user_id = %s", sql)
        self.assertEqual(("n1", "alice"), params)

    def test_mark_read_returns_false_when_not_found_or_not_owned(self):
        connection = _ScriptedConnection([
            ("UPDATE notifications SET read_at", _Result(one=None)),
        ])
        with _patched_pg(notification_model, connection):
            updated = notification_model.mark_read("mallory", "someone-elses-notification")
        self.assertFalse(updated)

    def test_noop_without_postgres(self):
        with patch.object(notification_model.pg, "enabled", return_value=False):
            notification_model.create(recipient_user_id="a", dedupe_key="k", type_="t", title="T")
            self.assertEqual([], notification_model.list_for_user("a"))
            self.assertEqual(0, notification_model.count_unread("a"))
            self.assertFalse(notification_model.mark_read("a", "n1"))


class SubscriptionLifecycleQueryTests(unittest.TestCase):
    def test_personal_list_lapsed_filters_active_statuses_past_period_end(self):
        connection = _ScriptedConnection([("SELECT * FROM subscriptions", _Result(many=[]))])
        with _patched_pg(subscription_model, connection):
            subscription_model.list_lapsed()
        sql, params = connection.calls[0]
        self.assertIn("current_period_end < NOW()", sql)
        self.assertEqual((list(subscription_model.ACTIVE_STATUSES), 500), params)

    def test_personal_mark_expired_only_touches_active_statuses(self):
        connection = _ScriptedConnection([("UPDATE subscriptions SET status = 'expired'", _Result(rowcount=2))])
        with _patched_pg(subscription_model, connection):
            updated = subscription_model.mark_expired(["s1", "s2"])
        self.assertEqual(2, updated)
        sql, params = connection.calls[0]
        self.assertEqual((["s1", "s2"], list(subscription_model.ACTIVE_STATUSES)), params)

    def test_personal_mark_expired_noop_for_empty_ids(self):
        with patch.object(subscription_model.pg, "enabled", return_value=True):
            self.assertEqual(0, subscription_model.mark_expired([]))

    def test_workspace_list_all_with_owner_joins_workspaces(self):
        connection = _ScriptedConnection([("SELECT s.*, w.owner_user_id", _Result(many=[]))])
        with _patched_pg(workspace_subscription_model, connection):
            workspace_subscription_model.list_all_with_owner()
        sql, _ = connection.calls[0]
        self.assertIn("JOIN workspaces w ON w.id = s.workspace_id", sql)
        self.assertIn("status NOT IN ('expired', 'canceled')", sql)

    def test_workspace_mark_expired_excludes_terminal_statuses(self):
        connection = _ScriptedConnection([("UPDATE subscriptions SET status = 'expired'", _Result(rowcount=1))])
        with _patched_pg(workspace_subscription_model, connection):
            updated = workspace_subscription_model.mark_expired(["w1"])
        self.assertEqual(1, updated)
        sql, params = connection.calls[0]
        self.assertIn("status NOT IN ('expired', 'canceled', 'suspended')", sql)
        self.assertEqual((["w1"],), params)

    def test_workspace_mark_expired_never_touches_an_admin_suspended_row(self):
        # Regression test for a real bug the code-review skill caught:
        # get_access_state() treats status='suspended' as an unconditional
        # ACCESS_READ_ONLY regardless of current_period_end (an admin's
        # explicit revoke()). If mark_expired() were allowed to flip that
        # row to 'expired', the next get_access_state() call would fall
        # through to the ordinary period_end comparison and could come back
        # ACCESS_ACTIVE -- silently restoring access the admin revoked.
        # Exercised here against the REAL get_access_state, not a mock, so
        # a future change to either function's logic can't silently
        # reintroduce the gap.
        suspended_row = {
            "status": "suspended",
            "current_period_end": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }
        self.assertEqual(
            workspace_subscription_model.ACCESS_READ_ONLY,
            workspace_subscription_model.get_access_state(suspended_row),
        )

        connection = _ScriptedConnection([("UPDATE subscriptions SET status = 'expired'", _Result(rowcount=0))])
        with _patched_pg(workspace_subscription_model, connection):
            updated = workspace_subscription_model.mark_expired(["suspended-1"])
        self.assertEqual(0, updated)
        sql, _ = connection.calls[0]
        self.assertIn("'suspended'", sql)


class LifecycleSchedulerOrchestrationTests(unittest.TestCase):
    """Pure decision-logic tests -- model-layer calls are mocked so these
    focus on what the scheduler decides to do with each subscription state,
    not on SQL correctness (covered above)."""

    def test_personal_expiring_soon_creates_a_dated_dedupe_key(self):
        row = {"id": 42, "user_id": "alice", "plan_code": "premium_monthly",
               "plan_name": "FlowMate Premium", "current_period_end": "2026-09-10T00:00:00+00:00"}
        with (
            patch.object(subscription_model, "list_expiring_soon", return_value=[row]),
            patch.object(notification_model, "create") as create,
        ):
            scheduler._remind_personal_expiring_soon()
        create.assert_called_once()
        kwargs = create.call_args.kwargs
        self.assertEqual("alice", kwargs["recipient_user_id"])
        self.assertEqual("sub_reminder:42:2026-09-10", kwargs["dedupe_key"])

    def test_running_the_reminder_pass_twice_uses_the_same_dedupe_key(self):
        # True double-insert prevention is the DB constraint (tested above);
        # this confirms the scheduler's own contribution -- it must derive
        # the identical key both times, or the constraint has nothing to
        # catch.
        row = {"id": 42, "user_id": "alice", "plan_code": "premium_monthly",
               "current_period_end": "2026-09-10T00:00:00+00:00"}
        with (
            patch.object(subscription_model, "list_expiring_soon", return_value=[row]),
            patch.object(notification_model, "create") as create,
        ):
            scheduler._remind_personal_expiring_soon()
            scheduler._remind_personal_expiring_soon()
        first_key = create.call_args_list[0].kwargs["dedupe_key"]
        second_key = create.call_args_list[1].kwargs["dedupe_key"]
        self.assertEqual(first_key, second_key)

    def test_workspace_in_grace_notifies_owner_and_does_not_expire(self):
        row = {
            "id": 7, "workspace_id": "ws-1", "workspace_owner_user_id": "owner-1",
            "access_state": workspace_subscription_model.ACCESS_GRACE,
            "current_period_end": "2026-09-01T00:00:00+00:00",
        }
        with (
            patch.object(workspace_subscription_model, "list_all_with_owner", return_value=[row]),
            patch.object(notification_model, "create") as create,
            patch.object(workspace_subscription_model, "mark_expired") as mark_expired,
        ):
            scheduler._process_workspace_subscriptions()
        create.assert_called_once()
        kwargs = create.call_args.kwargs
        self.assertEqual("owner-1", kwargs["recipient_user_id"])
        self.assertEqual("workspace_subscription_grace", kwargs["type_"])
        self.assertEqual("warning", kwargs["severity"])
        mark_expired.assert_not_called()

    def test_workspace_read_only_notifies_owner_and_marks_expired(self):
        row = {
            "id": 8, "workspace_id": "ws-2", "workspace_owner_user_id": "owner-2",
            "access_state": workspace_subscription_model.ACCESS_READ_ONLY,
            "current_period_end": "2026-08-01T00:00:00+00:00",
        }
        with (
            patch.object(workspace_subscription_model, "list_all_with_owner", return_value=[row]),
            patch.object(notification_model, "create") as create,
            patch.object(workspace_subscription_model, "mark_expired") as mark_expired,
        ):
            scheduler._process_workspace_subscriptions()
        create.assert_called_once()
        kwargs = create.call_args.kwargs
        self.assertEqual("workspace_subscription_read_only", kwargs["type_"])
        self.assertEqual("critical", kwargs["severity"])
        mark_expired.assert_called_once_with([8])

    def test_workspace_active_far_from_expiry_notifies_nobody(self):
        far_future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        row = {
            "id": 9, "workspace_id": "ws-3", "workspace_owner_user_id": "owner-3",
            "access_state": workspace_subscription_model.ACCESS_ACTIVE,
            "current_period_end": far_future,
        }
        with (
            patch.object(workspace_subscription_model, "list_all_with_owner", return_value=[row]),
            patch.object(notification_model, "create") as create,
            patch.object(workspace_subscription_model, "mark_expired") as mark_expired,
        ):
            scheduler._process_workspace_subscriptions()
        create.assert_not_called()
        mark_expired.assert_not_called()

    def test_workspace_active_within_reminder_window_notifies_owner(self):
        soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        row = {
            "id": 10, "workspace_id": "ws-4", "workspace_owner_user_id": "owner-4",
            "access_state": workspace_subscription_model.ACCESS_ACTIVE,
            "current_period_end": soon,
        }
        with (
            patch.object(workspace_subscription_model, "list_all_with_owner", return_value=[row]),
            patch.object(notification_model, "create") as create,
        ):
            scheduler._process_workspace_subscriptions()
        create.assert_called_once()
        self.assertEqual(
            "workspace_subscription_renewal_reminder",
            create.call_args.kwargs["type_"],
        )

    def test_row_missing_workspace_owner_is_skipped_without_error(self):
        row = {
            "id": 11, "workspace_id": "ws-5", "workspace_owner_user_id": None,
            "access_state": workspace_subscription_model.ACCESS_READ_ONLY,
            "current_period_end": "2026-08-01T00:00:00+00:00",
        }
        with (
            patch.object(workspace_subscription_model, "list_all_with_owner", return_value=[row]),
            patch.object(notification_model, "create") as create,
            patch.object(workspace_subscription_model, "mark_expired") as mark_expired,
        ):
            scheduler._process_workspace_subscriptions()
        create.assert_not_called()
        mark_expired.assert_not_called()

    def test_run_lifecycle_pass_calls_all_three_stages(self):
        with (
            patch.object(scheduler, "_expire_lapsed_personal") as expire_personal,
            patch.object(scheduler, "_remind_personal_expiring_soon") as remind_personal,
            patch.object(scheduler, "_process_workspace_subscriptions") as process_workspace,
        ):
            scheduler.run_lifecycle_pass()
        expire_personal.assert_called_once()
        remind_personal.assert_called_once()
        process_workspace.assert_called_once()


class NotificationsRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(TESTING=True, SECRET_KEY="test")
        cls.app.register_blueprint(notifications_route.notifications_bp)

    def test_list_requires_authentication(self):
        with patch.object(notifications_route, "get_current_user_id", return_value=""):
            response = self.app.test_client().get("/api/notifications")
        self.assertEqual(401, response.status_code)

    def test_list_returns_only_the_caller_s_notifications(self):
        with (
            patch.object(notifications_route, "get_current_user_id", return_value="alice"),
            patch.object(notification_model, "list_for_user", return_value=[{"id": "n1"}]) as list_for_user,
            patch.object(notification_model, "count_unread", return_value=1),
        ):
            response = self.app.test_client().get("/api/notifications")
        self.assertEqual(200, response.status_code)
        list_for_user.assert_called_once_with("alice", limit=30, unread_only=False)
        self.assertEqual(1, response.get_json()["unread_count"])

    def test_mark_read_returns_404_for_someone_elses_notification(self):
        with (
            patch.object(notifications_route, "get_current_user_id", return_value="mallory"),
            patch.object(notification_model, "mark_read", return_value=False),
        ):
            response = self.app.test_client().post("/api/notifications/not-mine/read")
        self.assertEqual(404, response.status_code)

    def test_mark_read_success(self):
        with (
            patch.object(notifications_route, "get_current_user_id", return_value="alice"),
            patch.object(notification_model, "mark_read", return_value=True) as mark_read,
            patch.object(notification_model, "count_unread", return_value=0),
        ):
            response = self.app.test_client().post("/api/notifications/n1/read")
        self.assertEqual(200, response.status_code)
        mark_read.assert_called_once_with("alice", "n1")


if __name__ == "__main__":
    unittest.main()
