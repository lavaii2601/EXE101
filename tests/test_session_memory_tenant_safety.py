import os
import sys
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from flask import Flask


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models import history as history_module  # noqa: E402
from models import session_memory as memory_module  # noqa: E402
from models.history import History  # noqa: E402
from models.session_memory import SessionMemory  # noqa: E402
from routes import chat as chat_route  # noqa: E402

WORKSPACE_ID = "10000000-0000-4000-8000-000000000001"


class _Result:
    def __init__(self, one=None, rows=None, rowcount=0):
        self._one = one
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows


class _RecordingConnection:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def execute(self, statement, params=()):
        self.calls.append((" ".join(str(statement).split()), tuple(params)))
        if not self.results:
            return _Result()
        return self.results.pop(0)


@contextmanager
def _connection(connection):
    yield connection


class SessionMemoryTenantTests(unittest.TestCase):
    def test_postgres_remember_requires_matching_user_and_session_owner(self):
        connection = _RecordingConnection([
            _Result(one=None),
            _Result(one=None),
        ])

        with (
            patch.object(memory_module.pg, "enabled", return_value=True),
            patch.object(memory_module.pg, "ensure_user"),
            patch.object(
                memory_module.pg,
                "connection",
                side_effect=lambda: _connection(connection),
            ),
        ):
            remembered = SessionMemory.remember(
                "alice",
                "00000000-0000-4000-8000-000000000001",
                "Project Atlas ships Friday",
                workspace_id=WORKSPACE_ID,
            )

        self.assertIsNone(remembered)
        duplicate_sql, duplicate_params = connection.calls[0]
        insert_sql, insert_params = connection.calls[1]
        self.assertIn("memory.user_id = %s", duplicate_sql)
        self.assertEqual(("alice", WORKSPACE_ID), duplicate_params[:2])
        self.assertIn("session.user_id = %s", insert_sql)
        self.assertEqual(("alice", WORKSPACE_ID), insert_params[-2:])

    def test_postgres_memory_reads_and_deletes_are_user_scoped(self):
        read_connection = _RecordingConnection([
            _Result(rows=[{"content": "first"}, {"content": "second"}]),
        ])
        delete_connection = _RecordingConnection([_Result(rowcount=2)])

        with (
            patch.object(memory_module.pg, "enabled", return_value=True),
            patch.object(
                memory_module.pg,
                "connection",
                side_effect=lambda: _connection(read_connection),
            ),
        ):
            memories = SessionMemory.list_for_session(
                "alice",
                "00000000-0000-4000-8000-000000000001",
                workspace_id=WORKSPACE_ID,
            )

        with (
            patch.object(memory_module.pg, "enabled", return_value=True),
            patch.object(
                memory_module.pg,
                "connection",
                side_effect=lambda: _connection(delete_connection),
            ),
        ):
            deleted = SessionMemory.delete_for_session(
                "alice",
                "00000000-0000-4000-8000-000000000001",
                workspace_id=WORKSPACE_ID,
            )

        self.assertEqual(["second", "first"], memories)
        self.assertEqual(2, deleted)
        read_sql, read_params = read_connection.calls[0]
        delete_sql, delete_params = delete_connection.calls[0]
        self.assertIn("memory.user_id = %s", read_sql)
        self.assertEqual(("alice", WORKSPACE_ID), read_params[:2])
        self.assertIn("user_id = %s", delete_sql)
        self.assertEqual(
            ("alice", WORKSPACE_ID, "00000000-0000-4000-8000-000000000001"),
            delete_params,
        )

    def test_sqlite_delete_all_clears_only_the_selected_user_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            alice_db = os.path.join(temp_dir, "alice.db")
            bob_db = os.path.join(temp_dir, "bob.db")
            alice_session = str(uuid.uuid4())
            bob_session = str(uuid.uuid4())

            with patch.object(memory_module.pg, "enabled", return_value=False):
                SessionMemory.remember("alice", alice_session, "Alice fact", db_path=alice_db)
                SessionMemory.remember("bob", bob_session, "Bob fact", db_path=bob_db)
                self.assertEqual(
                    1,
                    SessionMemory.delete_all_for_user("alice", db_path=alice_db),
                )
                self.assertEqual(
                    [],
                    SessionMemory.list_for_session(
                        "alice",
                        alice_session,
                        db_path=alice_db,
                    ),
                )
                self.assertEqual(
                    ["Bob fact"],
                    SessionMemory.list_for_session(
                        "bob",
                        bob_session,
                        db_path=bob_db,
                    ),
                )


