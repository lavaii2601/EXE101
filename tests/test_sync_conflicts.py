import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models import cache as cache_module  # noqa: E402
from models import schedule as schedule_module  # noqa: E402
from models.cache import Cache  # noqa: E402
from models.schedule import Schedule  # noqa: E402
from models.workspace_sync import WorkspaceSync  # noqa: E402
from routes import _background as background_route  # noqa: E402
from routes import chat as chat_route  # noqa: E402
from routes import schedule as schedule_route  # noqa: E402
from services.chat_agents import AgentResult  # noqa: E402


class ScheduleOptimisticConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.alice_db = os.path.join(self.temp_dir.name, "alice.db")
        self.bob_db = os.path.join(self.temp_dir.name, "bob.db")
        self.pg_patch = patch.object(
            schedule_module.pg,
            "enabled",
            return_value=False,
        )
        self.pg_patch.start()

    def tearDown(self):
        self.pg_patch.stop()
        Schedule._initialized_dbs.discard(self.alice_db)
        Schedule._initialized_dbs.discard(self.bob_db)
        WorkspaceSync._initialized_dbs.discard(self.alice_db)
        WorkspaceSync._initialized_dbs.discard(self.bob_db)
        self.temp_dir.cleanup()

    @staticmethod
    def _create(db_path, title):
        return Schedule.create(
            title=title,
            description="",
            start_time="2026-07-25T09:00:00",
            end_time="2026-07-25T10:00:00",
            attendees="",
            db_path=db_path,
        )

    def test_stale_schedule_writer_is_rejected_without_overwriting(self):
        schedule_id = self._create(self.alice_db, "Original")
        original = Schedule.get_by_id(schedule_id, db_path=self.alice_db)

        saved = Schedule.update(
            schedule_id,
            title="Saved from web",
            expected_updated_at=original["updated_at"],
            db_path=self.alice_db,
        )
        stale_saved = Schedule.update(
            schedule_id,
            title="Stale APK overwrite",
            expected_updated_at=original["updated_at"],
            db_path=self.alice_db,
        )
        current = Schedule.get_by_id(schedule_id, db_path=self.alice_db)

        self.assertTrue(saved)
        self.assertFalse(stale_saved)
        self.assertEqual("Saved from web", current["title"])
        self.assertNotEqual(original["updated_at"], current["updated_at"])

    def test_status_rowcount_and_database_per_tenant_are_isolated(self):
        alice_id = self._create(self.alice_db, "Alice event")
        bob_id = self._create(self.bob_db, "Bob event")
        self.assertEqual(alice_id, bob_id)

        alice = Schedule.get_by_id(alice_id, db_path=self.alice_db)
        self.assertTrue(
            Schedule.update_status(
                alice_id,
                "completed",
                expected_updated_at=alice["updated_at"],
                db_path=self.alice_db,
            )
        )
        self.assertFalse(
            Schedule.update_status(
                999999,
                "completed",
                db_path=self.alice_db,
            )
        )

        self.assertEqual(
            "completed",
            Schedule.get_by_id(alice_id, db_path=self.alice_db)["status"],
        )
        self.assertEqual(
            "pending",
            Schedule.get_by_id(bob_id, db_path=self.bob_db)["status"],
        )

    def test_postgres_calendar_attachment_is_tenant_scoped_metadata_only(self):
        executed = []

        class _Cursor:
            rowcount = 1

        class _Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def execute(sql, values):
                executed.append((sql, values))
                return _Cursor()

        with (
            patch.object(schedule_module.pg, "enabled", return_value=True),
            patch.object(
                schedule_module.pg,
                "user_id_from_db_path",
                return_value="alice",
            ),
            patch.object(
                schedule_module.pg,
                "connection",
                return_value=_Connection(),
            ),
        ):
            attached = Schedule.attach_calendar_event_id(
                17,
                "google-event-17",
                db_path="alice.db",
            )

        self.assertTrue(attached)
        self.assertEqual(1, len(executed))
        sql, values = executed[0]
        self.assertNotIn("updated_at", sql.lower())
        self.assertIn("user_id = %s", sql)
        self.assertEqual(("google-event-17", 17, "alice"), values)

    def test_background_google_link_publishes_revision_after_metadata_write(self):
        schedule_id = self._create(self.alice_db, "Needs Google link")
        schedule = Schedule.get_by_id(schedule_id, db_path=self.alice_db)

        class _Calendar:
            @staticmethod
            def create_event(**_kwargs):
                return "google-event-1"

        with (
            patch.object(
                schedule_route,
                "_calendar_auth_failure_payload",
                return_value=None,
            ),
            patch.object(
                schedule_route,
                "_load_calendar_service",
                return_value=_Calendar(),
            ),
            patch.object(schedule_route, "_clear_schedule_cache"),
        ):
            event_id = schedule_route._sync_schedule_to_calendar(
                "alice",
                schedule_id,
                schedule,
                self.alice_db,
                publish_background_revision=True,
            )

        linked = Schedule.get_by_id(schedule_id, db_path=self.alice_db)
        state = WorkspaceSync.get_state("alice", db_path=self.alice_db)

        self.assertEqual("google-event-1", event_id)
        self.assertEqual("google-event-1", linked["calendar_event_id"])
        self.assertEqual(schedule["updated_at"], linked["updated_at"])
        self.assertEqual(1, state["revision"])
        self.assertEqual(1, state["domains"]["schedule"])
        self.assertEqual(1, state["domains"]["calendar"])
        self.assertEqual(1, state["domains"]["overview"])

    def test_background_google_link_does_not_publish_when_attachment_loses_race(self):
        schedule_id = self._create(self.alice_db, "Already linked")
        stale_schedule = Schedule.get_by_id(schedule_id, db_path=self.alice_db)
        self.assertTrue(
            Schedule.attach_calendar_event_id(
                schedule_id,
                "winner-event",
                db_path=self.alice_db,
            )
        )

        class _Calendar:
            @staticmethod
            def create_event(**_kwargs):
                return "loser-event"

        with (
            patch.object(
                schedule_route,
                "_calendar_auth_failure_payload",
                return_value=None,
            ),
            patch.object(
                schedule_route,
                "_load_calendar_service",
                return_value=_Calendar(),
            ),
            patch.object(schedule_route, "_clear_schedule_cache"),
        ):
            event_id = schedule_route._sync_schedule_to_calendar(
                "alice",
                schedule_id,
                stale_schedule,
                self.alice_db,
                publish_background_revision=True,
            )

        linked = Schedule.get_by_id(schedule_id, db_path=self.alice_db)
        state = WorkspaceSync.get_state("alice", db_path=self.alice_db)
        self.assertEqual("winner-event", event_id)
        self.assertEqual("winner-event", linked["calendar_event_id"])
        self.assertEqual(0, state["revision"])

    def test_legacy_background_route_bumps_only_after_successful_attachment(self):
        operations = []

        class _Calendar:
            service = object()

            def __init__(self, **_kwargs):
                pass

            @staticmethod
            def create_event(**_kwargs):
                return "legacy-google-event"

        schedule = {
            "id": 7,
            "title": "Legacy background",
            "description": "",
            "start_time": "2026-07-25T09:00:00",
            "end_time": "2026-07-25T10:00:00",
            "attendees": "",
            "calendar_event_id": None,
        }

        with (
            patch.object(
                background_route,
                "get_user_db_path",
                return_value=self.alice_db,
            ),
            patch.object(background_route.os.path, "exists", return_value=True),
            patch.object(background_route, "CalendarService", _Calendar),
            patch.object(
                background_route.Schedule,
                "get_by_id",
                return_value=schedule,
            ),
            patch.object(
                background_route.Schedule,
                "attach_calendar_event_id",
                side_effect=lambda *_args, **_kwargs: operations.append("attach") or True,
            ),
            patch.object(
                background_route.WorkspaceSync,
                "bump",
                side_effect=lambda *_args, **_kwargs: operations.append("bump"),
            ) as bump,
        ):
            background_route._sync_to_calendar_async("alice", schedule["id"])

        self.assertEqual(["attach", "bump"], operations)
        bump.assert_called_once_with(
            "alice",
            ("schedule", "calendar", "overview"),
            db_path=self.alice_db,
        )


class ChecklistOptimisticConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.alice_db = os.path.join(self.temp_dir.name, "alice-cache.db")
        self.bob_db = os.path.join(self.temp_dir.name, "bob-cache.db")
        self.pg_patch = patch.object(
            cache_module.pg,
            "enabled",
            return_value=False,
        )
        self.pg_patch.start()

    def tearDown(self):
        self.pg_patch.stop()
        Cache._initialized_dbs.discard(self.alice_db)
        Cache._initialized_dbs.discard(self.bob_db)
        self.temp_dir.cleanup()

    def test_versioned_save_returns_current_copy_to_stale_writer(self):
        first_saved, first = Cache.set_versioned(
            "daily_checklist:2026-07-25",
            {"items": [{"id": "web", "text": "Web edit"}]},
            expected_revision=0,
            db_path=self.alice_db,
        )
        second_saved, second = Cache.set_versioned(
            "daily_checklist:2026-07-25",
            {"items": [{"id": "apk", "text": "APK edit"}]},
            expected_revision=first["revision"],
            db_path=self.alice_db,
        )
        stale_saved, current = Cache.set_versioned(
            "daily_checklist:2026-07-25",
            {"items": [{"id": "stale", "text": "Stale overwrite"}]},
            expected_revision=first["revision"],
            db_path=self.alice_db,
        )

        self.assertTrue(first_saved)
        self.assertTrue(second_saved)
        self.assertFalse(stale_saved)
        self.assertEqual(1, first["revision"])
        self.assertEqual(2, second["revision"])
        self.assertEqual(second, current)
        self.assertEqual(
            second,
            Cache.get(
                "daily_checklist:2026-07-25",
                db_path=self.alice_db,
            ),
        )

    def test_revision_stream_is_isolated_by_tenant_database(self):
        alice_saved, alice = Cache.set_versioned(
            "daily_checklist:2026-07-25",
            {"items": [{"id": "alice"}]},
            expected_revision=0,
            db_path=self.alice_db,
        )
        bob_saved, bob = Cache.set_versioned(
            "daily_checklist:2026-07-25",
            {"items": [{"id": "bob"}]},
            expected_revision=0,
            db_path=self.bob_db,
        )

        self.assertTrue(alice_saved)
        self.assertTrue(bob_saved)
        self.assertEqual(1, alice["revision"])
        self.assertEqual(1, bob["revision"])
        self.assertNotEqual(alice["items"], bob["items"])

    def test_expired_revision_resets_so_a_new_revision_zero_writer_can_save(self):
        key = "daily_checklist:expired"
        initial_saved, initial = Cache.set_versioned(
            key,
            {"items": [{"id": "expired"}]},
            expected_revision=0,
            ttl=-1,
            db_path=self.alice_db,
        )
        self.assertTrue(initial_saved)
        self.assertEqual(1, initial["revision"])
        self.assertIsNone(Cache.get(key, db_path=self.alice_db))

        replacement_saved, replacement = Cache.set_versioned(
            key,
            {"items": [{"id": "fresh"}]},
            expected_revision=0,
            db_path=self.alice_db,
        )

        self.assertTrue(replacement_saved)
        self.assertEqual(1, replacement["revision"])
        self.assertEqual(
            [{"id": "fresh"}],
            Cache.get(key, db_path=self.alice_db)["items"],
        )


class ChatProfileModeTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="sync-conflict-test")
        self.app.register_blueprint(chat_route.chat_bp)
        self.client = self.app.test_client()

    def test_server_profile_mode_overrides_stale_client_mode(self):
        captured_contexts = []

        class _RecordingAgent:
            def handle(self, context):
                captured_contexts.append(context)
                return AgentResult(response="ok")

        intent = {
            "intent": "chat.freeform",
            "entities": {},
            "refresh_targets": [],
        }
        with (
            patch.object(
                chat_route,
                "get_current_user_id",
                return_value="alice",
            ),
            patch.object(
                chat_route,
                "get_user_db_path",
                return_value="alice.db",
            ),
            patch.object(
                chat_route.User,
                "get",
                return_value={"user_mode": "student"},
            ),
            patch.object(chat_route.History, "init_db"),
            patch.object(chat_route.Schedule, "init_db"),
            patch.object(
                chat_route,
                "_ensure_chat_session",
                return_value="session-1",
            ),
            patch.object(
                chat_route.intent_orchestrator,
                "detect_workflow_with_ai",
                return_value=intent,
            ),
            patch.object(
                chat_route,
                "get_agent",
                return_value=_RecordingAgent(),
            ),
            patch.object(
                chat_route,
                "normalize_agent_result_language",
                side_effect=lambda result, *_args, **_kwargs: result,
            ),
            patch.object(chat_route.History, "create", return_value=1),
            patch.object(chat_route.History, "get_recent", return_value=[]),
            patch.object(chat_route, "learn_from_exchange_async"),
            patch.object(chat_route, "learn_from_mentors_async"),
        ):
            response = self.client.post(
                "/api/chat/message",
                json={"message": "hello", "mode": "worker"},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("student", response.get_json()["effective_mode"])
        self.assertEqual(1, len(captured_contexts))
        self.assertEqual("student", captured_contexts[0].mode)
        self.assertIn("Student Mode", captured_contexts[0].mode_prompt)


if __name__ == "__main__":
    unittest.main()
