import os
import sys
import unittest

from flask import Flask, jsonify, session


BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'web', 'backend')
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

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


if __name__ == '__main__':
    unittest.main()
