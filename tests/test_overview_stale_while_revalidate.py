import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'web' / 'backend'))

from services import overview_scheduler, overview_service  # noqa: E402


class OverviewStaleWhileRevalidateTests(unittest.TestCase):
    def test_unchanged_email_fingerprint_does_not_start_ai_refresh(self):
        with patch.object(overview_service, 'has_new_emails', return_value=False), patch.object(
            overview_service, 'refresh_daily_overview_async'
        ) as refresh:
            started = overview_service.check_and_refresh_if_new(
                'user@example.com',
                day='2026-07-20',
            )

        self.assertFalse(started)
        refresh.assert_not_called()

    def test_cached_overview_is_returned_while_revalidation_runs(self):
        cached = {
            'success': True,
            'date': '2026-07-20',
            'email_rows': [{'id': 'mail-1', 'summary': 'Cached summary'}],
            'generated': True,
        }
        with patch.object(overview_service, 'build_cached_overview', return_value=cached), patch.object(
            overview_service, 'get_day_schedules', return_value=[{'id': 7}]
        ), patch.object(
            overview_service, 'is_daily_overview_refreshing', return_value=False
        ), patch.object(
            overview_service, 'revalidate_daily_overview_async', return_value=True
        ):
            payload = overview_service.get_or_start_daily_overview(
                'user@example.com',
                '2026-07-20',
            )

        self.assertEqual(payload['email_rows'], cached['email_rows'])
        self.assertEqual(payload['schedules'], [{'id': 7}])
        self.assertTrue(payload['cache_hit'])
        self.assertTrue(payload['refreshing'])
        self.assertEqual(payload['refresh_state'], 'checking')

    def test_daily_warmup_reuses_cache_instead_of_forcing_ai(self):
        calls = []
        with patch.object(
            overview_scheduler.User,
            'list_user_ids',
            return_value=['connected-user'],
        ) as list_users, patch.object(
            overview_scheduler,
            'refresh_daily_overview_async',
            side_effect=lambda user_id, day, force: calls.append((user_id, day, force)),
        ):
            overview_scheduler._refresh_all_users('2026-07-20')

        list_users.assert_called_once_with(connected_only=True, limit=500)
        self.assertEqual(calls, [('connected-user', '2026-07-20', False)])


if __name__ == '__main__':
    unittest.main()
