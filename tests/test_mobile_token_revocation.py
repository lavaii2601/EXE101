import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask


BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'web', 'backend')
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from config import Config  # noqa: E402
from models import postgres_db as pg  # noqa: E402
from models.user import User  # noqa: E402
import utils.security as security  # noqa: E402
from routes import auth as auth_route  # noqa: E402


class _SqliteUserTestCase(unittest.TestCase):
    """Points models.user.User's SQLite path at a throwaway temp file, per
    the pattern already used in tests/test_account_deletion.py."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, 'token_version.db')
        self.pg_patch = patch.object(pg, 'enabled', return_value=False)
        self.pg_patch.start()
        self.db_patch = patch.object(Config, 'DATABASE_PATH', self.database_path)
        self.db_patch.start()
        User._initialized_dbs.discard(self.database_path)
        User.get_or_create('token-user', name='Token User', email='token@example.com')

    def tearDown(self):
        self.db_patch.stop()
        self.pg_patch.stop()
        User._initialized_dbs.discard(self.database_path)
        self.temp_dir.cleanup()


class TokenVersionModelTests(_SqliteUserTestCase):
    def test_new_user_starts_at_version_zero(self):
        self.assertEqual(0, int(User.get('token-user').get('token_version') or 0))

    def test_increment_is_atomic_and_cumulative(self):
        User.increment_token_version('token-user')
        User.increment_token_version('token-user')
        self.assertEqual(2, int(User.get('token-user')['token_version']))


class MobileTokenVersionSecurityTests(_SqliteUserTestCase):
    def setUp(self):
        super().setUp()
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY='token-version-test-secret',
            MOBILE_TOKEN_MAX_AGE=3600,
            MOBILE_USER_HEADER_ENABLED=False,
        )

    def _issue_token(self):
        with self.app.test_request_context():
            return security.issue_mobile_token('token-user')

    def _active_id_for(self, token):
        with self.app.test_request_context(
            headers={'Authorization': f'Bearer {token}'}
        ):
            return security.active_authenticated_user_id()

    def test_freshly_issued_token_authenticates(self):
        token = self._issue_token()
        self.assertEqual('token-user', self._active_id_for(token))

    def test_token_stops_authenticating_after_version_bump(self):
        token = self._issue_token()
        User.increment_token_version('token-user')
        self.assertIsNone(self._active_id_for(token))

    def test_a_freshly_reissued_token_authenticates_after_version_bump(self):
        self._issue_token()
        User.increment_token_version('token-user')
        new_token = self._issue_token()
        self.assertEqual('token-user', self._active_id_for(new_token))

    def test_pre_migration_token_with_no_ver_field_still_authenticates(self):
        # Simulates a token signed before this field existed: no "ver" key
        # at all. Must still work against an unmigrated (token_version=0)
        # account, so shipping this change doesn't force-log-out everyone
        # holding an already-issued token.
        with self.app.test_request_context():
            legacy_token = security._serializer().dumps(
                {'sub': 'token-user', 'type': 'mobile'}
            )
        self.assertEqual('token-user', self._active_id_for(legacy_token))

    def test_cookie_session_login_is_unaffected_by_token_version(self):
        # A browser cookie session never goes through verify_mobile_token,
        # so bumping token_version (e.g. from another device) must not log
        # out this user's *current* browser tab.
        User.increment_token_version('token-user')
        with self.app.test_request_context():
            from flask import session

            session['user_id'] = 'token-user'
            self.assertEqual('token-user', security.active_authenticated_user_id())


class LogoutAllDevicesRouteTests(_SqliteUserTestCase):
    def setUp(self):
        super().setUp()
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY='logout-all-devices-test-secret',
            MOBILE_TOKEN_MAX_AGE=3600,
            MOBILE_USER_HEADER_ENABLED=False,
        )
        self.app.register_blueprint(auth_route.auth_bp)
        self.client = self.app.test_client()

    def test_requires_authentication(self):
        response = self.client.post('/api/auth/logout-all-devices')
        self.assertEqual(401, response.status_code)
        self.assertEqual('not_authenticated', response.get_json()['error'])

    def test_bumps_token_version_and_invalidates_outstanding_bearer_token(self):
        with self.app.test_request_context():
            token = security.issue_mobile_token('token-user')

        response = self.client.post(
            '/api/auth/logout-all-devices',
            headers={'Authorization': f'Bearer {token}'},
        )
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()['success'])
        self.assertEqual(1, int(User.get('token-user')['token_version']))

        # The very token used to call this endpoint must no longer work.
        with self.app.test_request_context(
            headers={'Authorization': f'Bearer {token}'}
        ):
            self.assertIsNone(security.active_authenticated_user_id())

    def test_clears_the_browser_session_too(self):
        with self.client.session_transaction() as browser_session:
            browser_session['user_id'] = 'token-user'

        response = self.client.post('/api/auth/logout-all-devices')
        self.assertEqual(200, response.status_code)
        with self.client.session_transaction() as browser_session:
            self.assertNotIn('user_id', browser_session)


if __name__ == '__main__':
    unittest.main()
