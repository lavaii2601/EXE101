import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask


BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'web', 'backend')
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from routes import admin  # noqa: E402
from routes import work_hub as work_hub_route  # noqa: E402
from models import workspace as workspace_module  # noqa: E402


class AdminAuditDashboardTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='admin-audit-test')
        self.app.register_blueprint(admin.admin_bp)
        self.client = self.app.test_client()

    def _as_admin(self):
        return patch.object(
            admin, '_require_admin',
            return_value=({'identity': 'admin@example.com'}, None),
        )

    def test_returns_empty_shape_without_postgres(self):
        with self._as_admin(), patch.object(admin.pg, 'enabled', return_value=False):
            response = self.client.get('/api/admin/workspaces/ws-1/audit')
        payload = response.get_json()
        self.assertEqual(200, response.status_code)
        self.assertEqual('sqlite', payload['backend'])
        self.assertEqual([], payload['events'])
        self.assertFalse(payload['has_more'])

    def test_surfaces_real_audit_rows(self):
        events = [
            {'id': 1, 'event_type': 'project_created', 'created_at': '2026-09-07T10:00:00+00:00'},
        ]
        with (
            self._as_admin(),
            patch.object(admin.pg, 'enabled', return_value=True),
            patch.object(admin.workspace_model, 'list_audit_events', return_value=events) as list_events,
        ):
            response = self.client.get('/api/admin/workspaces/ws-1/audit')
        payload = response.get_json()
        self.assertEqual(200, response.status_code)
        self.assertEqual('postgres', payload['backend'])
        self.assertEqual(events, payload['events'])
        self.assertFalse(payload['has_more'])
        list_events.assert_called_once_with('ws-1', limit=51, event_type=None, before=None)

    def test_paginates_using_a_next_before_cursor(self):
        # 51 rows come back for a limit=50 request -> there's a next page,
        # and the 51st (the "peek" row) is trimmed off the response.
        events = [
            {'id': i, 'event_type': 'task_updated', 'created_at': f'2026-09-0{min(i, 7)}T00:00:00+00:00'}
            for i in range(1, 52)
        ]
        with (
            self._as_admin(),
            patch.object(admin.pg, 'enabled', return_value=True),
            patch.object(admin.workspace_model, 'list_audit_events', return_value=events),
        ):
            response = self.client.get('/api/admin/workspaces/ws-1/audit')
        payload = response.get_json()
        self.assertEqual(50, len(payload['events']))
        self.assertTrue(payload['has_more'])
        self.assertEqual(payload['events'][-1]['created_at'], payload['next_before'])

    def test_event_type_filter_and_limit_are_forwarded(self):
        with (
            self._as_admin(),
            patch.object(admin.pg, 'enabled', return_value=True),
            patch.object(admin.workspace_model, 'list_audit_events', return_value=[]) as list_events,
        ):
            response = self.client.get(
                '/api/admin/workspaces/ws-1/audit?event_type=project_deleted&limit=5&before=2026-09-01',
            )
        self.assertEqual(200, response.status_code)
        list_events.assert_called_once_with(
            'ws-1', limit=6, event_type='project_deleted', before='2026-09-01',
        )

    def test_limit_is_clamped_to_the_valid_range(self):
        with (
            self._as_admin(),
            patch.object(admin.pg, 'enabled', return_value=True),
            patch.object(admin.workspace_model, 'list_audit_events', return_value=[]) as list_events,
        ):
            self.client.get('/api/admin/workspaces/ws-1/audit?limit=99999')
        list_events.assert_called_once_with('ws-1', limit=201, event_type=None, before=None)

    def test_requires_admin(self):
        with self._as_admin() as mock_require_admin:
            mock_require_admin.return_value = (None, ({'error': 'admin_totp_required'}, 403))
            response = self.client.get('/api/admin/workspaces/ws-1/audit')
        self.assertEqual(403, response.status_code)


class CorrelationIdHeaderTests(unittest.TestCase):
    """The response should always carry an X-Request-Id, whether or not the
    client sent one -- covered directly against app.py's before/after_request
    hooks via a minimal throwaway app rather than importing the real app.py
    (which requires a fully configured environment)."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='correlation-id-test')

        import re
        import uuid
        from flask import g, request as flask_request

        @self.app.before_request
        def _set_correlation_id():
            inbound = (flask_request.headers.get('X-Request-Id') or '').strip()[:100]
            g.correlation_id = inbound if re.fullmatch(r'[A-Za-z0-9._-]+', inbound or '') else uuid.uuid4().hex

        @self.app.after_request
        def _echo_correlation_id(response):
            correlation_id = getattr(g, 'correlation_id', None)
            if correlation_id:
                response.headers['X-Request-Id'] = correlation_id
            return response

        @self.app.route('/ping')
        def ping():
            return {'ok': True}

        self.client = self.app.test_client()

    def test_mints_a_correlation_id_when_none_supplied(self):
        response = self.client.get('/ping')
        self.assertIn('X-Request-Id', response.headers)
        self.assertTrue(len(response.headers['X-Request-Id']) > 0)

    def test_reuses_a_well_formed_inbound_request_id(self):
        response = self.client.get('/ping', headers={'X-Request-Id': 'trace-abc-123'})
        self.assertEqual('trace-abc-123', response.headers['X-Request-Id'])

    def test_rejects_a_malformed_inbound_request_id(self):
        response = self.client.get('/ping', headers={'X-Request-Id': 'not valid! <script>'})
        self.assertNotEqual('not valid! <script>', response.headers['X-Request-Id'])


class WorkspaceAccessDeniedLoggingTests(unittest.TestCase):
    """utils.security.log_workspace_access_denied is what routes/work_hub.py,
    sharing.py, and workspace.py all call from their shared _error_response
    shape -- exercised end to end via work_hub_bp here."""

    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(TESTING=True, SECRET_KEY='security-log-test')
        cls.app.register_blueprint(work_hub_route.work_hub_bp)

    def test_denied_dashboard_request_logs_a_security_warning(self):
        with (
            patch.object(work_hub_route, 'get_current_user_id', return_value='mallory'),
            patch.object(
                work_hub_route.workspace_model, 'resolve_context',
                side_effect=workspace_module.WorkspaceError('membership_required'),
            ),
            self.assertLogs('flowmate.security', level='WARNING') as logs,
        ):
            response = self.app.test_client().get('/api/work-hub/dashboard')
        self.assertEqual(403, response.status_code)
        self.assertTrue(any('membership_required' in line and 'mallory' in line for line in logs.output))

    def test_validation_errors_are_not_logged_as_security_events(self):
        workspace = {'id': 'ws-1', 'type': 'business'}
        membership = {'role': 'owner', 'status': 'active'}
        with (
            patch.object(work_hub_route, 'get_current_user_id', return_value='alice'),
            patch.object(work_hub_route.workspace_model, 'resolve_context', return_value=(workspace, membership)),
            patch.object(work_hub_route.workspace_subscription, 'assert_writable', return_value=None),
            patch.object(work_hub_route, 'log_workspace_access_denied') as log_denied,
        ):
            response = self.app.test_client().post('/api/projects', json={'name': ''})
        self.assertEqual(400, response.status_code)
        self.assertEqual('project_name_required', response.get_json()['error'])
        log_denied.assert_not_called()


if __name__ == '__main__':
    unittest.main()
