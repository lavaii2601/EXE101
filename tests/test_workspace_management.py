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

from models import workspace as workspace_module  # noqa: E402
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

    Mirrors the fake-connection approach in test_subscription_management.py,
    extended to sequences: workspace model functions issue several queries
    per call (lock -> validate -> mutate -> audit), so a single
    prefix-to-result dict isn't enough -- order matters here.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.commits = 0

    def commit(self):
        # Real code explicitly commits mid-transaction before raising an
        # error for a mutation that must survive it (see accept_invitation's
        # invitation_expired/capacity_blocked branches) -- track calls so
        # tests can assert that actually happened, without needing a real
        # transaction to verify it.
        self.commits += 1

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
    """Patches workspace_module.pg so model code runs against one scripted
    connection instead of real Postgres. ensure_user is stubbed out (like
    test_subscription_management.py's _grant helper does) since it opens its
    own pg.connection() internally and isn't what these tests are about.
    json_value is stubbed to pass metadata through unwrapped -- its real
    implementation needs psycopg's Jsonb() adapter, which isn't installed in
    this dev environment (only the deployed backend's env has it), and these
    tests don't care about the exact wire format, just that a value flows
    through."""
    with (
        patch.object(workspace_module.pg, "enabled", return_value=True),
        patch.object(workspace_module.pg, "ensure_user"),
        patch.object(workspace_module.pg, "connection", side_effect=lambda: _connection(connection)),
        patch.object(workspace_module.pg, "json_value", side_effect=lambda v: v),
    ):
        yield


class WorkspaceSchemaTests(unittest.TestCase):
    def test_postgres_schema_defines_workspace_tables(self):
        schema = (REPO_ROOT / "database" / "postgres_schema.sql").read_text(encoding="utf-8")
        for table in (
            "CREATE TABLE IF NOT EXISTS workspaces",
            "CREATE TABLE IF NOT EXISTS workspace_memberships",
            "CREATE TABLE IF NOT EXISTS workspace_invitations",
            "CREATE TABLE IF NOT EXISTS workspace_audit_events",
        ):
            self.assertIn(table, schema)
        # One personal workspace per owner is enforced by a partial unique
        # index, not a CHECK constraint (Postgres can't express that in a
        # CHECK) -- assert the index exists so this invariant isn't silently
        # dropped in a future schema edit.
        self.assertIn("idx_workspaces_one_personal_per_owner", schema)
        self.assertIn("workspace_memberships_unique UNIQUE (workspace_id, user_id)", schema)
        self.assertIn("CHECK (role IN ('owner', 'admin', 'worker'))", schema)


