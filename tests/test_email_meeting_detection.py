import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from routes.email import _extract_meeting_suggestion, _prune_existing_meeting_suggestions  # noqa: E402


class EmailMeetingDetectionTests(unittest.TestCase):
    def test_empty_calendar_does_not_hide_pending_suggestions(self):
        pending = [{"id": 1, "title": "Testing lịch hẹn"}]
        with patch("routes.email._load_schedule_match_index", return_value=[]), patch(
            "routes.email.MeetingSuggestion.get_pending", return_value=pending
        ):
            self.assertEqual(pending, _prune_existing_meeting_suggestions("test.db"))

    def test_detects_natural_vietnamese_meeting_email(self):
        tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
        suggestion = _extract_meeting_suggestion({
            "id": "mail-1",
            "subject": "Mời họp review dự án",
            "sender": "Lan <lan@example.com>",
            "date": datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0700"),
            "snippet": "Mình họp lúc 3 giờ chiều ngày mai nhé.",
        })
        self.assertIsNotNone(suggestion)
        self.assertTrue(suggestion["start_time"].startswith(tomorrow))
        self.assertIn("T15:00:00", suggestion["start_time"])

    def test_detects_english_availability_request(self):
        suggestion = _extract_meeting_suggestion({
            "id": "mail-2",
            "subject": "Project sync",
            "sender": "Client <client@example.com>",
            "date": "Mon, 20 Jul 2026 08:00:00 +0700",
            "snippet": "Could we meet tomorrow at 10am for a review call?",
        })
        self.assertIsNotNone(suggestion)
        self.assertEqual("2026-07-21T10:00:00", suggestion["start_time"])


if __name__ == "__main__":
    unittest.main()
