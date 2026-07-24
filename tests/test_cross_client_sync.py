import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from flask import Flask, jsonify, redirect, request, session


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models import workspace_sync as workspace_sync_module  # noqa: E402
from models.workspace_sync import (  # noqa: E402
    WORKSPACE_SYNC_DOMAINS,
    WorkspaceSync,
)
from routes import sync as sync_route  # noqa: E402


class _Result:
    def __init__(self, one=None, rowcount=0):
        self._one = one
        self.rowcount = rowcount

    def fetchone(self):
        return self._one


class _RecordingConnection:
    def __init__(self, revision=4, domains=None):
        self.revision = revision
        self.domains = domains or {"chat": 3}
        self.calls = []

    def execute(self, statement, params=()):
        sql = " ".join(str(statement).split())
        self.calls.append((sql, tuple(params)))
        if "FOR UPDATE" in sql:
            return _Result(
                one={
                    "revision": self.revision,
                    "domains": self.domains,
                }
            )
        return _Result(rowcount=1)


@contextmanager
def _connection(connection):
    yield connection


class WorkspaceSyncModelTests(unittest.TestCase):
    def test_sqlite_revisions_are_monotonic_and_tenant_scoped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "shared.db")
            with patch.object(workspace_sync_module.pg, "enabled", return_value=False):
                initial = WorkspaceSync.get_state("alice", db_path=db_path)
                first = WorkspaceSync.bump(
                    "alice",
                    ["history", "chat", "unknown"],
                    db_path=db_path,
                )
                second = WorkspaceSync.bump(
                    "alice",
                    ["schedule"],
                    db_path=db_path,
                )
                bob = WorkspaceSync.get_state("bob", db_path=db_path)

        self.assertEqual(0, initial["revision"])
        self.assertEqual(1, first["revision"])
        self.assertEqual(1, first["domains"]["chat"])
        self.assertEqual(1, first["domains"]["history"])
        self.assertNotIn("unknown", first["domains"])
        self.assertEqual(2, second["revision"])
        self.assertEqual(1, second["domains"]["chat"])
        self.assertEqual(2, second["domains"]["schedule"])
        self.assertEqual(0, bob["revision"])
        self.assertEqual(
            {domain: 0 for domain in WORKSPACE_SYNC_DOMAINS},
            bob["domains"],
        )

    def test_postgres_bump_locks_and_updates_only_requested_user(self):
        connection = _RecordingConnection()
        with (
            patch.object(workspace_sync_module.pg, "enabled", return_value=True),
            patch.object(workspace_sync_module.pg, "ensure_user") as ensure_user,
            patch.object(
                workspace_sync_module.pg,
                "connection",
                side_effect=lambda: _connection(connection),
            ),
            patch.object(
                workspace_sync_module.pg,
                "json_value",
                side_effect=lambda value: value,
            ),
        ):
            state = WorkspaceSync.bump("alice", ["email", "overview"])

        self.assertEqual(5, state["revision"])
        self.assertEqual(5, state["domains"]["email"])
        self.assertEqual(5, state["domains"]["overview"])
        ensure_user.assert_called_once_with("alice")
        lock_call = next(call for call in connection.calls if "FOR UPDATE" in call[0])
        update_call = next(
            call
            for call in connection.calls
            if call[0].startswith("UPDATE workspace_sync_state")
        )
        self.assertIn("WHERE user_id = %s", lock_call[0])
        self.assertEqual(("alice",), lock_call[1])
        self.assertIn("WHERE user_id = %s", update_call[0])
        self.assertEqual("alice", update_call[1][-1])

    def test_postgres_schema_declares_sync_state_table(self):
        schema = (REPO_ROOT / "database" / "postgres_schema.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_sync_state", schema)
        self.assertIn(
            "user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE",
            schema,
        )


class WorkspaceSyncRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "sync.db")
        self.pg_patch = patch.object(
            workspace_sync_module.pg,
            "enabled",
            return_value=False,
        )
        self.pg_patch.start()
        self.path_patch = patch.object(
            sync_route,
            "get_user_db_path",
            return_value=self.db_path,
        )
        self.path_patch.start()

        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            MOBILE_USER_HEADER_ENABLED=False,
        )
        self.app.register_blueprint(sync_route.sync_bp)
        self.client = self.app.test_client()

    def tearDown(self):
        self.path_patch.stop()
        self.pg_patch.stop()
        self.temp_dir.cleanup()

    def _login(self, user_id):
        with self.client.session_transaction() as browser_session:
            browser_session["user_id"] = user_id

    def test_state_requires_authentication_and_returns_contract(self):
        unauthenticated = self.client.get("/api/sync/state")
        self.assertEqual(401, unauthenticated.status_code)
        self.assertEqual(
            "not_authenticated",
            unauthenticated.get_json()["error"],
        )

        self._login("alice")
        WorkspaceSync.bump(
            "alice",
            ["chat", "email"],
            db_path=self.db_path,
        )
        response = self.client.get("/api/sync/state?since=0")
        payload = response.get_json()

        self.assertEqual(200, response.status_code)
        self.assertTrue(payload["success"])
        self.assertEqual(1, payload["revision"])
        self.assertEqual(set(WORKSPACE_SYNC_DOMAINS), set(payload["domains"]))
        self.assertEqual(["chat", "email"], payload["changed"])
        self.assertGreaterEqual(payload["poll_after_ms"], 2000)

        unchanged = self.client.get("/api/sync/state?since=1").get_json()
        self.assertEqual([], unchanged["changed"])

    def test_since_ahead_of_current_resets_for_account_switch(self):
        self._login("alice")
        WorkspaceSync.bump(
            "alice",
            ["settings"],
            db_path=self.db_path,
        )
        payload = self.client.get("/api/sync/state?since=999").get_json()
        self.assertEqual(["settings"], payload["changed"])

    def test_route_state_is_tenant_isolated(self):
        WorkspaceSync.bump(
            "alice",
            ["history"],
            db_path=self.db_path,
        )
        self._login("bob")
        payload = self.client.get("/api/sync/state?since=0").get_json()
        self.assertEqual(0, payload["revision"])
        self.assertEqual([], payload["changed"])


class WorkspaceSyncHookTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "hooks.db")
        self.pg_patch = patch.object(
            workspace_sync_module.pg,
            "enabled",
            return_value=False,
        )
        self.pg_patch.start()
        self.path_patch = patch.object(
            sync_route,
            "get_user_db_path",
            return_value=self.db_path,
        )
        self.path_patch.start()

        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="hook-secret",
            MOBILE_USER_HEADER_ENABLED=False,
        )

        @self.app.route("/api/chat/message", methods=["POST"])
        def chat_message():
            return jsonify(
                {
                    "success": True,
                    "response": "done",
                    "refresh_targets": ["email", "overview"],
                }
            )

        @self.app.route("/api/calendar/create", methods=["POST"])
        def calendar_create():
            if request.args.get("fail") == "1":
                return jsonify({"success": False, "error": "failed"}), 500
            return jsonify({"success": True})

        @self.app.route("/api/user/profile", methods=["GET", "POST"])
        def user_profile():
            return jsonify({"success": True})

        @self.app.route("/api/schedule/plan-day", methods=["POST"])
        def suggest_plan():
            return jsonify({"success": True, "kind": "suggested_plan"})

        @self.app.route("/api/email/oauth2callback", methods=["GET"])
        def oauth_callback():
            session["user_id"] = "oauth-user"
            return redirect("/app")

        @self.app.route("/api/email/logout", methods=["POST"])
        def email_logout():
            session.clear()
            return jsonify({"success": True})

        sync_route.install_workspace_sync_hooks(self.app)
        self.app.register_blueprint(sync_route.sync_bp)
        self.client = self.app.test_client()

    def tearDown(self):
        self.path_patch.stop()
        self.pg_patch.stop()
        self.temp_dir.cleanup()

    def _login(self, user_id="alice"):
        with self.client.session_transaction() as browser_session:
            browser_session["user_id"] = user_id

    def test_successful_mutation_bumps_once_with_response_targets(self):
        self._login()
        response = self.client.post(
            "/api/chat/message",
            json={"message": "mark it read"},
        )
        state = WorkspaceSync.get_state("alice", db_path=self.db_path)

        self.assertEqual(200, response.status_code)
        self.assertEqual(1, state["revision"])
        self.assertEqual(1, state["domains"]["chat"])
        self.assertEqual(1, state["domains"]["history"])
        self.assertEqual(1, state["domains"]["email"])
        self.assertEqual(1, state["domains"]["overview"])

    def test_reads_failures_parse_only_posts_and_sync_state_do_not_bump(self):
        self._login()
        self.client.get("/api/user/profile")
        self.client.post("/api/calendar/create?fail=1")
        self.client.post("/api/schedule/plan-day", json={"text": "ideas"})
        self.client.get("/api/sync/state?since=0")
        state = WorkspaceSync.get_state("alice", db_path=self.db_path)
        self.assertEqual(0, state["revision"])

    def test_oauth_callback_uses_identity_established_during_route(self):
        response = self.client.get("/api/email/oauth2callback")
        state = WorkspaceSync.get_state("oauth-user", db_path=self.db_path)

        self.assertEqual(302, response.status_code)
        self.assertEqual(1, state["revision"])
        self.assertEqual(1, state["domains"]["email"])
        self.assertEqual(1, state["domains"]["profile"])
        self.assertEqual(1, state["domains"]["settings"])

    def test_logout_uses_identity_captured_before_route_clears_session(self):
        self._login()
        response = self.client.post("/api/email/logout")
        state = WorkspaceSync.get_state("alice", db_path=self.db_path)

        self.assertEqual(200, response.status_code)
        self.assertEqual(1, state["revision"])
        self.assertEqual(1, state["domains"]["email"])
        self.assertEqual(1, state["domains"]["settings"])

    def test_sync_bump_failure_does_not_change_successful_response(self):
        self._login()
        with patch.object(
            sync_route.WorkspaceSync,
            "bump",
            side_effect=RuntimeError("database unavailable"),
        ), self.assertLogs(self.app.logger.name, level="ERROR"):
            response = self.client.post(
                "/api/user/profile",
                json={"user_mode": "worker"},
            )

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