class WorkspaceModelTests(unittest.TestCase):
    def test_ensure_personal_workspace_creates_when_none_exists(self):
        workspace_row = {
            "id": "ws-1", "type": "personal", "name": "Personal",
            "owner_user_id": "alice", "status": "active",
        }
        connection = _ScriptedConnection([
            ("INSERT INTO workspaces", _Result(one=workspace_row)),
            ("INSERT INTO workspace_memberships", _Result(rowcount=1)),
        ])
        with _patched_pg(connection):
            result = workspace_module.ensure_personal_workspace("alice")

        self.assertEqual("ws-1", result["id"])
        self.assertEqual(2, len(connection.calls))

    def test_ensure_personal_workspace_is_idempotent(self):
        existing_row = {
            "id": "ws-1", "type": "personal", "name": "Personal",
            "owner_user_id": "alice", "status": "active",
        }
        connection = _ScriptedConnection([
            ("INSERT INTO workspaces", _Result(one=None)),  # ON CONFLICT DO NOTHING -> no row
            ("SELECT * FROM workspaces", _Result(one=existing_row)),
        ])
        with _patched_pg(connection):
            result = workspace_module.ensure_personal_workspace("alice")

        self.assertEqual("ws-1", result["id"])
        # No membership INSERT on the already-exists branch -- the owner
        # membership was created the first time this workspace was made.
        self.assertFalse(any(
            sql.startswith("INSERT INTO workspace_memberships") for sql, _ in connection.calls
        ))

    def test_create_business_workspace_creates_owner_membership_and_audit_event(self):
        workspace_row = {
            "id": "ws-2", "type": "business", "name": "Acme Inc",
            "owner_user_id": "alice", "status": "active",
        }
        connection = _ScriptedConnection([
            ("INSERT INTO workspaces", _Result(one=workspace_row)),
            ("INSERT INTO workspace_memberships", _Result(rowcount=1)),
            ("INSERT INTO workspace_audit_events", _Result(rowcount=1)),
        ])
        with _patched_pg(connection):
            result = workspace_module.create_business_workspace("alice", "Acme Inc")

        self.assertEqual("business", result["type"])
        membership_call = connection.calls[1]
        self.assertIn("'owner'", membership_call[0])

    def test_create_business_workspace_rejects_blank_name(self):
        with self.assertRaises(workspace_module.WorkspaceError) as raised:
            with patch.object(workspace_module.pg, "enabled", return_value=True):
                workspace_module.create_business_workspace("alice", "   ")
        self.assertEqual("workspace_name_required", raised.exception.code)

    def test_accept_invitation_succeeds_when_email_matches(self):
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        invitation_row = {
            "id": "inv-1", "workspace_id": "ws-2", "role": "worker",
            "status": "pending", "email_normalized": "bob@example.com",
            "expires_at": expires,
        }
        accepted_row = {**invitation_row, "status": "accepted"}
        connection = _ScriptedConnection([
            ("SELECT * FROM workspace_invitations WHERE token_hash", _Result(one=invitation_row)),
            # Personal workspace -> accept_invitation skips the Business
            # seat-capacity check (models/workspace_subscription.py) entirely.
            ("SELECT type FROM workspaces WHERE id", _Result(one={"type": "personal"})),
            ("INSERT INTO workspace_memberships", _Result(rowcount=1)),
            ("UPDATE workspace_invitations", _Result(one=accepted_row)),
            ("INSERT INTO workspace_audit_events", _Result(rowcount=1)),
        ])
        with _patched_pg(connection):
            result = workspace_module.accept_invitation("raw-token", "bob", "bob@example.com")

        self.assertEqual("accepted", result["status"])

    def test_accept_invitation_blocks_when_business_workspace_at_capacity(self):
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        invitation_row = {
            "id": "inv-1", "workspace_id": "ws-biz", "role": "worker",
            "status": "pending", "email_normalized": "bob@example.com",
            "expires_at": expires,
        }
        connection = _ScriptedConnection([
            ("SELECT * FROM workspace_invitations WHERE token_hash", _Result(one=invitation_row)),
            ("SELECT type FROM workspaces WHERE id", _Result(one={"type": "business"})),
            ("SELECT id FROM workspaces WHERE id", _Result(one={"id": "ws-biz"})),
            ("SELECT included_seats, extra_seats FROM subscriptions",
             _Result(one={"included_seats": 10, "extra_seats": 0})),
            ("SELECT COUNT(*) AS n FROM workspace_memberships", _Result(one={"n": 10})),
            ("UPDATE workspace_invitations SET status = 'capacity_blocked'", _Result(rowcount=1)),
            ("SELECT * FROM workspace_seat_requests", _Result(one=None)),
            ("INSERT INTO workspace_seat_requests",
             _Result(one={"id": "req-1", "workspace_id": "ws-biz", "invitation_id": "inv-1", "status": "pending_owner"})),
            ("INSERT INTO workspace_audit_events", _Result(rowcount=1)),
        ])
        with _patched_pg(connection):
            with self.assertRaises(workspace_module.WorkspaceError) as raised:
                workspace_module.accept_invitation("raw-token", "bob", "bob@example.com")

        self.assertEqual("capacity_blocked", raised.exception.code)
        # pg.connection() rolls back the whole transaction when an exception
        # escapes it (see models/postgres_db.py) -- without an explicit
        # commit here, the capacity_blocked status and seat request above
        # would silently vanish even though this test's scripted SQL ran.
        self.assertEqual(1, connection.commits)

    def test_accept_invitation_rejects_email_mismatch(self):
        invitation_row = {
            "id": "inv-1", "workspace_id": "ws-2", "role": "worker",
            "status": "pending", "email_normalized": "bob@example.com",
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        }
        connection = _ScriptedConnection([
            ("SELECT * FROM workspace_invitations WHERE token_hash", _Result(one=invitation_row)),
        ])
        with _patched_pg(connection):
            with self.assertRaises(workspace_module.WorkspaceError) as raised:
                workspace_module.accept_invitation("raw-token", "eve", "eve@example.com")

        self.assertEqual("invitation_email_mismatch", raised.exception.code)

    def test_accept_invitation_rejects_expired(self):
        invitation_row = {
            "id": "inv-1", "workspace_id": "ws-2", "role": "worker",
            "status": "pending", "email_normalized": "bob@example.com",
            "expires_at": datetime.now(timezone.utc) - timedelta(days=1),
        }
        connection = _ScriptedConnection([
            ("SELECT * FROM workspace_invitations WHERE token_hash", _Result(one=invitation_row)),
            ("UPDATE workspace_invitations SET status = 'expired'", _Result(rowcount=1)),
        ])
        with _patched_pg(connection):
            with self.assertRaises(workspace_module.WorkspaceError) as raised:
                workspace_module.accept_invitation("raw-token", "bob", "bob@example.com")

        self.assertEqual("invitation_expired", raised.exception.code)
        self.assertEqual(1, connection.commits)

    def test_accept_invitation_rejects_already_accepted(self):
        invitation_row = {
            "id": "inv-1", "workspace_id": "ws-2", "role": "worker",
            "status": "accepted", "email_normalized": "bob@example.com",
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        }
        connection = _ScriptedConnection([
            ("SELECT * FROM workspace_invitations WHERE token_hash", _Result(one=invitation_row)),
        ])
        with _patched_pg(connection):
            with self.assertRaises(workspace_module.WorkspaceError) as raised:
                workspace_module.accept_invitation("raw-token", "bob", "bob@example.com")

        self.assertEqual("invitation_not_pending", raised.exception.code)

    def test_update_member_role_rejects_changing_owner(self):
        owner_membership = {
            "id": "mem-1", "workspace_id": "ws-2", "user_id": "alice",
            "role": "owner", "status": "active",
        }
        connection = _ScriptedConnection([
            ("SELECT * FROM workspace_memberships", _Result(one=owner_membership)),
        ])
        with _patched_pg(connection):
            with self.assertRaises(workspace_module.WorkspaceError) as raised:
                workspace_module.update_member_role("ws-2", "alice", "admin", "someone")

        self.assertEqual("cannot_change_owner_role", raised.exception.code)

    def test_disable_member_rejects_disabling_owner(self):
        owner_membership = {
            "id": "mem-1", "workspace_id": "ws-2", "user_id": "alice",
            "role": "owner", "status": "active",
        }
        connection = _ScriptedConnection([
            ("SELECT * FROM workspace_memberships", _Result(one=owner_membership)),
        ])
        with _patched_pg(connection):
            with self.assertRaises(workspace_module.WorkspaceError) as raised:
                workspace_module.disable_member("ws-2", "alice", "someone")

        self.assertEqual("cannot_disable_owner", raised.exception.code)

    def test_resolve_context_falls_back_to_personal_workspace(self):
        personal = {"id": "ws-1", "type": "personal", "owner_user_id": "alice"}
        membership = {"workspace_id": "ws-1", "user_id": "alice", "role": "owner", "status": "active"}
        with (
            patch.object(workspace_module, "ensure_personal_workspace", return_value=personal),
            patch.object(workspace_module, "get_membership", return_value=membership),
        ):
            workspace, resolved_membership = workspace_module.resolve_context("alice", None)

        self.assertEqual("ws-1", workspace["id"])
        self.assertEqual("owner", resolved_membership["role"])

    def test_resolve_context_rejects_non_member(self):
        business = {"id": "ws-2", "type": "business", "owner_user_id": "alice"}
        with (
            patch.object(workspace_module, "get_workspace", return_value=business),
            patch.object(workspace_module, "get_membership", return_value=None),
        ):
            with self.assertRaises(workspace_module.WorkspaceError) as raised:
                workspace_module.resolve_context("mallory", "ws-2")

        self.assertEqual("membership_required", raised.exception.code)