class ChatSessionTenantTests(unittest.TestCase):
    def test_premium_session_uses_supported_365_day_retention(self):
        supplied = str(uuid.uuid4())
        connection = _RecordingConnection([
            _Result(one=None),
            _Result(one={"id": supplied}),
        ])

        with (
            patch.object(history_module.pg, "enabled", return_value=True),
            patch.object(history_module.pg, "ensure_user"),
            patch.object(
                history_module.pg,
                "connection",
                side_effect=lambda: _connection(connection),
            ),
            patch.object(
                history_module.subscription_model,
                "is_premium",
                return_value=True,
            ),
        ):
            actual = History.ensure_chat_session(
                "alice", session_id=supplied, workspace_id=WORKSPACE_ID
            )

        self.assertEqual(supplied, actual)
        insert_params = connection.calls[1][1]
        self.assertEqual(365, insert_params[5])
        self.assertEqual(365, insert_params[6])

    def test_foreign_supplied_session_id_is_replaced(self):
        supplied = str(uuid.uuid4())
        replacement = uuid.uuid4()
        connection = _RecordingConnection([
            _Result(one={"user_id": "bob", "available": True}),
            _Result(one={"id": str(replacement)}),
        ])

        with (
            patch.object(history_module.pg, "enabled", return_value=True),
            patch.object(history_module.pg, "ensure_user"),
            patch.object(
                history_module.subscription_model,
                "is_premium",
                return_value=False,
            ),
            patch.object(
                history_module.pg,
                "connection",
                side_effect=lambda: _connection(connection),
            ),
            patch.object(history_module.uuid, "uuid4", return_value=replacement),
        ):
            actual = History.ensure_chat_session(
                "alice", session_id=supplied, workspace_id=WORKSPACE_ID
            )

        self.assertEqual(str(replacement), actual)
        insert_sql, insert_params = connection.calls[1]
        self.assertIn("WHERE chat_sessions.user_id = EXCLUDED.user_id", insert_sql)
        self.assertEqual(str(replacement), insert_params[0])
        self.assertEqual("alice", insert_params[1])

    def test_owned_active_session_id_is_preserved(self):
        supplied = str(uuid.uuid4())
        connection = _RecordingConnection([
            _Result(one={
                "user_id": "alice",
                "workspace_id": WORKSPACE_ID,
                "available": True,
            }),
            _Result(one={"id": supplied}),
        ])

        with (
            patch.object(history_module.pg, "enabled", return_value=True),
            patch.object(history_module.pg, "ensure_user"),
            patch.object(
                history_module.subscription_model,
                "is_premium",
                return_value=False,
            ),
            patch.object(
                history_module.pg,
                "connection",
                side_effect=lambda: _connection(connection),
            ),
        ):
            actual = History.ensure_chat_session(
                "alice", session_id=supplied, workspace_id=WORKSPACE_ID
            )

        self.assertEqual(supplied, actual)
        self.assertEqual(supplied, connection.calls[1][1][0])


