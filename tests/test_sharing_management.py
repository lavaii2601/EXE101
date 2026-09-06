import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from flask import Flask


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models import shared_artifact as artifact_module  # noqa: E402
from models import workspace as workspace_module  # noqa: E402
from models import workspace_subscription as subscription_module  # noqa: E402
from routes import sharing as sharing_route  # noqa: E402

WORKSPACE_A = "20000000-0000-4000-8000-00000000000a"
WORKSPACE_B = "20000000-0000-4000-8000-00000000000b"


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
        patch.object(module.pg, "json_value", side_effect=lambda v: v),
    ):
        yield


class VisibilitySqlTests(unittest.TestCase):
    def test_worker_list_scopes_to_own_shares_or_workspace_visibility(self):
        connection = _ScriptedConnection([("SELECT * FROM shared_artifacts", _Result(many=[]))])
        with _patched_pg(artifact_module, connection):
            artifact_module.list_artifacts(WORKSPACE_A, "alice", "worker")
        sql, params = connection.calls[0]
        self.assertIn("source_owner_user_id = %s OR visibility = 'workspace'", sql)
        self.assertEqual((WORKSPACE_A, "alice"), params)

    def test_admin_list_has_no_visibility_filter(self):
        connection = _ScriptedConnection([("SELECT * FROM shared_artifacts", _Result(many=[]))])
        with _patched_pg(artifact_module, connection):
            artifact_module.list_artifacts(WORKSPACE_A, "carol", "admin")
        sql, params = connection.calls[0]
        self.assertNotIn("source_owner_user_id = %s OR visibility", sql)
        self.assertEqual((WORKSPACE_A,), params)

    def test_get_artifact_is_scoped_to_the_requested_workspace(self):
        connection = _ScriptedConnection([("SELECT * FROM shared_artifacts", _Result(one=None))])
        with _patched_pg(artifact_module, connection):
            result = artifact_module.get_artifact(WORKSPACE_B, "a1")
        sql, params = connection.calls[0]
        self.assertIn("workspace_id = %s", sql)
        self.assertIn("revoked_at IS NULL", sql)
        self.assertEqual(("a1", WORKSPACE_B), params)
        self.assertIsNone(result)

    def test_is_artifact_visible_owner_admin_bypass(self):
        artifact = {"source_owner_user_id": "alice", "visibility": "private"}
        self.assertTrue(artifact_module.is_artifact_visible(artifact, "carol", "admin"))
        self.assertTrue(artifact_module.is_artifact_visible(artifact, "alice", "worker"))
        self.assertFalse(artifact_module.is_artifact_visible(artifact, "bob", "worker"))

    def test_is_artifact_visible_workspace_visibility_open_to_any_member(self):
        artifact = {"source_owner_user_id": "alice", "visibility": "workspace"}
        self.assertTrue(artifact_module.is_artifact_visible(artifact, "bob", "worker"))


class RevokeSharerOnlyTests(unittest.TestCase):
    def test_owner_cannot_revoke_someone_elses_artifact(self):
        with (
            patch.object(artifact_module.pg, "enabled", return_value=True),
            patch.object(
                artifact_module, "get_artifact",
                return_value={"id": "a1", "source_owner_user_id": "alice"},
            ),
        ):
            with self.assertRaises(artifact_module.ArtifactError) as ctx:
                artifact_module.revoke_artifact(WORKSPACE_A, "a1", "carol")
        self.assertEqual("insufficient_role", ctx.exception.code)

    def test_sharer_can_revoke_their_own_artifact(self):
        connection = _ScriptedConnection([
            ("UPDATE shared_artifacts SET revoked_at = NOW()", _Result(one={"id": "a1"})),
            ("INSERT INTO workspace_audit_events", _Result()),
        ])
        with (
            patch.object(artifact_module, "get_artifact", return_value={"id": "a1", "source_owner_user_id": "alice"}),
            _patched_pg(artifact_module, connection),
        ):
            revoked = artifact_module.revoke_artifact(WORKSPACE_A, "a1", "alice")
        self.assertTrue(revoked)

    def test_revoke_nonexistent_artifact_raises_not_found(self):
        with (
            patch.object(artifact_module.pg, "enabled", return_value=True),
            patch.object(artifact_module, "get_artifact", return_value=None),
        ):
            with self.assertRaises(artifact_module.ArtifactError) as ctx:
                artifact_module.revoke_artifact(WORKSPACE_A, "missing", "alice")
        self.assertEqual("artifact_not_found", ctx.exception.code)


