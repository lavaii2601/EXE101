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

from models import project as project_module  # noqa: E402
from models import status_report as status_report_module  # noqa: E402
from models import task as task_module  # noqa: E402
from models import workspace as workspace_module  # noqa: E402
from models import workspace_subscription as subscription_module  # noqa: E402
from routes import work_hub as work_hub_route  # noqa: E402

WORKSPACE_A = "10000000-0000-4000-8000-00000000000a"
WORKSPACE_B = "10000000-0000-4000-8000-00000000000b"


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


class ProjectVisibilitySqlTests(unittest.TestCase):
    def test_worker_list_scopes_to_workspace_visibility_or_own(self):
        connection = _ScriptedConnection([("SELECT * FROM projects", _Result(many=[]))])
        with _patched_pg(project_module, connection):
            project_module.list_projects(WORKSPACE_A, "alice", "worker")
        sql, params = connection.calls[0]
        self.assertIn("visibility = 'workspace' OR owner_user_id = %s OR created_by_user_id = %s", sql)
        self.assertEqual((WORKSPACE_A, "alice", "alice"), params)

    def test_admin_list_has_no_visibility_filter(self):
        connection = _ScriptedConnection([("SELECT * FROM projects", _Result(many=[]))])
        with _patched_pg(project_module, connection):
            project_module.list_projects(WORKSPACE_A, "carol", "admin")
        sql, params = connection.calls[0]
        self.assertNotIn("visibility = 'workspace'", sql)
        self.assertEqual((WORKSPACE_A,), params)

    def test_get_project_is_scoped_to_the_requested_workspace(self):
        connection = _ScriptedConnection([("SELECT * FROM projects", _Result(one=None))])
        with _patched_pg(project_module, connection):
            result = project_module.get_project(WORKSPACE_B, "p1")
        sql, params = connection.calls[0]
        self.assertIn("workspace_id = %s", sql)
        self.assertEqual(("p1", WORKSPACE_B), params)
        self.assertIsNone(result)


class TaskVisibilitySqlTests(unittest.TestCase):
    def test_worker_list_scopes_to_assignee_creator_or_visible_project(self):
        connection = _ScriptedConnection([("SELECT t.* FROM tasks t", _Result(many=[]))])
        with _patched_pg(task_module, connection):
            task_module.list_tasks(WORKSPACE_A, "bob", "worker")
        sql, params = connection.calls[0]
        self.assertIn("t.assignee_user_id = %s OR t.created_by_user_id = %s", sql)
        self.assertIn("p.visibility = 'workspace' OR p.owner_user_id = %s OR p.created_by_user_id = %s", sql)
        self.assertEqual((WORKSPACE_A, "bob", "bob", "bob", "bob"), params)

    def test_get_task_is_scoped_to_the_requested_workspace(self):
        connection = _ScriptedConnection([("SELECT * FROM tasks", _Result(one=None))])
        with _patched_pg(task_module, connection):
            result = task_module.get_task(WORKSPACE_B, "t1")
        sql, params = connection.calls[0]
        self.assertIn("workspace_id = %s", sql)
        self.assertEqual(("t1", WORKSPACE_B), params)
        self.assertIsNone(result)

    def test_create_task_rejects_project_from_a_different_workspace(self):
        # get_project(workspace_id=B, project_id) scoped by workspace_id=B
        # finds nothing because the project actually belongs to workspace A.
        connection = _ScriptedConnection([("SELECT * FROM projects", _Result(one=None))])
        with _patched_pg(project_module, connection), _patched_pg(task_module, connection):
            with self.assertRaises(task_module.TaskError) as ctx:
                task_module.create_task(WORKSPACE_B, "project-in-a", "eve", title="Steal data")
        self.assertEqual("project_not_found", ctx.exception.code)


