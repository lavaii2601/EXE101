import glob
import os
import sys
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

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

from config import Config
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

    def test_login_hashes_dummy_password_even_for_unknown_email(self):
        # Login used to short-circuit on `not user` before ever calling
        # check_password_hash, so "no such account" returned after only a
        # fast DB lookup while "wrong password" paid for the deliberately
        # slow hash comparison -- a timing side-channel for enumerating
        # registered emails despite the identical error message/status.
        # Assert the (slow) comparison now always runs.
        with (
            patch.object(auth.User, 'get_by_email', return_value=None),
            patch.object(auth, 'check_password_hash', wraps=auth.check_password_hash) as spy,
        ):
            response = self.client.post(
                '/api/auth/login',
                json={'email': 'nobody@example.com', 'password': 'whatever123'},
            )

        self.assertEqual(response.status_code, 401)
        spy.assert_called_once_with(auth._DUMMY_PASSWORD_HASH, 'whatever123')

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

    def test_set_password_requires_an_authenticated_session(self):
        response = self.client.post('/api/auth/set-password', json={'password': 'brandnewpass1'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()['error'], 'not_authenticated')

    def test_set_password_rejects_an_account_that_already_has_one(self):
        with self.client.session_transaction() as browser_session:
            browser_session['user_id'] = 'local_test_user'

        account = {'user_id': 'local_test_user', 'password_hash': generate_password_hash('existing')}
        with patch.object(auth.User, 'get', return_value=account):
            response = self.client.post('/api/auth/set-password', json={'password': 'brandnewpass1'})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()['error'], 'password_already_set')

    def test_set_password_rejects_a_weak_password(self):
        with self.client.session_transaction() as browser_session:
            browser_session['user_id'] = 'local_test_user'

        account = {'user_id': 'local_test_user', 'password_hash': None}
        with patch.object(auth.User, 'get', return_value=account):
            response = self.client.post('/api/auth/set-password', json={'password': 'short'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error'], 'weak_password')

    def test_set_password_succeeds_for_a_recovered_google_only_account(self):
        with self.client.session_transaction() as browser_session:
            browser_session['user_id'] = 'local_test_user'

        account = {'user_id': 'local_test_user', 'password_hash': None}
        with (
            patch.object(auth.User, 'get', return_value=account),
            patch.object(auth.User, 'update') as update,
        ):
            response = self.client.post('/api/auth/set-password', json={'password': 'brandnewpass1'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        update.assert_called_once()
        self.assertEqual('local_test_user', update.call_args.args[0])
        self.assertIn('password_hash', update.call_args.kwargs)

    def test_set_password_backfills_email_from_gmail_when_blank(self):
        """intent=recover already proved this account owns gmail_email (see
        lookup_google_identity_owner), so using it as the login email here
        needs no separate step from the user -- and never overwrites an
        email the account already has."""
        with self.client.session_transaction() as browser_session:
            browser_session['user_id'] = 'local_test_user'

        account = {
            'user_id': 'local_test_user',
            'password_hash': None,
            'email': '',
            'gmail_email': 'Recovered@Gmail.com',
        }
        with (
            patch.object(auth.User, 'get', return_value=account),
            patch.object(auth.User, 'update') as update,
        ):
            response = self.client.post('/api/auth/set-password', json={'password': 'brandnewpass1'})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['email'], 'recovered@gmail.com')
        self.assertEqual(update.call_args.kwargs.get('email'), 'recovered@gmail.com')

    def test_set_password_never_overwrites_an_existing_email(self):
        with self.client.session_transaction() as browser_session:
            browser_session['user_id'] = 'local_test_user'

        account = {
            'user_id': 'local_test_user',
            'password_hash': None,
            'email': 'already-set@example.com',
            'gmail_email': 'other@gmail.com',
        }
        with (
            patch.object(auth.User, 'get', return_value=account),
            patch.object(auth.User, 'update') as update,
        ):
            response = self.client.post('/api/auth/set-password', json={'password': 'brandnewpass1'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['email'], 'already-set@example.com')
        self.assertNotIn('email', update.call_args.kwargs)

    def test_gmail_disconnect_keeps_the_app_session(self):
        with self.client.session_transaction() as browser_session:
            browser_session['user_id'] = 'local_test_user'

        with (
            patch.object(email.oauth, 'get_user_token_file', return_value=os.path.join(os.devnull, 'missing-token.json')),
            patch.object(email.User, 'update'),
            patch.object(email.oauth, '_clear_oauth_state'),
        ):
            response = self.client.post('/api/email/logout')

        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as browser_session:
            self.assertEqual(browser_session['user_id'], 'local_test_user')


class UserModelDuplicateEmailRowTests(unittest.TestCase):
    """A handful of real accounts have two rows for the same address -- an
    old build could create both the raw-email user_id and the sanitized one
    for the same Google account (see utils/user_context.py's
    resolve_google_user_id). get_by_email used to always take the oldest
    matching row; when that older row is a password-less leftover and the
    password was set on the newer sanitized one, login kept resolving to the
    wrong row and a freshly-set password looked like it silently didn't
    work -- this reproduces that exact scenario against a real SQLite DB."""

    def setUp(self):
        import tempfile
        from models.user import User

        self.User = User
        self.tmpdir = tempfile.mkdtemp()
        self._original_db_path = Config.DATABASE_PATH
        Config.DATABASE_PATH = os.path.join(self.tmpdir, 'duplicate_rows_test.db')
        User._initialized_dbs.discard(Config.DATABASE_PATH)

    def tearDown(self):
        Config.DATABASE_PATH = self._original_db_path
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_by_email_prefers_the_row_with_a_password_over_the_older_one(self):
        email = 'duplicate.legacy@gmail.com'
        self.User.get_or_create('duplicate.legacy@gmail.com', name='Older raw-id row', email=email)
        self.User.get_or_create('duplicate_legacy_gmail_com', name='Newer sanitized row', email=email)
        self.User.update('duplicate_legacy_gmail_com', password_hash=generate_password_hash('brandnewpass1'))

        resolved = self.User.get_by_email(email)

        self.assertEqual(resolved['user_id'], 'duplicate_legacy_gmail_com')
        self.assertIsNotNone(resolved['password_hash'])


class PasswordAuthFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(PROJECT_ROOT, 'web', 'frontend', 'index.html'), encoding='utf-8') as handle:
            cls.html = handle.read()
        # app.js was split into per-feature files (web/frontend/js/*.js) --
        # concatenate them all so substring assertions below still work
        # regardless of which file now holds the matching code.
        js_dir = os.path.join(PROJECT_ROOT, 'web', 'frontend', 'js')
        cls.javascript = ''.join(
            open(path, encoding='utf-8').read()
            for path in sorted(glob.glob(os.path.join(js_dir, '*.js')))
        )

    def test_web_login_gate_is_password_only_with_a_google_recovery_bridge(self):
        for element_id in (
            'appAuthForm',
            'authNameInput',
            'authEmailInput',
            'authPasswordInput',
            'authModeToggle',
            'authRecoverGoogleBtn',
            'setPasswordModal',
            'setPasswordInput',
        ):
            self.assertIn(f'id="{element_id}"', self.html)
        self.assertIn("/auth/${isSignup ? 'register' : 'login'}", self.javascript)
        # Google OAuth is no longer offered as a login button on the gate --
        # only the password form plus the one-time recovery link.
        self.assertNotIn('id="authGateLoginBtn"', self.html)
        self.assertNotIn('id="authAppleLoginBtn"', self.html)
        self.assertIn("intent=link", self.javascript)
        self.assertIn("intent=recover", self.javascript)

    def test_app_session_and_google_connection_are_checked_separately(self):
        self.assertIn("fetch(`${API_BASE}/user/profile`", self.javascript)
        self.assertIn("fetch(`${API_BASE}/email/auth-status`", self.javascript)
        self.assertIn('app_authenticated: isAuthenticated', self.javascript)

    def test_app_logout_and_google_disconnect_use_distinct_endpoints(self):
        self.assertIn("apiFetch(`${API_BASE}/auth/logout`", self.javascript)
        self.assertIn("apiFetch(`${API_BASE}/email/logout`", self.javascript)


class MobileFlutterAuthContractTests(unittest.TestCase):
    def test_mobile_uses_canonical_api_host_without_post_redirect(self):
        flutter_config_path = os.path.join(
            PROJECT_ROOT, 'mobile_flutter', 'lib', 'api', 'config.dart'
        )
        react_native_config_path = os.path.join(
            PROJECT_ROOT, 'mobile', 'src', 'api', 'config.js'
        )
        with open(flutter_config_path, encoding='utf-8') as handle:
            flutter_config = handle.read()
        with open(react_native_config_path, encoding='utf-8') as handle:
            react_native_config = handle.read()

        self.assertIn(
            "const String kApiBase = 'https://www.flowmate.pro/api';",
            flutter_config,
        )
        self.assertNotIn(
            "const String kApiBase = 'https://flowmate.pro/api';",
            flutter_config,
        )
        self.assertIn(
            "const DEPLOYED_API = 'https://www.flowmate.pro/api';",
            react_native_config,
        )
        self.assertNotIn(
            "const DEPLOYED_API = 'https://flowmate.pro/api';",
            react_native_config,
        )

    def test_release_manifest_allows_api_network_access(self):
        manifest_path = os.path.join(
            PROJECT_ROOT,
            'mobile_flutter',
            'android',
            'app',
            'src',
            'main',
            'AndroidManifest.xml',
        )
        manifest = ElementTree.parse(manifest_path).getroot()
        android_name = '{http://schemas.android.com/apk/res/android}name'
        permissions = {
            element.attrib.get(android_name)
            for element in manifest.findall('uses-permission')
        }

        self.assertIn('android.permission.INTERNET', permissions)


if __name__ == '__main__':
    unittest.main()
