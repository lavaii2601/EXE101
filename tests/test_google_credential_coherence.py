import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from google.oauth2.credentials import Credentials


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / 'web' / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

from utils import user_context  # noqa: E402
from utils.google_service_cache import get_cached_service  # noqa: E402


# Credentials.from_authorized_user_info() (google-auth) treats a missing
# "expiry" as "already expired" (it's designed for gcloud-style
# refresh-token-only info with no access token yet) -- a real credential
# this app persists always has one after a genuine OAuth exchange/refresh,
# so fixtures need a real future expiry to behave like production data
# instead of accidentally exercising the "always expired" branch.
_FUTURE_EXPIRY_DT = datetime.utcnow() + timedelta(hours=1)
_FUTURE_EXPIRY_ISO = _FUTURE_EXPIRY_DT.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'


def _token_info(token):
    return {
        'token': token,
        'refresh_token': 'refresh-token',
        'token_uri': 'https://oauth2.googleapis.com/token',
        'client_id': 'client-id',
        'client_secret': 'client-secret',
        'scopes': ['scope-a'],
        'expiry': _FUTURE_EXPIRY_ISO,
    }


def _credentials(token):
    """A live Credentials object with a real (non-expired) expiry -- the
    constructor wants a datetime for `expiry`, unlike to_json()'s string."""
    info = {key: value for key, value in _token_info(token).items() if key != 'expiry'}
    return Credentials(expiry=_FUTURE_EXPIRY_DT, **info)


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
        self.base_token = os.path.join(self.temp_dir.name, 'gmail_token.json')
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
        with open(token_file, 'r', encoding='utf-8') as token:
            self.assertEqual(json.load(token)['token'], 'token-v1')

    def test_cross_worker_token_update_rewrites_local_cache_and_evicts_services(self):
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

        with open(token_file, 'r', encoding='utf-8') as token:
            self.assertEqual(json.load(token)['token'], 'token-v2')
        self.assertIsNot(next_service, first_service)
        self.assertEqual(next_service.name, 'new')

    def test_cross_worker_revocation_removes_local_cache_and_evicts_services(self):
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

    def test_inspection_reports_store_failure_without_using_stale_local_cache(self):
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
        credentials = _credentials('new-token')
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
        with open(token_file, 'r', encoding='utf-8') as token:
            self.assertEqual(json.load(token)['token'], 'new-token')

    def test_failed_persist_cannot_leave_a_local_token(self):
        state = {
            'row': _token_row('old-token', 'revision-1'),
            'persist_error': RuntimeError('write failed'),
        }
        credentials = _credentials('new-token')
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
        credentials = _credentials('local-token')
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


class _FakeOAuthTokensTable:
    """A real (if tiny) in-memory stand-in for the oauth_tokens table,
    supporting the exact query shapes persist_google_credentials/
    list_google_accounts/activate_google_account/delete_google_credentials/
    _restore_google_credentials_from_db actually issue. Unlike
    GoogleCredentialCoherenceTests' single-row _Connection above, the
    multi-account functions need real multi-row SELECT/UPDATE semantics,
    so this executes against a genuine list of row dicts rather than one
    mutable slot."""

    def __init__(self):
        self.rows = []
        self._next_id = 1

    def _matching(self, user_id, account_email=None, active_only=False, include_revoked=False):
        for row in self.rows:
            if row['user_id'] != user_id or row['provider'] != 'google':
                continue
            if not include_revoked and row['revoked_at'] is not None:
                continue
            if account_email is not None and row['account_email'] != account_email:
                continue
            if active_only and not row['is_active']:
                continue
            yield row