class StatusReportLifecycleTests(unittest.TestCase):
    def test_publish_is_one_way(self):
        published = {
            "id": "r1", "workspace_id": WORKSPACE_A, "author_user_id": "alice", "status": "published",
        }
        with (
            patch.object(status_report_module.pg, "enabled", return_value=True),
            patch.object(status_report_module, "get_report", return_value=published),
        ):
            with self.assertRaises(status_report_module.StatusReportError) as ctx:
                status_report_module.update_draft(WORKSPACE_A, "r1", "alice", done_text="edited after publish")
        self.assertEqual("report_not_editable", ctx.exception.code)

    def test_publish_rejects_all_blank_fields(self):
        draft = {
            "id": "r1", "workspace_id": WORKSPACE_A, "author_user_id": "alice", "status": "draft",
            "done_text": "", "doing_text": "  ", "blocked_text": "", "next_text": "", "risks_text": "",
        }
        with (
            patch.object(status_report_module.pg, "enabled", return_value=True),
            patch.object(status_report_module, "get_report", return_value=draft),
        ):
            with self.assertRaises(status_report_module.StatusReportError) as ctx:
                status_report_module.publish_report(WORKSPACE_A, "r1", "alice")
        self.assertEqual("report_empty", ctx.exception.code)

    def test_only_author_or_admin_can_edit_a_draft(self):
        draft = {
            "id": "r1", "workspace_id": WORKSPACE_A, "author_user_id": "alice", "status": "draft",
        }
        with (
            patch.object(status_report_module.pg, "enabled", return_value=True),
            patch.object(status_report_module, "get_report", return_value=draft),
        ):
            with self.assertRaises(status_report_module.StatusReportError) as ctx:
                status_report_module.update_draft(WORKSPACE_A, "r1", "mallory", done_text="not mine")
        self.assertEqual("report_not_editable", ctx.exception.code)

    def test_draft_is_only_visible_to_its_author(self):
        draft = {"author_user_id": "alice", "status": "draft", "visibility": "workspace"}
        self.assertTrue(status_report_module.is_report_visible(draft, "alice", "worker"))
        self.assertFalse(status_report_module.is_report_visible(draft, "bob", "worker"))
        self.assertTrue(status_report_module.is_report_visible(draft, "bob", "admin"))

    def test_published_workspace_visible_report_is_visible_to_any_member(self):
        published = {"author_user_id": "alice", "status": "published", "visibility": "workspace"}
        self.assertTrue(status_report_module.is_report_visible(published, "bob", "worker"))

    def test_update_draft_records_an_audit_event(self):
        # create_draft/publish_report/delete_report all record an audit
        # event; update_draft was the one lifecycle mutation that didn't,
        # leaving a gap in the trail between a report's creation and its
        # publish/delete with no record of what changed in between.
        draft = {
            "id": "r1", "workspace_id": WORKSPACE_A, "author_user_id": "alice", "status": "draft",
        }
        updated_row = {**draft, "done_text": "progress update"}
        connection = _ScriptedConnection([
            ("UPDATE status_reports SET", _Result(one=updated_row)),
            ("INSERT INTO workspace_audit_events", _Result(rowcount=1)),
        ])
        with (
            patch.object(status_report_module, "get_report", return_value=draft),
            _patched_pg(status_report_module, connection),
        ):
            result = status_report_module.update_draft(
                WORKSPACE_A, "r1", "alice", done_text="progress update",
            )
        self.assertEqual("progress update", result["done_text"])
        audit_call = connection.calls[1]
        self.assertIn("status_report_draft_updated", audit_call[1])

    def test_delete_published_report_requires_admin_role(self):
        with (
            patch.object(status_report_module.pg, "enabled", return_value=True),
            patch.object(
                status_report_module, "get_report",
                return_value={"id": "r1", "author_user_id": "alice", "status": "published"},
            ),
        ):
            with self.assertRaises(status_report_module.StatusReportError) as ctx:
                status_report_module.delete_report(WORKSPACE_A, "r1", "alice", "worker")
        self.assertEqual("insufficient_role", ctx.exception.code)


class WorkspaceReadOnlyEnforcementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(TESTING=True, SECRET_KEY="test")
        cls.app.register_blueprint(work_hub_route.work_hub_bp)

    def _resolve_as(self, role, workspace_type="business"):
        workspace = {"id": WORKSPACE_A, "type": workspace_type}
        membership = {"role": role, "status": "active"}
        return (
            patch.object(work_hub_route, "get_current_user_id", return_value="alice"),
            patch.object(
                work_hub_route.workspace_model, "resolve_context",
                return_value=(workspace, membership),
            ),
        )

    def test_read_only_blocks_project_creation(self):
        p1, p2 = self._resolve_as("owner")
        with p1, p2, patch.object(
            work_hub_route.workspace_subscription, "assert_writable",
            side_effect=subscription_module.WorkspaceSubscriptionError("workspace_read_only"),
        ):
            response = self.app.test_client().post("/api/projects", json={"name": "New"})
        self.assertEqual(403, response.status_code)
        self.assertEqual("workspace_read_only", response.get_json()["error"])

    def test_read_only_still_allows_reads(self):
        p1, p2 = self._resolve_as("worker")
        with p1, p2, patch.object(project_module, "list_projects", return_value=[]):
            response = self.app.test_client().get("/api/projects")
        self.assertEqual(200, response.status_code)

    def test_worker_cannot_create_project(self):
        p1, p2 = self._resolve_as("worker")
        with p1, p2:
            response = self.app.test_client().post("/api/projects", json={"name": "New"})
        self.assertEqual(403, response.status_code)
        self.assertEqual("insufficient_role", response.get_json()["error"])


class ProjectDeleteAuthorizationTests(unittest.TestCase):
    """delete_project used to enforce the workspace-wide owner/admin-only
    _require_manage_role instead of can_manage_project (its own docstring:
    "whether the caller may PATCH/DELETE this project") -- so a worker set
    as a project's delegate owner_user_id could PATCH it but got 403 trying
    to DELETE the very project they're documented to manage."""

    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(TESTING=True, SECRET_KEY="test")
        cls.app.register_blueprint(work_hub_route.work_hub_bp)

    def _resolve_as(self, role, user_id="alice", workspace_type="business"):
        workspace = {"id": WORKSPACE_A, "type": workspace_type}
        membership = {"role": role, "status": "active"}
        return (
            patch.object(work_hub_route, "get_current_user_id", return_value=user_id),
            patch.object(
                work_hub_route.workspace_model, "resolve_context",
                return_value=(workspace, membership),
            ),
        )

    def test_project_delegate_owner_can_delete_their_own_project(self):
        p1, p2 = self._resolve_as("worker", user_id="alice")
        project = {"id": "p1", "owner_user_id": "alice"}
        with (
            p1, p2,
            patch.object(project_module, "get_project", return_value=project),
            patch.object(project_module, "delete_project", return_value=True) as delete,
        ):
            response = self.app.test_client().delete("/api/projects/p1")
        self.assertEqual(200, response.status_code)
        delete.assert_called_once_with(WORKSPACE_A, "p1", "alice")

    def test_worker_who_is_not_the_project_delegate_cannot_delete_it(self):
        p1, p2 = self._resolve_as("worker", user_id="bob")
        project = {"id": "p1", "owner_user_id": "alice"}
        with (
            p1, p2,
            patch.object(project_module, "get_project", return_value=project),
            patch.object(project_module, "delete_project") as delete,
        ):
            response = self.app.test_client().delete("/api/projects/p1")
        self.assertEqual(403, response.status_code)
        self.assertEqual("insufficient_role", response.get_json()["error"])
        delete.assert_not_called()

    def test_workspace_admin_can_delete_a_project_they_do_not_own(self):
        p1, p2 = self._resolve_as("admin", user_id="admin-user")
        project = {"id": "p1", "owner_user_id": "alice"}
        with (
            p1, p2,
            patch.object(project_module, "get_project", return_value=project),
            patch.object(project_module, "delete_project", return_value=True) as delete,
        ):
            response = self.app.test_client().delete("/api/projects/p1")
        self.assertEqual(200, response.status_code)
        delete.assert_called_once_with(WORKSPACE_A, "p1", "admin-user")

    def test_delete_missing_project_is_not_found(self):
        p1, p2 = self._resolve_as("owner")
        with p1, p2, patch.object(project_module, "get_project", return_value=None):
            response = self.app.test_client().delete("/api/projects/missing")
        self.assertEqual(404, response.status_code)
        self.assertEqual("project_not_found", response.get_json()["error"])


