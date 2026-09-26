import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from routes.email import (  # noqa: E402
    _extract_meeting_suggestion,
    _is_meeting_suggestion_stale,
    _prune_existing_meeting_suggestions,
    _store_meeting_suggestions,
)


class EmailMeetingDetectionTests(unittest.TestCase):
    def test_empty_calendar_does_not_hide_pending_suggestions(self):
        pending = [{"id": 1, "title": "Testing lịch hẹn"}]
        with patch("routes.email.meeting._load_schedule_match_index", return_value=[]), patch(
            "routes.email.MeetingSuggestion.get_pending", return_value=pending
        ):
            self.assertEqual(pending, _prune_existing_meeting_suggestions("test.db"))

    def test_stale_pending_suggestion_is_dismissed_and_hidden(self):
        past = (datetime.now() - timedelta(days=5)).isoformat()
        upcoming = (datetime.now() + timedelta(days=2)).isoformat()
        pending = [
            {"id": 1, "email_id": "old-mail", "title": "Đã trôi qua", "start_time": past},
            {"id": 2, "email_id": "new-mail", "title": "Sắp tới", "start_time": upcoming},
        ]
        with patch("routes.email.meeting._load_schedule_match_index", return_value=[]), patch(
            "routes.email.MeetingSuggestion.get_pending", return_value=pending
        ), patch("routes.email.MeetingSuggestion.dismiss_email") as dismiss:
            visible = _prune_existing_meeting_suggestions("test.db")
        self.assertEqual([pending[1]], visible)
        dismiss.assert_called_once_with("old-mail", db_path="test.db")

    def test_scan_does_not_store_a_suggestion_whose_date_already_passed(self):
        old_email = {
            "id": "stale-mail",
            "subject": "Mời họp review dự án",
            "sender": "Lan <lan@example.com>",
            # Sent well over a year before "now" -- "ngày mai" resolves to a
            # date that has long since passed by the time this scan runs.
            "date": (datetime.now() - timedelta(days=400)).strftime("%a, %d %b %Y %H:%M:%S +0700"),
            "snippet": "Mình họp lúc 3 giờ chiều ngày mai nhé.",
        }
        with patch("routes.email.MeetingSuggestion.upsert") as upsert, patch(
            "routes.email.MeetingSuggestion.dismiss_email"
        ) as dismiss:
            detected = _store_meeting_suggestions([old_email], "test.db")
        self.assertEqual([], detected)
        upsert.assert_not_called()
        dismiss.assert_called_once_with("stale-mail", db_path="test.db")

    def test_is_meeting_suggestion_stale(self):
        self.assertFalse(_is_meeting_suggestion_stale({}))
        self.assertTrue(_is_meeting_suggestion_stale({
            "start_time": (datetime.now() - timedelta(hours=1)).isoformat()
        }))
        self.assertFalse(_is_meeting_suggestion_stale({
            "start_time": (datetime.now() + timedelta(hours=1)).isoformat()
        }))

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
