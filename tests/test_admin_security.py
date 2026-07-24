import os
import sys
import time
import unittest
from unittest.mock import patch


BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'web', 'backend')
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from config import Config
from routes import admin


RFC_6238_SECRET = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'


class AdminTotpTests(unittest.TestCase):
    def test_rfc_6238_sha1_vector(self):
        self.assertEqual(
            admin._totp_at(RFC_6238_SECRET, timestamp=59, digits=8),
            '94287082',
        )

    def test_totp_accepts_current_window_and_rejects_bad_format(self):
        now = 1_700_000_000
        code = admin._totp_at(RFC_6238_SECRET, timestamp=now)
        self.assertTrue(admin._verify_totp(code, RFC_6238_SECRET, timestamp=now))
        self.assertTrue(
            admin._verify_totp(code, RFC_6238_SECRET, timestamp=now + 30)
        )
        self.assertFalse(
            admin._verify_totp(code, RFC_6238_SECRET, timestamp=now + 60)
        )
        self.assertFalse(
            admin._verify_totp('12345x', RFC_6238_SECRET, timestamp=now)
        )

    def test_short_secret_is_rejected(self):
        with self.assertRaises(ValueError):
            admin._decode_totp_secret('JBSWY3DP')


class AdminRouteSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app

        cls.app = app
        cls.app.config.update(TESTING=True)

    def setUp(self):
        admin._totp_attempts.clear()

    def _client_with_google_session(self, email='admin@example.com'):
        client = self.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session['user_id'] = 'admin_example_com'
            flask_session['gmail_user_email'] = email
        return client

    def test_admin_fails_closed_without_configuration(self):
        client = self.app.test_client()
        with (
            patch.object(Config, 'ADMIN_EMAILS', set()),
            patch.object(Config, 'ADMIN_TOTP_SECRET', ''),
        ):
            response = client.get('/api/admin/overview')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()['error'], 'admin_not_configured')

    def test_profile_email_cannot_grant_admin_access(self):
        client = self.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session['user_id'] = 'ordinary_user'

        editable_profile = {
            'email': 'admin@example.com',
            'gmail_email': 'person@example.com',
            'gmail_connected': 1,
        }
        with (
            patch.object(Config, 'ADMIN_EMAILS', {'admin@example.com'}),
            patch.object(Config, 'ADMIN_TOTP_SECRET', RFC_6238_SECRET),
            patch.object(admin.User, 'get', return_value=editable_profile),
        ):
            response = client.get('/api/admin/overview')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['error'], 'admin_not_allowed')

    def test_allowlisted_google_account_still_requires_totp(self):
        client = self._client_with_google_session()
        google_user = {
            'gmail_email': 'admin@example.com',
            'gmail_connected': 1,
        }
        with (
            patch.object(Config, 'ADMIN_EMAILS', {'admin@example.com'}),
            patch.object(Config, 'ADMIN_TOTP_SECRET', RFC_6238_SECRET),
            patch.object(admin.User, 'get', return_value=google_user),
        ):
            response = client.get('/api/admin/overview')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['error'], 'admin_totp_required')

    def test_valid_totp_creates_admin_session(self):
        client = self._client_with_google_session()
        google_user = {
            'gmail_email': 'admin@example.com',
            'gmail_connected': 1,
        }
        code = admin._totp_at(RFC_6238_SECRET, timestamp=time.time())
        with (
            patch.object(Config, 'ADMIN_EMAILS', {'admin@example.com'}),
            patch.object(Config, 'ADMIN_TOTP_SECRET', RFC_6238_SECRET),
            patch.object(admin.User, 'get', return_value=google_user),
        ):
            response = client.post(
                '/api/admin/verify-totp',
                json={'code': code},
                headers={'Origin': 'http://localhost:5000'},
            )
            session_response = client.get('/api/admin/session')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['totp_verified'])
        self.assertEqual(session_response.status_code, 200)
        self.assertTrue(session_response.get_json()['totp_verified'])

    def test_admin_dashboard_redirects_to_login_shell_without_admin_session(self):
        client = self.app.test_client()
        response = client.get('/admin')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/admin/login')

    def test_admin_login_shell_is_data_free_and_public(self):
        client = self.app.test_client()
        response = client.get('/admin/login')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Server Control', response.data)

    def test_admin_dashboard_served_after_admin_verification(self):
        client = self.app.test_client()
        with patch('app._require_admin', return_value=({'identity': 'admin'}, None)):
            response = client.get('/admin')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Server Control', response.data)

    def test_finance_endpoint_fails_closed_without_admin_session(self):
        client = self.app.test_client()
        with (
            patch.object(Config, 'ADMIN_EMAILS', {'admin@example.com'}),
            patch.object(Config, 'ADMIN_TOTP_SECRET', RFC_6238_SECRET),
        ):
            response = client.get('/api/admin/finance')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.get_json()['error'],
            'admin_google_login_required',
        )

    def test_finance_endpoint_returns_currency_safe_empty_ledger(self):
        client = self._client_with_google_session()
        google_user = {
            'gmail_email': 'admin@example.com',
            'gmail_connected': 1,
        }
        with client.session_transaction() as flask_session:
            flask_session['admin_totp_user'] = 'admin_example_com'
            flask_session['admin_totp_verified_at'] = int(time.time())

        with (
            patch.object(Config, 'ADMIN_EMAILS', {'admin@example.com'}),
            patch.object(Config, 'ADMIN_TOTP_SECRET', RFC_6238_SECRET),
            patch.object(admin.User, 'get', return_value=google_user),
            patch.object(admin.pg, 'enabled', return_value=False),
        ):
            response = client.get('/api/admin/finance')

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload['finance']['has_data'])
        self.assertEqual(
            payload['finance']['currencies'][0]['currency'],
            'VND',
        )
        self.assertEqual(
            payload['finance']['currencies'][0]['net_revenue_month'],
            0,
        )


if __name__ == '__main__':
    unittest.main()
