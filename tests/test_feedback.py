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

from routes import feedback  # noqa: E402


class FeedbackSubmitTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='feedback-test-secret')
        self.app.register_blueprint(feedback.feedback_bp)
        self.client = self.app.test_client()

    def test_rejects_an_unauthenticated_submission(self):
        response = self.client.post('/api/feedback', json={'message': 'Hello'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()['error'], 'not_authenticated')

    def test_rejects_an_empty_or_whitespace_only_message(self):
        with self.client.session_transaction() as flask_session:
            flask_session['user_id'] = 'local_test_user'
        response = self.client.post('/api/feedback', json={'message': '   '})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error'], 'empty_message')

    def test_rejects_a_message_over_the_length_cap(self):
        with self.client.session_transaction() as flask_session:
            flask_session['user_id'] = 'local_test_user'
        response = self.client.post('/api/feedback', json={'message': 'x' * 2001})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error'], 'message_too_long')

    def test_submits_feedback_and_calls_the_model_with_the_trimmed_message(self):
        with self.client.session_transaction() as flask_session:
            flask_session['user_id'] = 'local_test_user'
        with patch.object(feedback.feedback_model, 'create') as create_mock:
            response = self.client.post('/api/feedback', json={'message': '  Great app!  '})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        create_mock.assert_called_once_with('local_test_user', 'Great app!')


class AdminFeedbackListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app

        cls.app = app
        cls.app.config.update(TESTING=True)

    def test_rejects_a_non_admin_request(self):
        from config import Config

        client = self.app.test_client()
        with patch.object(Config, 'ADMIN_EMAILS', {'admin@example.com'}):
            response = client.get('/api/admin/feedback')
        self.assertEqual(response.status_code, 401)

    def test_returns_the_feedback_list_for_a_real_admin(self):
        from routes import admin

        client = self.app.test_client()
        with (
            patch.object(admin, '_require_admin', return_value=({'identity': 'admin_user'}, None)),
            patch.object(admin, 'pg') as pg_mock,
            patch.object(admin.feedback_model, 'list_recent', return_value=[{'user_id': 'u1', 'message': 'hi'}]),
        ):
            pg_mock.enabled.return_value = True
            response = client.get('/api/admin/feedback')

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['feedback'], [{'user_id': 'u1', 'message': 'hi'}])


if __name__ == '__main__':
    unittest.main()