class WorkHubDashboardTests(unittest.TestCase):
    """Phase 5's team dashboard: a pure Python rollup over whatever
    list_projects/list_tasks/list_reports already returned for this caller,
    so these tests only need to fake those lists, not real SQL."""

    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(TESTING=True, SECRET_KEY="test")
        cls.app.register_blueprint(work_hub_route.work_hub_bp)

    def _resolve_as(self, role, workspace_type="business"):
        workspace = {"id": WORKSPACE_A, "type": workspace_type}
        membership = {"role": role, "status": "active"}
        return (
            patch.object(work_hub_route, "get_current_user_id", return_value="alice"),
            patch.object(
                work_hub_route.workspace_model, "resolve_context",
                return_value=(workspace, membership),
            ),
        )

    def test_rollup_counts_match_the_underlying_lists(self):
        projects = [
            {"id": "p1", "status": "active"},
            {"id": "p2", "status": "active"},
            {"id": "p3", "status": "completed"},
        ]
        tasks = [
            {"id": "t1", "status": "todo", "due_date": "2020-01-01"},  # overdue
            {"id": "t2", "status": "done", "due_date": "2020-01-01"},  # not overdue, done
            {"id": "t3", "status": "in_progress", "due_date": None},
        ]
        reports = [
            {"id": "r2", "project_id": "p1", "report_date": "2026-09-05"},
            {"id": "r1", "project_id": "p1", "report_date": "2026-09-01"},
            {"id": "r3", "project_id": None, "report_date": "2026-09-03"},
        ]
        p1, p2 = self._resolve_as("owner")
        with (
            p1, p2,
            patch.object(project_module, "list_projects", return_value=projects),
            patch.object(task_module, "list_tasks", return_value=tasks),
            patch.object(status_report_module, "list_reports", return_value=reports),
            patch.object(workspace_module, "list_members", return_value=[{"user_id": "alice"}, {"user_id": "bob"}]),
        ):
            response = self.app.test_client().get("/api/work-hub/dashboard")
        self.assertEqual(200, response.status_code)
        dashboard = response.get_json()["dashboard"]
        self.assertEqual(2, dashboard["project_counts"]["active"])
        self.assertEqual(1, dashboard["project_counts"]["completed"])
        self.assertEqual(3, dashboard["total_projects"])
        self.assertEqual(3, dashboard["total_tasks"])
        self.assertEqual(1, dashboard["overdue_tasks"])
        self.assertEqual(2, dashboard["active_members"])
        # Latest report per project: r2 (newer than r1) for p1, r3 for the
        # no-project bucket.
        latest_ids = {r["id"] for r in dashboard["latest_reports"]}
        self.assertEqual({"r2", "r3"}, latest_ids)

    def test_worker_dashboard_only_sees_what_list_calls_already_scoped(self):
        # The route never applies its own visibility filter -- it trusts
        # list_projects/list_tasks/list_reports to have already scoped the
        # results to this caller. This test just confirms the role/user
        # actually reaches those calls, matching the real scoping tested
        # directly in ProjectVisibilitySqlTests/TaskVisibilitySqlTests above.
        p1, p2 = self._resolve_as("worker")
        with (
            p1, p2,
            patch.object(project_module, "list_projects", return_value=[]) as list_projects,
            patch.object(task_module, "list_tasks", return_value=[]) as list_tasks,
            patch.object(status_report_module, "list_reports", return_value=[]) as list_reports,
            patch.object(workspace_module, "list_members", return_value=[]),
        ):
            response = self.app.test_client().get("/api/work-hub/dashboard")
        self.assertEqual(200, response.status_code)
        list_projects.assert_called_once_with(WORKSPACE_A, "alice", "worker")
        list_tasks.assert_called_once_with(WORKSPACE_A, "alice", "worker")
        list_reports.assert_called_once_with(WORKSPACE_A, "alice", "worker")

    def test_membership_required_before_reading_dashboard(self):
        with (
            patch.object(work_hub_route, "get_current_user_id", return_value="mallory"),
            patch.object(
                work_hub_route.workspace_model, "resolve_context",
                side_effect=work_hub_route.workspace_model.WorkspaceError("membership_required"),
            ),
        ):
            response = self.app.test_client().get("/api/work-hub/dashboard")
        self.assertEqual(403, response.status_code)
        self.assertEqual("membership_required", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