class WorkspaceRouteTests(unittest.TestCase):
    """Route-level tests patch the model directly (same convention as
    test_subscription_management.py's SubscriptionRouteTests), so IDOR/role
    enforcement is tested without needing to fake Postgres SQL."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="workspace-test")
        self.app.register_blueprint(workspace_route.workspace_bp)
        self.app.register_blueprint(workspace_route.workspace_invitations_bp)
        self.client = self.app.test_client()

    def test_get_workspace_rejects_non_member(self):
        with (
            patch.object(workspace_route, "get_current_user_id", return_value="mallory"),
            patch.object(workspace_route.workspace_model, "get_membership", return_value=None),
        ):
            response = self.client.get("/api/workspaces/ws-2")

        self.assertEqual(403, response.status_code)
        self.assertEqual("membership_required", response.get_json()["error"])

    def test_worker_cannot_create_invitation(self):
        worker_membership = {"role": "worker", "status": "active"}
        with (
            patch.object(workspace_route, "get_current_user_id", return_value="bob"),
            patch.object(workspace_route.workspace_model, "get_membership", return_value=worker_membership),
        ):
            response = self.client.post(
                "/api/workspaces/ws-2/invitations",
                json={"email": "new@example.com", "role": "worker"},
            )

        self.assertEqual(403, response.status_code)
        self.assertEqual("insufficient_role", response.get_json()["error"])

    def test_admin_can_create_invitation(self):
        admin_membership = {"role": "admin", "status": "active"}
        created = {"id": "inv-1", "email_normalized": "new@example.com", "role": "worker", "token": "raw-token"}
        with (
            patch.object(workspace_route, "get_current_user_id", return_value="carol"),
            patch.object(workspace_route.workspace_model, "get_membership", return_value=admin_membership),
            patch.object(workspace_route.workspace_model, "create_invitation", return_value=created) as create,
        ):
            response = self.client.post(
                "/api/workspaces/ws-2/invitations",
                json={"email": "new@example.com", "role": "worker"},
            )

        self.assertEqual(201, response.status_code)
        self.assertEqual("raw-token", response.get_json()["invitation"]["token"])
        create.assert_called_once_with("ws-2", "new@example.com", "worker", "carol")

    def test_accept_invitation_rejects_email_mismatch(self):
        with (
            patch.object(workspace_route, "get_current_user_id", return_value="mallory"),
            patch.object(workspace_route, "_current_user_emails", return_value=["mallory@example.com"]),
            patch.object(
                workspace_route.workspace_model, "find_invitation_by_token",
                return_value={"id": "inv-1", "email_normalized": "bob@example.com"},
            ),
        ):
            response = self.client.post("/api/workspace-invitations/some-token/accept")

        self.assertEqual(403, response.status_code)
        self.assertEqual("invitation_email_mismatch", response.get_json()["error"])

    def test_owner_can_change_member_role(self):
        owner_membership = {"role": "owner", "status": "active"}
        updated = {"user_id": "bob", "role": "admin", "status": "active"}
        with (
            patch.object(workspace_route, "get_current_user_id", return_value="alice"),
            patch.object(workspace_route.workspace_model, "get_membership", return_value=owner_membership),
            patch.object(workspace_route.workspace_model, "update_member_role", return_value=updated) as update,
        ):
            response = self.client.patch(
                "/api/workspaces/ws-2/members/bob/role",
                json={"role": "admin"},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("admin", response.get_json()["membership"]["role"])
        update.assert_called_once_with("ws-2", "bob", "admin", "alice")


if __name__ == "__main__":
    unittest.main()
