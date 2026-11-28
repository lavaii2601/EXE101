import os
import sys
import unittest

from flask import Flask, jsonify, session


BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'web', 'backend')
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from utils import security as security_module  # noqa: E402
from utils.security import enforce_rate_limit  # noqa: E402


class RateLimitIdentityTests(unittest.TestCase):
    """enforce_rate_limit() used to key its bucket on bearer/header/IP only,
    never the cookie-session identity that every browser login actually
    uses -- so two different logged-in users sharing one IP (office NAT,
    school network, CGNAT) shared one bucket, and a user could evade their
    own limit just by switching networks. Fixed by keying on
    authenticated_user_id(), which does consult the session."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='test', RATE_LIMIT_PER_MINUTE=2)

        @self.app.route('/probe')
        def probe():
            limited = enforce_rate_limit()
            if limited:
                return jsonify(limited[0]), limited[1]
            return jsonify({'ok': True})

        self.client = self.app.test_client()

    def _login_as(self, user_id):
        with self.client.session_transaction() as flask_session:
            flask_session['user_id'] = user_id

    def test_two_session_users_behind_the_same_ip_do_not_share_a_bucket(self):
        # Same test client -> same remote_addr for every request. Exhaust
        # alice's 2-request limit, then confirm bob (a different session
        # identity, same "IP") is unaffected.
        self._login_as('alice')
        self.assertEqual(200, self.client.get('/probe').status_code)
        self.assertEqual(200, self.client.get('/probe').status_code)
        self.assertEqual(429, self.client.get('/probe').status_code)

        self._login_as('bob')
        self.assertEqual(200, self.client.get('/probe').status_code)

    def test_unauthenticated_requests_still_fall_back_to_ip(self):
        # No session identity at all -- still rate-limited (by IP), not
        # exempted entirely.
        self.assertEqual(200, self.client.get('/probe').status_code)
        self.assertEqual(200, self.client.get('/probe').status_code)
        self.assertEqual(429, self.client.get('/probe').status_code)


class LoginRateLimitTests(unittest.TestCase):
    """/api/auth/login and /api/auth/register used to fall through to the
    generic 180/min default, letting one IP brute-force a password at that
    rate. Fixed by capping both at LOGIN_RATE_LIMIT_PER_MINUTE."""

    def setUp(self):
        # /api/auth/login and /api/auth/register are real routes other test
        # files also hit through the real app (e.g. test_admin_security.py,
        # test_password_auth_parity.py). enforce_rate_limit()'s bucket is a
        # module-level global keyed only on (identity, path), shared by every
        # Flask app in the process -- without clearing it here, an earlier
        # test's calls to these same paths count against this test's limit.
        security_module._request_buckets.clear()
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True, SECRET_KEY='test', RATE_LIMIT_PER_MINUTE=180,
            LOGIN_RATE_LIMIT_PER_MINUTE=2,
        )

        @self.app.route('/api/auth/login')
        def login_probe():
            limited = enforce_rate_limit()
            if limited:
                return jsonify(limited[0]), limited[1]
            return jsonify({'ok': True})

        @self.app.route('/api/auth/register')
        def register_probe():
            limited = enforce_rate_limit()
            if limited:
                return jsonify(limited[0]), limited[1]
            return jsonify({'ok': True})

        self.client = self.app.test_client()

    def test_login_is_capped_below_the_generic_default(self):
        self.assertEqual(200, self.client.get('/api/auth/login').status_code)
        self.assertEqual(200, self.client.get('/api/auth/login').status_code)
        self.assertEqual(429, self.client.get('/api/auth/login').status_code)

    def test_register_is_capped_below_the_generic_default(self):
        self.assertEqual(200, self.client.get('/api/auth/register').status_code)
        self.assertEqual(200, self.client.get('/api/auth/register').status_code)
        self.assertEqual(429, self.client.get('/api/auth/register').status_code)


if __name__ == '__main__':
    unittest.main()
