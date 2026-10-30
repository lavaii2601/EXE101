"""_summarize_latest_emails was refactored this session from a fully
sequential loop (one blocking AI call per email, back to back) into a
two-phase sequential-quota-check + parallel-AI-call pipeline, specifically
to speed up "summarize my last N emails" in chat. These tests guard the
two things that refactor could plausibly have broken: result ordering
(ThreadPoolExecutor.map does preserve input order, but this proves it end
to end through the real function) and the exact quota-exhaustion stopping
behavior (enforce_ai_quota must still be checked once per email, in order,
sequentially -- it's a DB side-effecting increment, not just a read)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import chat_agents  # noqa: E402
from services.chat_agents import email_agents  # noqa: E402


def _email(email_id, subject):
    return {'id': email_id, 'subject': subject, 'sender': 'a@b.com', 'date': '2026-10-20'}


class SummarizeLatestEmailsTests(unittest.TestCase):
    def setUp(self):
        self.token_file = tempfile.NamedTemporaryFile()
        self.addCleanup(self.token_file.close)
        self.emails = [_email(f'mail-{i}', f'Subject {i}') for i in range(1, 6)]

        self.gmail_service = MagicMock()
        self.gmail_service.get_emails.return_value = [{'id': e['id']} for e in self.emails]
        self.gmail_service.get_email_details_batch.return_value = self.emails

        self.patches = [
            patch.object(email_agents, 'get_user_token_file', return_value=self.token_file.name),
            patch.object(email_agents, 'get_cached_gmail_service', return_value=self.gmail_service),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_summaries_stay_in_the_original_email_order_despite_parallel_execution(self):
        # Each fake summary call sleeps a different, deliberately-scrambled
        # amount so completion order differs from input order if the
        # function naively used whichever result finished first instead of
        # ThreadPoolExecutor.map's input-order guarantee.
        import time as time_module
        delays = {'mail-1': 0.03, 'mail-2': 0.01, 'mail-3': 0.04, 'mail-4': 0.0, 'mail-5': 0.02}

        def fake_summarize(email, user_id=None):
            time_module.sleep(delays[email['id']])
            return f"Summary for {email['id']}"

        with (
            patch.object(
                email_agents, 'enforce_ai_quota',
                return_value={'allowed': True, 'used': 1, 'limit': 50, 'remaining': 49},
            ),
            patch.object(chat_agents.ai_service, 'summarize_email_polished', side_effect=fake_summarize),
        ):
            body, emails = email_agents._summarize_latest_emails('alice', count=5)

        self.assertEqual(['mail-1', 'mail-2', 'mail-3', 'mail-4', 'mail-5'], [e['id'] for e in emails])
        # The rendered body must list them in the same order too.
        self.assertLess(body.index('Summary for mail-1'), body.index('Summary for mail-2'))
        self.assertLess(body.index('Summary for mail-2'), body.index('Summary for mail-3'))
        self.assertLess(body.index('Summary for mail-4'), body.index('Summary for mail-5'))

    def test_stops_at_the_exact_email_where_quota_is_exhausted(self):
        # Allowed for the first 2 emails, exhausted starting at the 3rd --
        # must stop there and never call summarize_email_polished for
        # emails 3, 4, 5.
        call_count = {'n': 0}

        def fake_enforce_quota(user_id, action):
            call_count['n'] += 1
            if call_count['n'] <= 2:
                return {'allowed': True, 'used': call_count['n'], 'limit': 2, 'remaining': 2 - call_count['n']}
            return {'allowed': False, 'used': 2, 'limit': 2, 'remaining': 0}

        summarized_ids = []

        def fake_summarize(email, user_id=None):
            summarized_ids.append(email['id'])
            return f"Summary for {email['id']}"

        with (
            patch.object(email_agents, 'enforce_ai_quota', side_effect=fake_enforce_quota),
            patch.object(chat_agents.ai_service, 'summarize_email_polished', side_effect=fake_summarize),
        ):
            body, emails = email_agents._summarize_latest_emails('alice', count=5)

        self.assertEqual(['mail-1', 'mail-2'], [e['id'] for e in emails])
        self.assertEqual(['mail-1', 'mail-2'], summarized_ids)
        self.assertIn('hết lượt tóm tắt email AI miễn phí', body)

    def test_quota_exhausted_before_the_first_email_raises(self):
        with (
            patch.object(
                email_agents, 'enforce_ai_quota',
                return_value={'allowed': False, 'used': 1, 'limit': 0, 'remaining': 0},
            ),
            patch.object(chat_agents.ai_service, 'summarize_email_polished') as fake_summarize,
        ):
            with self.assertRaises(RuntimeError):
                email_agents._summarize_latest_emails('alice', count=5)
        fake_summarize.assert_not_called()


if __name__ == '__main__':
    unittest.main()
