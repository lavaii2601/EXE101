import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils import user_context  # noqa: E402


class _Result:
    def __init__(self, one=None, many=None):
        self._one = one
        self._many = many or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class _IdentityConnection:
    def __init__(self, users=None, exact_by_email=None, identities=None):
        self.users = dict(users or {})
        self.exact_by_email = dict(exact_by_email or {})
        self.identities = dict(identities or {})
        self.inserted_users = []
        self.inserted_identities = []

    def execute(self, statement, params=()):
        sql = " ".join(str(statement).split())
        params = tuple(params)

        if sql.startswith("SELECT user_id FROM user_identities"):
            subject = params[0]
            user_id = self.identities.get(subject)
            return _Result(one={"user_id": user_id} if user_id else None)

        if "FROM users WHERE LOWER(COALESCE(gmail_email" in sql:
            email = params[0]
            return _Result(
                many=[
                    {"user_id": user_id}
                    for user_id in self.exact_by_email.get(email, [])
                ]
            )

        if sql.startswith("SELECT user_id, gmail_email, email FROM users"):
            return _Result(one=self.users.get(params[0]))

        if sql.startswith("INSERT INTO users"):
            user_id, email, gmail_email = params
            self.inserted_users.append(params)
            self.users.setdefault(
                user_id,
                {
                    "user_id": user_id,
                    "email": email,
                    "gmail_email": gmail_email,
                },
            )
            return _Result()

        if sql.startswith("INSERT INTO user_identities"):
            subject, user_id, account_email = params
            self.inserted_identities.append(params)
            self.identities.setdefault(subject, user_id)
            return _Result()

        raise AssertionError(f"Unexpected SQL in identity test: {sql}")


@contextmanager
def _connection(connection):
    yield connection


class GoogleIdentityMappingTests(unittest.TestCase):
    def _resolve_with(self, connection, subject, email):
        with (
            patch.object(user_context.pg, "enabled", return_value=True),
            patch.object(
                user_context.pg,
                "connection",
                side_effect=lambda: _connection(connection),
            ),
        ):
            return user_context.resolve_google_user_id(subject, email)

    def test_punctuation_collision_does_not_reuse_another_accounts_legacy_id(self):
        first_email = "a.b@example.com"
        colliding_email = "a_b@example.com"
        legacy_user_id = user_context.sanitize_user_id(first_email)
        self.assertEqual(
            legacy_user_id,
            user_context.sanitize_user_id(colliding_email),
        )
        connection = _IdentityConnection(
            users={
                legacy_user_id: {
                    "user_id": legacy_user_id,
                    "gmail_email": first_email,
                    "email": first_email,
                }
            }
        )

        resolved = self._resolve_with(
            connection,
            "google-subject-for-underscore-account",
            colliding_email,
        )

        self.assertNotEqual(legacy_user_id, resolved)
        self.assertEqual(
            user_context._stable_principal(
                "google",
                "google-subject-for-underscore-account",
            ),
            resolved,
        )
        self.assertEqual(resolved, connection.inserted_users[0][0])
        self.assertEqual(resolved, connection.inserted_identities[0][1])

    def test_exact_legacy_email_is_linked_once_to_immutable_subject(self):
        connection = _IdentityConnection(
            exact_by_email={"owner@example.com": ["legacy-owner"]}
        )

        first = self._resolve_with(
            connection,
            "immutable-google-subject",
            "owner@example.com",
        )
        renamed = self._resolve_with(
            connection,
            "immutable-google-subject",
            "renamed@example.com",
        )

        self.assertEqual("legacy-owner", first)
        self.assertEqual(first, renamed)
        self.assertEqual(1, len(connection.inserted_identities))


if __name__ == "__main__":
    unittest.main()
