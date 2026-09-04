import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask, session
from werkzeug.security import generate_password_hash


# Keep this route-level suite independent from production-style values in a
# developer's environment while Config is imported.
_previous_debug = os.environ.get('DEBUG')
os.environ['DEBUG'] = 'true'

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'web', 'backend')
)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from routes import auth, email
from utils.security import authenticated_user_id

if _previous_debug is None:
    os.environ.pop('DEBUG', None)
else:
    os.environ['DEBUG'] = _previous_debug


class PasswordAuthParityTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY='password-auth-test-secret',
            MOBILE_TOKEN_MAX_AGE=3600,
        )
        self.app.register_blueprint(auth.auth_bp)
        self.app.register_blueprint(email.email_bp)
        self.client = self.app.test_client()

    def test_password_login_creates_a_browser_session(self):
        account = {
            'user_id': 'local_test_user',
            'email': 'user@example.com',
            'password_hash': generate_password_hash('password123'),
        }
        with patch.object(auth.User, 'get_by_email', return_value=account):
            response = self.client.post(
                '/api/auth/login',
                json={'email': 'USER@example.com', 'password': 'password123'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        self.assertTrue(response.get_json()['access_token'])
        with self.client.session_transaction() as browser_session:
            self.assertEqual(browser_session['user_id'], 'local_test_user')

    def test_password_registration_creates_a_browser_session(self):
        with (
            patch.object(auth.User, 'get_by_email', return_value=None),
            patch.object(auth.User, 'get_or_create'),
            patch.object(auth.User, 'update'),
        ):
            response = self.client.post(
                '/api/auth/register',
                json={
                    'name': 'Test User',
                    'email': 'new@example.com',
                    'password': 'password123',
                },
            )

        self.assertEqual(response.status_code, 200)
        user_id = response.get_json()['user_id']
        self.assertTrue(user_id.startswith('local_'))
        with self.client.session_transaction() as browser_session:
            self.assertEqual(browser_session['user_id'], user_id)

    def test_anonymous_default_sentinel_is_not_authenticated(self):
        with self.app.test_request_context('/'):
            session['user_id'] = 'default'
            self.assertIsNone(authenticated_user_id())

    def test_app_logout_clears_password_browser_session(self):
        with self.client.session_transaction() as browser_session:
            browser_session['user_id'] = 'local_test_user'

        response = self.client.post('/api/auth/logout')

        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as browser_session:
            self.assertNotIn('user_id', browser_session)

    def test_gmail_disconnect_keeps_the_app_session(self):
        with self.client.session_transaction() as browser_session:
            browser_session['user_id'] = 'local_test_user'

        with (
            patch.object(email, 'get_user_token_file', return_value=os.path.join(os.devnull, 'missing-token.pickle')),
            patch.object(email.User, 'update'),
            patch.object(email, '_clear_oauth_state'),
        ):
            response = self.client.post('/api/email/logout')

        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as browser_session:
            self.assertEqual(browser_session['user_id'], 'local_test_user')


class PasswordAuthFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(PROJECT_ROOT, 'web', 'frontend', 'index.html'), encoding='utf-8') as handle:
            cls.html = handle.read()
        with open(os.path.join(PROJECT_ROOT, 'web', 'frontend', 'js', 'app.js'), encoding='utf-8') as handle:
            cls.javascript = handle.read()

    def test_web_exposes_the_same_password_and_google_choices_as_mobile(self):
        for element_id in (
            'appAuthForm',
            'authNameInput',
            'authEmailInput',
            'authPasswordInput',
            'authGateLoginBtn',
            'authModeToggle',
        ):
            self.assertIn(f'id="{element_id}"', self.html)
        self.assertIn("/auth/${isSignup ? 'register' : 'login'}", self.javascript)

    def test_app_session_and_google_connection_are_checked_separately(self):
        self.assertIn("fetch(`${API_BASE}/user/profile`", self.javascript)
        self.assertIn("fetch(`${API_BASE}/email/auth-status`", self.javascript)
        self.assertIn('app_authenticated: isAuthenticated', self.javascript)

    def test_app_logout_and_google_disconnect_use_distinct_endpoints(self):
        self.assertIn("apiFetch(`${API_BASE}/auth/logout`", self.javascript)
        self.assertIn("apiFetch(`${API_BASE}/email/logout`", self.javascript)


if __name__ == '__main__':
    unittest.main()
