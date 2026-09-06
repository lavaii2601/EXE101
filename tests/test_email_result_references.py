import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models import history as history_module  # noqa: E402
from models import session_memory as memory_module  # noqa: E402
from models.history import History  # noqa: E402
from models.session_memory import SessionMemory  # noqa: E402
from services import chat_agents  # noqa: E402
from services.chat_agents import (  # noqa: E402
    ChatContext,
    EmailSearchAgent,
    _email_result_reference,
    _mark_emails_propose,
)


def _context(message, original_message=None):
    return ChatContext(
        user_message=message,
        original_user_message=original_message,
        user_id="alice",
        db_path="alice.db",
        chat_session_id="00000000-0000-4000-8000-000000000001",
        mode="worker",
        mode_prompt="",
        task="chat",
        intent_result={"intent": "email.mark_unread", "entities": {}},
    )


class EmailResultReferenceTests(unittest.TestCase):
    def test_parses_english_and_vietnamese_ordinals(self):
        cases = (
            ("mark the second one unread", ("ordinal", 2)),
            ("đánh dấu cái thứ 2 chưa đọc", ("ordinal", 2)),
            ("mark email #3 as read", ("ordinal", 3)),
            ("đánh dấu email thứ ba đã đọc", ("ordinal", 3)),
        )
        for message, expected in cases:
            with self.subTest(message=message):
                self.assertEqual(expected, _email_result_reference(message))

    def test_ordinal_followup_proposes_only_the_exact_remembered_email(self):
        remembered = [
            {"id": "mail-1", "title": "Alpha"},
            {"id": "mail-2", "title": "Beta"},
            {"id": "mail-3", "title": "Gamma"},
        ]
        with (
            tempfile.NamedTemporaryFile() as token,
            patch.object(chat_agents.email_agents, "get_user_token_file", return_value=token.name),
            patch.object(
                chat_agents.SessionMemory,
                "get_email_results",
                return_value=remembered,
            ),
            patch.object(chat_agents.email_agents, "get_cached_gmail_service") as gmail_service,
        ):
            for prompt in (
                "mark the second one unread",
                "đánh dấu cái thứ 2 chưa đọc",
            ):
                with self.subTest(prompt=prompt):
                    result = _mark_emails_propose(
                        _context(
                            "Mark the Project Beta email unread",
                            original_message=prompt,
                        ),
                        read=False,
                    )
                    self.assertEqual(
                        ["mail-2"],
                        result.pending_action["arguments"]["email_ids"],
                    )
                    self.assertEqual(
                        ["Beta"],
                        result.pending_action["arguments"]["titles"],
                    )
                    self.assertIn("Xác nhận", result.response)

        gmail_service.assert_not_called()

    def test_reference_without_same_session_map_never_falls_back_to_first_three(self):
        with (
            tempfile.NamedTemporaryFile() as token,
            patch.object(chat_agents.email_agents, "get_user_token_file", return_value=token.name),
            patch.object(
                chat_agents.SessionMemory,
                "get_email_results",
                return_value=[],
            ),
            patch.object(chat_agents.email_agents, "get_cached_gmail_service") as gmail_service,
        ):
            result = _mark_emails_propose(
                _context("mark the second one unread"),
                read=False,
            )

        self.assertIsNone(result.pending_action)
        self.assertIn("chưa có danh sách email", result.response)
        gmail_service.assert_not_called()

    def test_out_of_range_reference_is_not_proposed(self):
        with (
            tempfile.NamedTemporaryFile() as token,
            patch.object(chat_agents.email_agents, "get_user_token_file", return_value=token.name),
            patch.object(
                chat_agents.SessionMemory,
                "get_email_results",
                return_value=[{"id": "mail-1", "title": "Only"}],
            ),
        ):
            result = _mark_emails_propose(
                _context("mark the second one unread"),
                read=False,
            )

        self.assertIsNone(result.pending_action)
        self.assertIn("không có mục số 2", result.response)

    def test_email_search_remembers_the_displayed_order_for_this_session(self):
        emails = [
            {"id": "mail-1", "subject": "Alpha"},
            {"id": "mail-2", "subject": "Beta"},
        ]
        ctx = _context("find emails from Lan")
        ctx.intent_result = {"intent": "email.search", "entities": {}}

        with (
            patch.object(
                chat_agents.email_agents,
                "_direct_email_search_response",
                return_value=("EMAIL TÌM THẤY", emails),
            ),
            patch.object(
                chat_agents.SessionMemory,
                "remember_email_results",
            ) as remember,
        ):
            result = EmailSearchAgent().handle(ctx)

        self.assertEqual("EMAIL TÌM THẤY", result.response)
        remember.assert_called_once_with(
            "alice",
            ctx.chat_session_id,
            emails,
            db_path="alice.db",
            workspace_id=None,
        )


class EmailResultSessionMemoryTests(unittest.TestCase):
    def test_sqlite_result_map_is_session_scoped_and_hidden_from_prompt_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "alice.db")
            session_id = str(uuid.uuid4())
            other_session_id = str(uuid.uuid4())

            with (
                patch.object(history_module.pg, "enabled", return_value=False),
                patch.object(memory_module.pg, "enabled", return_value=False),
            ):
                History.ensure_chat_session("alice", session_id=session_id, db_path=db_path)
                History.ensure_chat_session("alice", session_id=other_session_id, db_path=db_path)
                SessionMemory.remember(
                    "alice",
                    session_id,
                    "Project Atlas ships Friday",
                    db_path=db_path,
                )
                SessionMemory.remember_email_results(
                    "alice",
                    session_id,
                    [
                        {"id": "mail-1", "subject": "Alpha"},
                        {"id": "mail-2", "subject": "Beta"},
                    ],
                    db_path=db_path,
                )

                self.assertEqual(
                    [
                        {"id": "mail-1", "title": "Alpha"},
                        {"id": "mail-2", "title": "Beta"},
                    ],
                    SessionMemory.get_email_results(
                        "alice",
                        session_id,
                        db_path=db_path,
                    ),
                )
                self.assertEqual(
                    [],
                    SessionMemory.get_email_results(
                        "alice",
                        other_session_id,
                        db_path=db_path,
                    ),
                )
                self.assertEqual(
                    ["Project Atlas ships Friday"],
                    SessionMemory.list_for_session(
                        "alice",
                        session_id,
                        db_path=db_path,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