class _MultiAccountConnection:
    def __init__(self, table):
        self.table = table

    def execute(self, sql, params=None):
        statement = ' '.join(sql.split()).upper()
        params = params or ()

        if statement.startswith('SELECT ACCOUNT_EMAIL, ACCOUNT_NAME'):
            # list_google_accounts
            user_id = params[0]
            rows = sorted(
                self.table._matching(user_id),
                key=lambda r: (not r['is_active'], -r['updated_at']),
            )
            return _ListResult([dict(r) for r in rows])

        if statement.startswith('SELECT 1 FROM OAUTH_TOKENS'):
            # activate_google_account's existence check
            user_id, account_email = params
            match = next(self.table._matching(user_id, account_email=account_email), None)
            return _ListResult([{'?column?': 1}] if match else [])

        if statement.startswith('SELECT IS_ACTIVE FROM OAUTH_TOKENS'):
            # delete_google_credentials's was_active check
            user_id, account_email = params
            match = next(self.table._matching(user_id, account_email=account_email), None)
            return _ListResult([{'is_active': match['is_active']}] if match else [])

        if statement.startswith('SELECT ACCOUNT_EMAIL FROM OAUTH_TOKENS'):
            # persist_google_credentials resolving the active account for a
            # bare refresh call (account_email not supplied by the caller)
            user_id = params[0]
            match = next(self.table._matching(user_id, active_only=True), None)
            return _ListResult([{'account_email': match['account_email']}] if match else [])

        if statement.startswith('SELECT TOKEN_JSON, SCOPES, UPDATED_AT, REVOKED_AT'):
            # _restore_google_credentials_from_db
            user_id = params[0]
            match = next(self.table._matching(user_id, active_only=True), None)
            return _ListResult([dict(match)] if match else [])

        if statement.startswith('UPDATE OAUTH_TOKENS SET IS_ACTIVE = (ACCOUNT_EMAIL'):
            # activate_google_account's single flip-all statement
            account_email, user_id = params
            for row in self.table._matching(user_id):
                row['is_active'] = row['account_email'] == account_email
            return _ListResult([])

        if statement.startswith('UPDATE OAUTH_TOKENS SET IS_ACTIVE = FALSE'):
            # persist_google_credentials deactivating every sibling account
            user_id, keep_email = params
            for row in self.table._matching(user_id):
                if row['account_email'] != keep_email:
                    row['is_active'] = False
            return _ListResult([])

        if statement.startswith('UPDATE OAUTH_TOKENS SET REVOKED_AT = NOW(), IS_ACTIVE = FALSE'):
            if len(params) == 2:
                user_id, account_email = params
            else:
                (user_id,), account_email = params, None
            for row in self.table._matching(user_id, account_email=account_email):
                row['revoked_at'] = 'revoked-now'
                row['is_active'] = False
            return _ListResult([])

        if statement.startswith('UPDATE OAUTH_TOKENS SET IS_ACTIVE = TRUE WHERE ID'):
            # delete_google_credentials auto-promoting a replacement
            (user_id,) = params
            candidates = sorted(
                self.table._matching(user_id), key=lambda r: r['updated_at'], reverse=True,
            )
            if candidates:
                candidates[0]['is_active'] = True
            return _ListResult([])

        if statement.startswith('INSERT INTO OAUTH_TOKENS'):
            (user_id, account_email, token_json, scopes, expires_at,
             account_name, account_picture) = params
            existing = next(self.table._matching(user_id, account_email=account_email, include_revoked=True), None)
            if existing:
                existing.update(
                    token_json=token_json, scopes=list(scopes or []), expires_at=expires_at,
                    revoked_at=None, is_active=True,
                    account_name=account_name or existing.get('account_name'),
                    account_picture=account_picture or existing.get('account_picture'),
                    updated_at=existing['updated_at'] + 1,
                )
                row = existing
            else:
                row = {
                    'id': self.table._next_id, 'user_id': user_id, 'provider': 'google',
                    'account_email': account_email, 'account_name': account_name,
                    'account_picture': account_picture, 'token_json': token_json,
                    'scopes': list(scopes or []), 'expires_at': expires_at,
                    'revoked_at': None, 'is_active': True, 'updated_at': self.table._next_id,
                }
                self.table._next_id += 1
                self.table.rows.append(row)
            return _ListResult([dict(row)])

        raise AssertionError(f'Unexpected SQL: {statement}')


class _ListResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class _MultiAccountConnectionContext:
    def __init__(self, table):
        self.table = table

    def __enter__(self):
        return _MultiAccountConnection(self.table)

    def __exit__(self, exc_type, exc, traceback):
        return False


