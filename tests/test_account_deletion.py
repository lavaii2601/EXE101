import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from flask import Flask, session


BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'web', 'backend')
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from config import Config  # noqa: E402
from models.user import User  # noqa: E402
from routes import user as user_route  # noqa: E402
from services import account_deletion_service  # noqa: E402
from utils.security import active_authenticated_user_id, issue_mobile_token  # noqa: E402
from utils.user_context import get_user_db_path  # noqa: E402


class _Result:
    def __init__(self, *, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _PostgresConnection:
    def __init__(self):
        self.queries = []
        self.replacements = {
            'workspace-with-team': {'user_id': 'admin-user'},
            'workspace-solo': None,
        }

    def execute(self, sql, params=()):
        normalized = ' '.join(sql.split())
        self.queries.append((normalized, params))
        if normalized.startswith('SELECT id, name FROM workspaces'):
            return _Result(rows=[
                {'id': 'workspace-with-team', 'name': 'Team'},
                {'id': 'workspace-solo', 'name': 'Solo'},
            ])
        if normalized.startswith('SELECT user_id FROM workspace_memberships'):
            return _Result(row=self.replacements[params[0]])
        if normalized.startswith('DELETE FROM users'):
            return _Result(rowcount=1)
        return _Result(rowcount=1)


class AccountDeletionServiceTests(unittest.TestCase):
    def test_postgres_transfers_shared_workspace_and_deletes_solo_workspace(self):
        connection = _PostgresConnection()

        @contextmanager
        def fake_connection():
            yield connection

        with patch.object(account_deletion_service.pg, 'connection', fake_connection):
            result = account_deletion_service._delete_postgres_account('owner-user')

        self.assertEqual(1, result['transferred_business_workspaces'])
        self.assertEqual(1, result['deleted_business_workspaces'])
        self.assertTrue(any(
            query.startswith('UPDATE workspaces SET owner_user_id')
            and params == ('admin-user', 'workspace-with-team')
            for query, params in connection.queries
        ))
        self.assertTrue(any(
            query.startswith('DELETE FROM knowledge_documents')
            for query, _params in connection.queries
        ))
        self.assertTrue(any(
            query.startswith('DELETE FROM users')
            for query, _params in connection.queries
        ))

    def test_sqlite_deletion_removes_user_record_and_private_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = os.path.join(temp_dir, 'assistant.db')
            token_path = os.path.join(temp_dir, 'gmail_token.json')
            with (
                patch.object(Config, 'DATABASE_PATH', database_path),
                patch.object(Config, 'GMAIL_TOKEN_FILE', token_path),
                patch.object(account_deletion_service.pg, 'enabled', return_value=False),
                patch.object(account_deletion_service, 'delete_google_credentials'),
            ):
                User._initialized_dbs.discard(database_path)
                User.get_or_create('delete-me', name='Delete Me', email='delete@example.com')
                private_db = get_user_db_path('delete-me')
                sqlite3.connect(private_db).close()

                result = account_deletion_service.delete_account('delete-me')

                self.assertEqual(0, result['transferred_business_workspaces'])
                self.assertFalse(os.path.exists(private_db))
                self.assertIsNone(User.get('delete-me'))
                User._initialized_dbs.discard(database_path)


class AccountDeletionRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='account-deletion-test')
        self.app.register_blueprint(user_route.user_bp)
        self.client = self.app.test_client()

    def _login(self):
        with self.client.session_transaction() as flask_session:
            flask_session['user_id'] = 'delete-me'

    def test_confirmation_is_required(self):
        self._login()
        with patch.object(user_route, 'delete_account') as delete_spy:
            response = self.client.post('/api/user/account/delete', json={})

        self.assertEqual(400, response.status_code)
        self.assertEqual('account_deletion_confirmation_required', response.get_json()['error'])
        delete_spy.assert_not_called()

    def test_confirmed_deletion_clears_session(self):
        self._login()
        deletion_result = {
            'transferred_business_workspaces': 1,
            'deleted_business_workspaces': 0,
        }
        with patch.object(user_route, 'delete_account', return_value=deletion_result) as delete_spy:
            response = self.client.post(
                '/api/user/account/delete',
                json={'confirmation': 'DELETE'},
            )

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()['success'])
        delete_spy.assert_called_once_with('delete-me')
        with self.client.session_transaction() as flask_session:
            self.assertNotIn('user_id', flask_session)

    def test_old_mobile_token_is_rejected_after_user_row_is_deleted(self):
        with self.app.app_context():
            token = issue_mobile_token('deleted-user')
        with (
            self.app.test_request_context(
                '/', headers={'Authorization': f'Bearer {token}'}
            ),
            patch('models.user.User.get', return_value=None),
        ):
            self.assertIsNone(active_authenticated_user_id())


if __name__ == '__main__':
    unittest.main()