class WorkspaceIsolationSchemaTests(unittest.TestCase):
    def test_existing_tables_gain_workspace_columns_before_backfill(self):
        schema = (REPO_ROOT / "database" / "postgres_schema.sql").read_text(
            encoding="utf-8"
        )
        backfill_position = schema.index("UPDATE chat_sessions cs")
        for table in ("chat_sessions", "history", "session_memory"):
            alter = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS workspace_id UUID;"
            self.assertIn(alter, schema)
            self.assertLess(schema.index(alter), backfill_position)


class ClearRouteSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(TESTING=True, SECRET_KEY="test")
        cls.app.register_blueprint(chat_route.chat_bp)

    def test_clear_without_session_removes_all_conversations_and_memory(self):
        with (
            patch.object(chat_route, "get_current_user_id", return_value="alice"),
            patch.object(chat_route, "get_current_workspace_id", return_value=WORKSPACE_ID),
            patch.object(chat_route, "get_user_db_path", return_value="alice.db"),
            patch.object(
                chat_route.History,
                "clear_chat_state",
                return_value={"history": 4, "memory": 2, "sessions": 1},
            ) as clear_state,
        ):
            response = self.app.test_client().post("/api/chat/clear", json={})

        self.assertEqual(200, response.status_code)
        self.assertEqual(4, response.get_json()["deleted_count"])
        clear_state.assert_called_once_with(
            "alice",
            db_path="alice.db",
            chat_session_id=None,
            clear_all_history=False,
            workspace_id=WORKSPACE_ID,
        )

    def test_clear_all_removes_session_metadata_and_memory_for_same_user(self):
        with (
            patch.object(chat_route, "get_current_user_id", return_value="alice"),
            patch.object(chat_route, "get_current_workspace_id", return_value=WORKSPACE_ID),
            patch.object(chat_route, "get_user_db_path", return_value="alice.db"),
            patch.object(
                chat_route.History,
                "clear_chat_state",
                return_value={"history": 7, "memory": 3, "sessions": 2},
            ) as clear_state,
        ):
            response = self.app.test_client().post("/api/chat/clear-all")

        payload = response.get_json()
        self.assertEqual(200, response.status_code)
        self.assertEqual(7, payload["deleted_count"])
        self.assertEqual(3, payload["deleted_memory_count"])
        self.assertEqual(2, payload["deleted_session_count"])
        clear_state.assert_called_once_with(
            "alice",
            db_path="alice.db",
            clear_all_history=True,
            workspace_id=WORKSPACE_ID,
        )

    def test_sqlite_session_clear_is_one_scoped_state_operation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "alice.db")
            first = str(uuid.uuid4())
            second = str(uuid.uuid4())
            with (
                patch.object(history_module.pg, "enabled", return_value=False),
                patch.object(memory_module.pg, "enabled", return_value=False),
            ):
                History.ensure_chat_session("alice", first, db_path=db_path)
                History.ensure_chat_session("alice", second, db_path=db_path)
                History.create(
                    "first",
                    "answer",
                    action_type="chat",
                    db_path=db_path,
                    chat_session_id=first,
                )
                History.create(
                    "second",
                    "answer",
                    action_type="chat",
                    db_path=db_path,
                    chat_session_id=second,
                )
                SessionMemory.remember(
                    "alice", first, "first fact", db_path=db_path
                )
                SessionMemory.remember(
                    "alice", second, "second fact", db_path=db_path
                )

                deleted = History.clear_chat_state(
                    "alice",
                    db_path=db_path,
                    chat_session_id=first,
                )

                self.assertEqual(
                    {"history": 1, "memory": 1, "sessions": 0},
                    deleted,
                )
                self.assertEqual(
                    [],
                    History.get_recent(
                        db_path=db_path,
                        chat_session_id=first,
                    ),
                )
                self.assertEqual(
                    ["second fact"],
                    SessionMemory.list_for_session(
                        "alice", second, db_path=db_path
                    ),
                )
                self.assertTrue(
                    History.chat_session_available(
                        "alice", first, db_path=db_path
                    )
                )


if __name__ == "__main__":
    unittest.main()
