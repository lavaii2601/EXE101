import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask
from werkzeug.security import generate_password_hash


_previous_debug = os.environ.get('DEBUG')
os.environ['DEBUG'] = 'true'

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'web', 'backend')
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from routes import auth  # noqa: E402

if _previous_debug is None:
    os.environ.pop('DEBUG', None)
else:
    os.environ['DEBUG'] = _previous_debug


class ForgotPasswordTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='forgot-password-test-secret')
        self.app.register_blueprint(auth.auth_bp)
        self.client = self.app.test_client()

    def test_returns_generic_success_for_an_unknown_email(self):
        with (
            patch.object(auth.User, 'get_by_email', return_value=None),
            patch.object(auth, 'send_password_reset_email') as send_mock,
        ):
            response = self.client.post('/api/auth/forgot-password', json={'email': 'nobody@example.com'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        send_mock.assert_not_called()

    def test_sends_an_email_and_returns_the_same_generic_response_for_a_known_account(self):
        account = {
            'user_id': 'local_test_user',
            'email': 'user@example.com',
            'password_hash': generate_password_hash('oldpassword1'),
        }
        with (
            patch.object(auth.User, 'get_by_email', return_value=account),
            patch.object(auth, 'send_password_reset_email') as send_mock,
        ):
            response = self.client.post('/api/auth/forgot-password', json={'email': 'USER@example.com'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        send_mock.assert_called_once()
        self.assertEqual(send_mock.call_args[0][0], 'user@example.com')

    def test_skips_sending_for_a_google_only_account_with_no_password(self):
        account = {'user_id': 'local_test_user', 'email': 'user@example.com', 'password_hash': None}
        with (
            patch.object(auth.User, 'get_by_email', return_value=account),
            patch.object(auth, 'send_password_reset_email') as send_mock,
        ):
            response = self.client.post('/api/auth/forgot-password', json={'email': 'user@example.com'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        send_mock.assert_not_called()

    def test_reset_rejects_a_garbage_token(self):
        response = self.client.post(
            '/api/auth/reset-password',
            json={'token': 'not-a-real-token', 'password': 'newpassword1'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error'], 'invalid_or_expired_token')

    def test_reset_rejects_weak_password(self):
        response = self.client.post(
            '/api/auth/reset-password',
            json={'token': 'whatever', 'password': 'short'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error'], 'weak_password')

    def test_reset_succeeds_updates_password_and_bumps_token_version(self):
        old_hash = generate_password_hash('oldpassword1')
        account = {'user_id': 'local_test_user', 'password_hash': old_hash}
        with self.app.test_request_context():
            token = auth.issue_password_reset_token('local_test_user', old_hash)

        with (
            patch.object(auth.User, 'get', return_value=account),
            patch.object(auth.User, 'update') as update_mock,
            patch.object(auth.User, 'increment_token_version') as bump_mock,
        ):
            response = self.client.post(
                '/api/auth/reset-password',
                json={'token': token, 'password': 'brandnewpass1'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        update_mock.assert_called_once()
        self.assertEqual(update_mock.call_args.args[0], 'local_test_user')
        bump_mock.assert_called_once_with('local_test_user')

    def test_reset_rejects_a_replayed_token_after_the_password_already_changed(self):
        # The token embeds a stamp of password_hash at issue time instead of
        # using a separate single-use token table -- once a reset actually
        # succeeds and password_hash changes, replaying the same link must
        # fail rather than silently resetting to an older, already-used link.
        old_hash = generate_password_hash('oldpassword1')
        new_hash = generate_password_hash('alreadychangedpass1')
        with self.app.test_request_context():
            token = auth.issue_password_reset_token('local_test_user', old_hash)

        with patch.object(auth.User, 'get', return_value={'user_id': 'local_test_user', 'password_hash': new_hash}):
            response = self.client.post(
                '/api/auth/reset-password',
                json={'token': token, 'password': 'anothernewpass1'},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error'], 'invalid_or_expired_token')


if __name__ == '__main__':
    unittest.main()
