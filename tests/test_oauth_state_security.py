import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes import email as email_route  # noqa: E402


def _missing_state():
    return {
        "found": False,
        "code_verifier": None,
        "mobile": False,
    }


def _issued_mobile_state():
    return {
        "found": True,
        "code_verifier": "verifier",
        "mobile": True,
    }


class OAuthStateSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.app.register_blueprint(email_route.email_bp)
        self.client = self.app.test_client()

    def test_unknown_callback_state_is_rejected_before_token_exchange(self):
        flow = MagicMock()
        with (
            patch.object(email_route, "_build_oauth_flow", return_value=flow),
            patch.object(
                email_route,
                "_consume_oauth_state",
                return_value=_missing_state(),
            ),
        ):
            response = self.client.get(
                "/api/email/oauth2callback?state=attacker-state&code=fake"
            )

        self.assertEqual(400, response.status_code)
        self.assertEqual("invalid_oauth_state", response.get_json()["error"])
        flow.fetch_token.assert_not_called()

    def test_matching_browser_session_proves_issued_state(self):
        flow = MagicMock()
        flow.fetch_token.side_effect = RuntimeError("exchange stopped for test")
        with self.client.session_transaction() as browser_session:
            browser_session["oauth_state"] = "browser-state"

        with (
            patch.object(email_route, "_build_oauth_flow", return_value=flow),
            patch.object(
                email_route,
                "_consume_oauth_state",
                return_value=_missing_state(),
            ),
        ):
            response = self.client.get(
                "/api/email/oauth2callback?state=browser-state&code=fake"
            )

        self.assertEqual(400, response.status_code)
        self.assertEqual("token_fetch_failed", response.get_json()["error"])
        flow.fetch_token.assert_called_once()

    def test_consumed_mobile_state_cannot_be_replayed(self):
        flow = MagicMock()
        flow.fetch_token.side_effect = RuntimeError("exchange stopped for test")
        with (
            patch.object(email_route, "_build_oauth_flow", return_value=flow),
            patch.object(
                email_route,
                "_consume_oauth_state",
                side_effect=[_issued_mobile_state(), _missing_state()],
            ),
        ):
            first = self.client.get(
                "/api/email/oauth2callback?state=mobile-state&code=fake"
            )
            replay = self.client.get(
                "/api/email/oauth2callback?state=mobile-state&code=fake"
            )

        self.assertEqual("token_fetch_failed", first.get_json()["error"])
        self.assertEqual("invalid_oauth_state", replay.get_json()["error"])
        flow.fetch_token.assert_called_once()

    def test_local_state_consume_is_atomic_and_preserves_mobile_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(email_route.pg, "enabled", return_value=False),
                patch.object(email_route.Config, "DATA_DIR", temp_dir),
            ):
                email_route._store_oauth_code_verifier(
                    "one-time-state",
                    "one-time-verifier",
                )
                email_route._mark_oauth_mobile("one-time-state")
                first = email_route._consume_oauth_state("one-time-state")
                replay = email_route._consume_oauth_state("one-time-state")

        self.assertTrue(first["found"])
        self.assertTrue(first["mobile"])
        self.assertEqual("one-time-verifier", first["code_verifier"])
        self.assertEqual(_missing_state(), replay)


if __name__ == "__main__":
    unittest.main()
