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


class AdminWorkspaceDashboardTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='admin-workspace-test')
        self.app.register_blueprint(admin.admin_bp)
        self.client = self.app.test_client()

    def test_workspace_dashboard_returns_empty_shape_without_postgres(self):
        with (
            patch.object(
                admin,
                '_require_admin',
                return_value=({'identity': 'admin@example.com'}, None),
            ),
            patch.object(admin.pg, 'enabled', return_value=False),
        ):
            response = self.client.get('/api/admin/workspaces')

        payload = response.get_json()
        self.assertEqual(200, response.status_code)
        self.assertEqual('sqlite', payload['backend'])
        self.assertEqual([], payload['workspaces'])
        self.assertEqual(0, payload['summary']['business_workspaces'])
        self.assertEqual(0, payload['summary']['pending_seat_requests'])

    def test_workspace_dashboard_uses_operational_postgres_payload(self):
        dashboard = {
            'summary': {
                'business_workspaces': 1,
                'active_workspaces': 1,
                'attention_workspaces': 0,
                'active_seats': 4,
                'seat_capacity': 10,
                'pending_seat_requests': 0,
            },
            'workspaces': [{'workspace_id': 'ws-1', 'access_state': 'active'}],
        }
        with (
            patch.object(
                admin,
                '_require_admin',
                return_value=({'identity': 'admin@example.com'}, None),
            ),
            patch.object(admin.pg, 'enabled', return_value=True),
            patch.object(admin, '_postgres_workspace_dashboard', return_value=dashboard),
        ):
            response = self.client.get('/api/admin/workspaces')

        payload = response.get_json()
        self.assertEqual(200, response.status_code)
        self.assertEqual('postgres', payload['backend'])
        self.assertEqual('active', payload['workspaces'][0]['access_state'])
        self.assertEqual(4, payload['summary']['active_seats'])

    def test_admin_can_revoke_workspace_subscription_with_audit_actor(self):
        with (
            patch.object(
                admin,
                '_require_admin',
                return_value=({'identity': 'admin@example.com'}, None),
            ),
            patch.object(admin.pg, 'enabled', return_value=True),
            patch.object(admin.workspace_subscription, 'revoke', return_value=True) as revoke,
        ):
            response = self.client.post(
                '/api/admin/workspaces/ws-1/subscription/revoke',
                json={},
            )

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()['revoked'])
        revoke.assert_called_once_with(
            'ws-1',
            actor_user_id='admin@example.com',
        )


class WorkspaceAccessAlertCountsTests(unittest.TestCase):
    """Phase 6 operational alerts: reuses workspace_subscription's own
    decorated rows (access_state computed by get_access_state) rather than
    a second, independently-written threshold -- these tests exercise the
    boundary the design doc's DoD asks for (active/grace/read_only)."""

    def test_counts_grace_and_read_only_separately_from_active(self):
        rows = [
            {'id': 1, 'access_state': 'active'},
            {'id': 2, 'access_state': 'grace'},
            {'id': 3, 'access_state': 'grace'},
            {'id': 4, 'access_state': 'read_only'},
            {'id': 5, 'access_state': 'none'},
        ]
        with patch.object(admin.workspace_subscription, 'list_all_with_owner', return_value=rows):
            counts = admin._workspace_access_alert_counts()
        self.assertEqual({'workspaces_in_grace': 2, 'workspaces_read_only': 1}, counts)

    def test_zero_counts_when_nothing_lapsed(self):
        rows = [{'id': 1, 'access_state': 'active'}]
        with patch.object(admin.workspace_subscription, 'list_all_with_owner', return_value=rows):
            counts = admin._workspace_access_alert_counts()
        self.assertEqual({'workspaces_in_grace': 0, 'workspaces_read_only': 0}, counts)

    def test_empty_when_no_business_workspaces_exist(self):
        with patch.object(admin.workspace_subscription, 'list_all_with_owner', return_value=[]):
            counts = admin._workspace_access_alert_counts()
        self.assertEqual({'workspaces_in_grace': 0, 'workspaces_read_only': 0}, counts)

    def test_overview_route_merges_alert_counts_into_summary(self):
        with (
            patch.object(
                admin, '_require_admin',
                return_value=({'identity': 'admin@example.com'}, None),
            ),
            patch.object(admin.pg, 'enabled', return_value=True),
            patch.object(
                admin, '_postgres_dashboard',
                return_value={
                    'summary': {'users_total': 1, 'workspaces_in_grace': 2, 'workspaces_read_only': 1},
                    'users_by_mode': [], 'activity_14d': [], 'recent_sync_jobs': [],
                    'recent_users': [], 'table_sizes': [], 'database': {},
                },
            ),
        ):
            app = Flask(__name__)
            app.config.update(TESTING=True, SECRET_KEY='overview-test')
            app.register_blueprint(admin.admin_bp)
            response = app.test_client().get('/api/admin/overview')
        payload = response.get_json()
        self.assertEqual(200, response.status_code)
        self.assertEqual(2, payload['summary']['workspaces_in_grace'])
        self.assertEqual(1, payload['summary']['workspaces_read_only'])


if __name__ == '__main__':
    unittest.main()