class MultiAccountLinkingTests(unittest.TestCase):
    """Exercises the real list_google_accounts/activate_google_account/
    delete_google_credentials/persist_google_credentials functions through
    a full link-two-accounts/switch/unlink lifecycle -- the "Verify" item
    from the multi-account plan that never got its own test."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_patch = patch.object(
            user_context.Config, 'GMAIL_TOKEN_FILE',
            os.path.join(self.temp_dir.name, 'gmail_token.json'),
        )
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        user_context._credential_versions.clear()

        self.table = _FakeOAuthTokensTable()
        self.enabled_patch = patch.object(user_context.pg, 'enabled', return_value=True)
        self.connection_patch = patch.object(
            user_context.pg, 'connection',
            side_effect=lambda: _MultiAccountConnectionContext(self.table),
        )
        self.ensure_user_patch = patch.object(user_context.pg, 'ensure_user')
        self.json_value_patch = patch.object(user_context.pg, 'json_value', side_effect=lambda v: v)
        for p in (self.enabled_patch, self.connection_patch, self.ensure_user_patch, self.json_value_patch):
            p.start()
            self.addCleanup(p.stop)

    def _link(self, user_id, account_email, name='', picture=''):
        user_context.persist_google_credentials(
            user_id, _credentials(f'token-{account_email}'),
            account_email=account_email, account_name=name, account_picture=picture,
        )

    def test_linking_a_second_account_becomes_the_new_active_slot(self):
        self._link('worker@example.com', 'a@gmail.com', name='Account A')
        self._link('worker@example.com', 'b@gmail.com', name='Account B')

        accounts = user_context.list_google_accounts('worker@example.com')

        self.assertEqual(len(accounts), 2)
        active = [a for a in accounts if a['is_active']]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]['account_email'], 'b@gmail.com')
        # Linking B must not have erased A from the list, just deactivated it.
        self.assertIn('a@gmail.com', {a['account_email'] for a in accounts})

    def test_activate_switches_the_active_slot_and_restores_local_cache(self):
        self._link('worker@example.com', 'a@gmail.com')
        self._link('worker@example.com', 'b@gmail.com')

        token_file = user_context.activate_google_account('worker@example.com', 'a@gmail.com')

        accounts = {a['account_email']: a['is_active'] for a in user_context.list_google_accounts('worker@example.com')}
        self.assertEqual(accounts, {'a@gmail.com': True, 'b@gmail.com': False})
        with open(token_file, 'r', encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['token'], 'token-a@gmail.com')

    def test_activate_rejects_an_email_that_was_never_linked(self):
        self._link('worker@example.com', 'a@gmail.com')

        with self.assertRaises(user_context.CredentialStoreError):
            user_context.activate_google_account('worker@example.com', 'never-linked@gmail.com')

    def test_unlinking_the_active_account_promotes_the_other_one(self):
        self._link('worker@example.com', 'a@gmail.com')
        self._link('worker@example.com', 'b@gmail.com')  # b becomes active

        user_context.delete_google_credentials('worker@example.com', account_email='b@gmail.com')

        accounts = user_context.list_google_accounts('worker@example.com')
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]['account_email'], 'a@gmail.com')
        self.assertTrue(accounts[0]['is_active'])

    def test_unlinking_the_last_account_leaves_an_empty_list(self):
        self._link('worker@example.com', 'a@gmail.com')

        user_context.delete_google_credentials('worker@example.com', account_email='a@gmail.com')

        self.assertEqual(user_context.list_google_accounts('worker@example.com'), [])

    def test_accounts_from_a_different_user_never_cross_over(self):
        self._link('alice@example.com', 'alice-work@gmail.com')
        self._link('bob@example.com', 'bob-work@gmail.com')

        alice_accounts = user_context.list_google_accounts('alice@example.com')

        self.assertEqual(len(alice_accounts), 1)
        self.assertEqual(alice_accounts[0]['account_email'], 'alice-work@gmail.com')


if __name__ == '__main__':
    unittest.main()
