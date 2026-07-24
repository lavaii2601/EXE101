import os
import pickle
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from google.oauth2.credentials import Credentials


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / 'web' / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

from utils import user_context  # noqa: E402
from utils.google_service_cache import get_cached_service  # noqa: E402


def _token_info(token):
    return {
        'token': token,
        'refresh_token': 'refresh-token',
        'token_uri': 'https://oauth2.googleapis.com/token',
        'client_id': 'client-id',
        'client_secret': 'client-secret',
        'scopes': ['scope-a'],
    }


def _token_row(token, updated_at, revoked_at=None):
    return {
        'token_json': _token_info(token),
        'scopes': ['scope-a'],
        'updated_at': updated_at,
        'revoked_at': revoked_at,
    }


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, state):
        self.state = state

    def execute(self, sql, params=None):
        statement = ' '.join(sql.split()).upper()
        if statement.startswith('SELECT'):
            self.state['select_count'] = self.state.get('select_count', 0) + 1
            error = self.state.get('select_error')
            if error:
                raise error
            return _Result(self.state.get('row'))
        if statement.startswith('INSERT INTO OAUTH_TOKENS'):
            error = self.state.get('persist_error')
            if error:
                raise error
            token_info = params[2]
            self.state['revision'] = self.state.get('revision', 0) + 1
            self.state['row'] = {
                'token_json': token_info,
                'scopes': list(params[3] or []),
                'updated_at': f"persist-{self.state['revision']}",
                'revoked_at': None,
            }
            return _Result(self.state['row'])
        if statement.startswith('UPDATE OAUTH_TOKENS'):
            error = self.state.get('delete_error')
            if error:
                raise error
            row = self.state.get('row')
            if row:
                row = dict(row)
                row['revoked_at'] = 'revoked-now'
                self.state['row'] = row
            return _Result(row)
        raise AssertionError(f'Unexpected SQL: {statement}')


class _ConnectionContext:
    def __init__(self, state):
        self.connection = _Connection(state)

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, traceback):
        return False


class _FakeService:
    def __init__(self, name):
        self.name = name
        self.service = object()


class GoogleCredentialCoherenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_token = os.path.join(self.temp_dir.name, 'gmail_token.pickle')
        self.config_patch = patch.object(
            user_context.Config,
            'GMAIL_TOKEN_FILE',
            self.base_token,
        )
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        user_context._credential_versions.clear()

    def _postgres(self, state):
        return (
            patch.object(user_context.pg, 'enabled', return_value=True),
            patch.object(
                user_context.pg,
                'connection',
                side_effect=lambda: _ConnectionContext(state),
            ),
        )

    def _token_file(self):
        return user_context._user_token_path('worker@example.com')

    def test_every_acquisition_checks_postgres_without_rebuilding_unchanged_cache(self):
        state = {'row': _token_row('token-v1', 'revision-1')}
        enabled, connection = self._postgres(state)
        with enabled, connection:
            token_file = user_context.get_user_token_file('worker@example.com')
            first = get_cached_service(
                token_file,
                lambda: _FakeService('first'),
                service_kind='gmail',
            )
            user_context.get_user_token_file('worker@example.com')
            second = get_cached_service(
                token_file,
                lambda: _FakeService('second'),
                service_kind='gmail',
            )

        self.assertEqual(state['select_count'], 2)
        self.assertIs(second, first)
        with open(token_file, 'rb') as token:
            self.assertEqual(pickle.load(token).token, 'token-v1')

    def test_cross_worker_token_update_rewrites_pickle_and_evicts_services(self):
        state = {'row': _token_row('token-v1', 'revision-1')}
        enabled, connection = self._postgres(state)
        with enabled, connection:
            token_file = user_context.get_user_token_file('worker@example.com')
            first_service = get_cached_service(
                token_file,
                lambda: _FakeService('old'),
                service_kind='gmail',
            )

            state['row'] = _token_row('token-v2', 'revision-2')
            user_context.get_user_token_file('worker@example.com')
            next_service = get_cached_service(
                token_file,
                lambda: _FakeService('new'),
                service_kind='gmail',
            )

        with open(token_file, 'rb') as token:
            self.assertEqual(pickle.load(token).token, 'token-v2')
        self.assertIsNot(next_service, first_service)
        self.assertEqual(next_service.name, 'new')

    def test_cross_worker_revocation_removes_pickle_and_evicts_services(self):
        state = {'row': _token_row('token-v1', 'revision-1')}
        enabled, connection = self._postgres(state)
        with enabled, connection:
            token_file = user_context.get_user_token_file('worker@example.com')
            get_cached_service(
                token_file,
                lambda: _FakeService('old'),
                service_kind='calendar',
            )

            state['row'] = _token_row(
                'token-v1',
                'revision-2',
                revoked_at='revoked-now',
            )
            user_context.get_user_token_file('worker@example.com')
            replacement = get_cached_service(
                token_file,
                lambda: _FakeService('must-not-build'),
                service_kind='calendar',
            )

        self.assertFalse(os.path.exists(token_file))
        self.assertIsNone(replacement)

    def test_database_read_failure_discards_stale_local_token_and_fails_closed(self):
        state = {'row': _token_row('token-v1', 'revision-1')}
        enabled, connection = self._postgres(state)
        with enabled, connection:
            token_file = user_context.get_user_token_file('worker@example.com')
            self.assertTrue(os.path.exists(token_file))
            state['select_error'] = RuntimeError('database unavailable')

            with self.assertRaises(user_context.CredentialStoreError):
                user_context.get_user_token_file('worker@example.com')

        self.assertFalse(os.path.exists(token_file))

    def test_inspection_reports_store_failure_without_using_stale_pickle(self):
        state = {'row': _token_row('token-v1', 'revision-1')}
        enabled, connection = self._postgres(state)
        with enabled, connection:
            token_file = user_context.get_user_token_file('worker@example.com')
            state['select_error'] = RuntimeError('database unavailable')
            status = user_context.inspect_google_credentials('worker@example.com')

        self.assertEqual(status['error'], 'credential_store_unavailable')
        self.assertFalse(status['has_token'])
        self.assertFalse(status['valid'])
        self.assertFalse(os.path.exists(token_file))

    def test_persist_updates_authority_and_invalidates_cached_service(self):
        state = {'row': _token_row('old-token', 'revision-1')}
        credentials = Credentials(**_token_info('new-token'))
        enabled, connection = self._postgres(state)
        with (
            enabled,
            connection,
            patch.object(user_context.pg, 'ensure_user'),
            patch.object(user_context.pg, 'json_value', side_effect=lambda value: value),
        ):
            token_file = user_context.get_user_token_file('worker@example.com')
            old_service = get_cached_service(
                token_file,
                lambda: _FakeService('old'),
                service_kind='gmail',
            )
            user_context.persist_google_credentials(
                'worker@example.com',
                credentials,
                account_email='worker@example.com',
            )
            new_service = get_cached_service(
                token_file,
                lambda: _FakeService('new'),
                service_kind='gmail',
            )

        self.assertEqual(state['row']['token_json']['token'], 'new-token')
        self.assertIsNot(new_service, old_service)
        with open(token_file, 'rb') as token:
            self.assertEqual(pickle.load(token).token, 'new-token')

    def test_failed_persist_cannot_leave_a_local_token(self):
        state = {
            'row': _token_row('old-token', 'revision-1'),
            'persist_error': RuntimeError('write failed'),
        }
        credentials = Credentials(**_token_info('new-token'))
        enabled, connection = self._postgres(state)
        with (
            enabled,
            connection,
            patch.object(user_context.pg, 'ensure_user'),
            patch.object(user_context.pg, 'json_value', side_effect=lambda value: value),
        ):
            token_file = user_context.get_user_token_file('worker@example.com')
            with self.assertRaises(user_context.CredentialStoreError):
                user_context.persist_google_credentials(
                    'worker@example.com',
                    credentials,
                )

        self.assertFalse(os.path.exists(token_file))

    def test_delete_revokes_authority_and_invalidates_local_cache(self):
        state = {'row': _token_row('token-v1', 'revision-1')}
        enabled, connection = self._postgres(state)
        with enabled, connection:
            token_file = user_context.get_user_token_file('worker@example.com')
            first_service = get_cached_service(
                token_file,
                lambda: _FakeService('old'),
                service_kind='gmail',
            )
            user_context.delete_google_credentials('worker@example.com')

        self.assertIsNotNone(first_service)
        self.assertEqual(state['row']['revoked_at'], 'revoked-now')
        self.assertFalse(os.path.exists(token_file))

    def test_failed_delete_still_removes_local_token_and_reports_failure(self):
        state = {
            'row': _token_row('token-v1', 'revision-1'),
            'delete_error': RuntimeError('revoke failed'),
        }
        enabled, connection = self._postgres(state)
        with enabled, connection:
            token_file = user_context.get_user_token_file('worker@example.com')
            with self.assertRaises(user_context.CredentialStoreError):
                user_context.delete_google_credentials('worker@example.com')

        self.assertFalse(os.path.exists(token_file))
        self.assertIsNone(state['row']['revoked_at'])

    def test_sqlite_mode_keeps_existing_local_only_behavior(self):
        credentials = Credentials(**_token_info('local-token'))
        with patch.object(user_context.pg, 'enabled', return_value=False):
            token_file = user_context.persist_google_credentials(
                'worker@example.com',
                credentials,
            )
            returned = user_context.get_user_token_file('worker@example.com')
            status = user_context.inspect_google_credentials('worker@example.com')

        self.assertEqual(returned, token_file)
        self.assertTrue(status['has_token'])
        self.assertTrue(status['valid'])


if __name__ == '__main__':
    unittest.main()
