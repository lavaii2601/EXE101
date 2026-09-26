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
from routes import email


RFC_6238_SECRET = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'


class AdminTotpTests(unittest.TestCase):
    def test_rfc_6238_sha1_vector(self):
        self.assertEqual(
            admin._totp_at(RFC_6238_SECRET, timestamp=59, digits=8),
            '94287082',
        )

    def test_totp_accepts_current_window_and_rejects_bad_format(self):
        # _verify_totp returns the matched time-step counter (not a plain
        # bool) so _consume_totp_counter can detect a replay of the same
        # code -- assert both matches resolve to the SAME counter (they're
        # the same 30s step, just checked at different offsets).
        now = 1_700_000_000
        code = admin._totp_at(RFC_6238_SECRET, timestamp=now)
        matched = admin._verify_totp(code, RFC_6238_SECRET, timestamp=now)
        self.assertIsNotNone(matched)
        self.assertEqual(
            matched,
            admin._verify_totp(code, RFC_6238_SECRET, timestamp=now + 30),
        )
        self.assertIsNone(
            admin._verify_totp(code, RFC_6238_SECRET, timestamp=now + 60)
        )
        self.assertIsNone(
            admin._verify_totp('12345x', RFC_6238_SECRET, timestamp=now)
        )

    def test_consume_totp_counter_rejects_replay_of_the_same_code(self):
        admin._totp_consumed_counters.clear()
        self.assertTrue(admin._consume_totp_counter('admin-1', 12345))
        self.assertFalse(admin._consume_totp_counter('admin-1', 12345))
        # A different user, or the next time-step, must not be blocked by
        # someone else's (or an earlier) consumed counter.
        self.assertTrue(admin._consume_totp_counter('admin-2', 12345))
        self.assertTrue(admin._consume_totp_counter('admin-1', 12346))

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
        admin._totp_consumed_counters.clear()

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

    def test_totp_rate_limit_cannot_be_bypassed_by_spoofing_x_forwarded_for(self):
        # _attempt_key used to read the client-supplied X-Forwarded-For
        # header directly (taking its attacker-controlled leftmost entry)
        # instead of request.remote_addr, which ProxyFix(x_for=1) already
        # resolves correctly. That let every attempt land in a fresh bucket
        # by sending a different fake header each time, bypassing the
        # brute-force cap entirely. Assert a spoofed header no longer helps.
        client = self._client_with_google_session()
        google_user = {'gmail_email': 'admin@example.com', 'gmail_connected': 1}
        with (
            patch.object(Config, 'ADMIN_EMAILS', {'admin@example.com'}),
            patch.object(Config, 'ADMIN_TOTP_SECRET', RFC_6238_SECRET),
            patch.object(Config, 'ADMIN_TOTP_MAX_ATTEMPTS', 3),
            patch.object(admin.User, 'get', return_value=google_user),
        ):
            # ProxyFix(x_for=1) trusts exactly one hop, taken from the
            # RIGHT of X-Forwarded-For -- that's Railway's own edge
            # appending the real observed client IP. A prepended fake
            # left-hand entry is exactly what an attacker can freely
            # inject; the real client IP (last segment) stays constant.
            for i in range(3):
                response = client.post(
                    '/api/admin/verify-totp',
                    json={'code': '000000'},
                    headers={
                        'Origin': 'http://localhost:5000',
                        'X-Forwarded-For': f'{i}.{i}.{i}.{i}, 203.0.113.50',
                    },
                )
                self.assertEqual(401, response.status_code)

            # A 4th attempt with yet another fake prefix (same real IP)
            # must now be throttled -- not land in a brand-new bucket.
            response = client.post(
                '/api/admin/verify-totp',
                json={'code': '000000'},
                headers={
                    'Origin': 'http://localhost:5000',
                    'X-Forwarded-For': '9.9.9.9, 203.0.113.50',
                },
            )
        self.assertEqual(429, response.status_code)
        self.assertEqual('admin_totp_rate_limited', response.get_json()['error'])

    def test_replayed_totp_code_is_rejected_on_second_submission(self):
        client = self._client_with_google_session()
        google_user = {'gmail_email': 'admin@example.com', 'gmail_connected': 1}
        code = admin._totp_at(RFC_6238_SECRET, timestamp=time.time())
        with (
            patch.object(Config, 'ADMIN_EMAILS', {'admin@example.com'}),
            patch.object(Config, 'ADMIN_TOTP_SECRET', RFC_6238_SECRET),
            patch.object(admin.User, 'get', return_value=google_user),
        ):
            first = client.post(
                '/api/admin/verify-totp',
                json={'code': code},
                headers={'Origin': 'http://localhost:5000'},
            )
            second = client.post(
                '/api/admin/verify-totp',
                json={'code': code},
                headers={'Origin': 'http://localhost:5000'},
            )
        self.assertEqual(200, first.status_code)
        self.assertEqual(401, second.status_code)
        self.assertEqual('admin_totp_invalid', second.get_json()['error'])

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

    def test_signed_in_non_admin_cannot_open_admin_login_shell(self):
        client = self.app.test_client()
        with (
            patch('app.authenticated_user_id', return_value='ordinary_user'),
            patch('app.is_current_user_admin', return_value=False),
        ):
            response = client.get('/admin/login')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/app')

    def test_signed_in_admin_can_open_admin_login_shell_for_totp(self):
        client = self.app.test_client()
        with (
            patch('app.authenticated_user_id', return_value='admin_user'),
            patch('app.is_current_user_admin', return_value=True),
        ):
            response = client.get('/admin/login')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Server Control', response.data)

    def test_admin_role_check_uses_trusted_google_identity(self):
        with (
            patch.object(Config, 'ADMIN_EMAILS', {'admin@example.com'}),
            patch.object(admin, 'authenticated_user_id', return_value='admin_example_com'),
            patch.object(admin, '_trusted_google_email', return_value='admin@example.com'),
        ):
            self.assertTrue(admin.is_current_user_admin())

    def test_auth_status_exposes_admin_role_from_server_allowlist(self):
        client = self._client_with_google_session()
        credential_status = {
            'token_file': os.path.join(BACKEND_DIR, 'missing-test-token.json'),
            'valid': True,
            'scopes': [],
            'has_token': True,
            'error': None,
            'refreshed': False,
        }
        with (
            patch.object(email.oauth, 'inspect_google_credentials', return_value=credential_status),
            patch.object(email.oauth, 'is_current_user_admin', return_value=True),
            patch.object(email.User, 'get', return_value={}),
        ):
            response = client.get('/api/email/auth-status')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['authenticated'])
        self.assertTrue(response.get_json()['is_admin'])

    def test_auth_status_keeps_regular_user_out_of_admin_role(self):
        client = self._client_with_google_session(email='person@example.com')
        credential_status = {
            'token_file': os.path.join(BACKEND_DIR, 'missing-test-token.json'),
            'valid': True,
            'scopes': [],
            'has_token': True,
            'error': None,
            'refreshed': False,
        }
        with (
            patch.object(email.oauth, 'inspect_google_credentials', return_value=credential_status),
            patch.object(email.oauth, 'is_current_user_admin', return_value=False),
            patch.object(email.User, 'get', return_value={}),
        ):
            response = client.get('/api/email/auth-status')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['authenticated'])
        self.assertFalse(response.get_json()['is_admin'])

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
