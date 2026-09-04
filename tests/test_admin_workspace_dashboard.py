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


if __name__ == '__main__':
    unittest.main()