class CrossWorkspaceIsolationTests(unittest.TestCase):
    def test_list_my_shares_is_not_workspace_scoped_but_joins_workspace_name(self):
        connection = _ScriptedConnection([("SELECT sa.*, w.name AS workspace_name", _Result(many=[]))])
        with _patched_pg(artifact_module, connection):
            artifact_module.list_my_shares("alice")
        sql, params = connection.calls[0]
        self.assertIn("JOIN workspaces w ON w.id = sa.workspace_id", sql)
        self.assertIn("source_owner_user_id = %s AND sa.revoked_at IS NULL", sql)
        self.assertEqual(("alice",), params)


class WorkspaceReadOnlyEnforcementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(TESTING=True, SECRET_KEY="test")
        cls.app.register_blueprint(sharing_route.sharing_bp)

    def _resolve_as(self, role, workspace_type="business"):
        workspace = {"id": WORKSPACE_A, "type": workspace_type}
        membership = {"role": role, "status": "active"}
        return (
            patch.object(sharing_route, "get_current_user_id", return_value="alice"),
            patch.object(
                sharing_route.workspace_model, "resolve_context",
                return_value=(workspace, membership),
            ),
        )

    def test_read_only_blocks_create(self):
        p1, p2 = self._resolve_as("worker")
        with p1, p2, patch.object(
            sharing_route.workspace_subscription, "assert_writable",
            side_effect=subscription_module.WorkspaceSubscriptionError("workspace_read_only"),
        ):
            response = self.app.test_client().post(
                "/api/workspaces/x/shared-artifacts",
                json={"source_type": "email_summary", "title": "t", "content": {}},
            )
        self.assertEqual(403, response.status_code)
        self.assertEqual("workspace_read_only", response.get_json()["error"])

    def test_read_only_still_allows_list(self):
        p1, p2 = self._resolve_as("worker")
        with p1, p2, patch.object(artifact_module, "list_artifacts", return_value=[]):
            response = self.app.test_client().get("/api/workspaces/x/shared-artifacts")
        self.assertEqual(200, response.status_code)


class PersonalRoutesHaveNoWorkspaceConceptTests(unittest.TestCase):
    """Regression guard for Phase 4's DoD line "Owner/admin khong truy van
    duoc mailbox/calendar nguon": routes/email.py and routes/calendar.py
    must never gain a workspace_id-scoped code path, since that would let a
    workspace-scoped caller reach another member's personal mailbox data."""

    def test_email_routes_have_no_workspace_concept(self):
        source = (BACKEND_DIR / "routes" / "email.py").read_text(encoding="utf-8")
        self.assertNotIn("workspace_id", source)
        self.assertNotIn("resolve_context", source)

    def test_calendar_routes_have_no_workspace_concept(self):
        source = (BACKEND_DIR / "routes" / "calendar.py").read_text(encoding="utf-8")
        self.assertNotIn("workspace_id", source)
        self.assertNotIn("resolve_context", source)


class SmartInboxBucketTests(unittest.TestCase):
    def _email(self, **overrides):
        base = {
            "subject": "Weekly newsletter",
            "sender": "newsletter@shop.com",
            "snippet": "Check out our latest deals",
            "is_unread": True,
        }
        base.update(overrides)
        return base

    def test_promotion_tag_is_low_priority(self):
        from routes import email as email_route
        email = self._email(tag="promotion")
        self.assertEqual("low_priority", email_route._smart_inbox_bucket(email))

    def test_automated_sender_is_low_priority(self):
        from routes import email as email_route
        email = self._email(sender="noreply@service.com", tag="other")
        self.assertEqual("low_priority", email_route._smart_inbox_bucket(email))

    def test_deadline_term_is_action_required(self):
        from routes import email as email_route
        email = self._email(
            tag="work", sender="boss@company.com",
            subject="Submission deadline this Friday", snippet="Please submit by Friday",
        )
        self.assertEqual("action_required", email_route._smart_inbox_bucket(email))

    def test_unread_question_is_action_required(self):
        from routes import email as email_route
        email = self._email(
            tag="other", sender="colleague@company.com",
            subject="Can you review this?", snippet="Let me know your thoughts",
        )
        self.assertEqual("action_required", email_route._smart_inbox_bucket(email))

    def test_waiting_term_is_waiting(self):
        from routes import email as email_route
        email = self._email(
            tag="other", sender="support@service.com", is_unread=False,
            subject="Your request has been received", snippet="Your request is pending review",
        )
        self.assertEqual("waiting", email_route._smart_inbox_bucket(email))

    def test_default_bucket_is_fyi(self):
        from routes import email as email_route
        email = self._email(tag="other", sender="friend@example.com", is_unread=False, subject="Hi", snippet="How are you")
        self.assertEqual("fyi", email_route._smart_inbox_bucket(email))


if __name__ == "__main__":
    unittest.main()
