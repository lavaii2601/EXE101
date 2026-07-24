import os
import pickle
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / 'web' / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

from services.calendar_service import CalendarService  # noqa: E402
from services.gmail_service import GmailService  # noqa: E402
from utils import user_context  # noqa: E402


class _Response:
    status = 401


class _GoogleApiError(Exception):
    def __init__(self):
        super().__init__('invalid credentials')
        self.resp = _Response()


class _FailingRequest:
    def execute(self):
        raise _GoogleApiError()


class _FailingMessages:
    def list(self, **_kwargs):
        return _FailingRequest()


class _FailingUsers:
    def messages(self):
        return _FailingMessages()


class _FailingGmailApi:
    def users(self):
        return _FailingUsers()


class _FailingEvents:
    def list(self, **_kwargs):
        return _FailingRequest()


class _FailingCalendarApi:
    def events(self):
        return _FailingEvents()


class _RefreshableCredentials:
    def __init__(self):
        self.valid = False
        self.expired = True
        self.refresh_token = 'refresh-token'
        self.scopes = ['scope-a']

    def refresh(self, _request):
        self.valid = True
        self.expired = False


class GoogleSyncVisibilityTests(unittest.TestCase):
    def test_gmail_strict_fetch_raises_instead_of_returning_empty_inbox(self):
        service = GmailService.__new__(GmailService)
        service.service = _FailingGmailApi()
        service.last_error = None
        service.last_error_status = None
        service.last_error_reason = None

        with self.assertRaises(_GoogleApiError):
            service.get_emails(raise_errors=True)

        self.assertEqual(service.last_error_status, 401)

    def test_calendar_strict_fetch_raises_instead_of_returning_empty_events(self):
        service = CalendarService.__new__(CalendarService)
        service.service = _FailingCalendarApi()
        service.last_error = None
        service.last_error_status = None
        service.last_error_reason = None

        with self.assertRaises(_GoogleApiError):
            service.get_events(raise_errors=True)

        self.assertEqual(service.last_error_status, 401)

    def test_credential_inspection_refreshes_and_reports_valid_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            token_file = os.path.join(temp_dir, 'google.pickle')
            with open(token_file, 'wb') as token:
                pickle.dump(_RefreshableCredentials(), token)

            with patch.object(
                user_context,
                'get_user_token_file',
                return_value=token_file,
            ), patch.object(
                user_context,
                'persist_google_credentials',
            ) as persist:
                status = user_context.inspect_google_credentials(
                    'admin@example.com',
                    refresh=True,
                )

        self.assertTrue(status['valid'])
        self.assertTrue(status['refreshed'])
        self.assertFalse(status['expired'])
        persist.assert_called_once()


if __name__ == '__main__':
    unittest.main()
