import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from flask import Flask


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes import email as email_route  # noqa: E402


def _error_from_redirect(response):
    """oauth2callback failures redirect back into the app (web: /app?...,
    mobile: the flowmateai:// deep link) instead of returning bare JSON --
    see _oauth_error_redirect. Pull the error code out of that Location."""
    assert response.status_code == 302, f"expected a redirect, got {response.status_code}"
    query = parse_qs(urlparse(response.headers["Location"]).query)
    return query.get("error", [None])[0]


def _missing_state():
    return {
        "found": False,
        "code_verifier": None,
        "mobile": False,
        "mobile_code_challenge": None,
        "link_user_id": None,
    }


def _issued_mobile_state(link_user_id=None):
    return {
        "found": True,
        "code_verifier": "verifier",
        "mobile": True,
        "mobile_code_challenge": None,
        "link_user_id": link_user_id,
    }


def _issued_mobile_state_with_challenge(challenge, link_user_id=None):
    return {
        "found": True,
        "code_verifier": "verifier",
        "mobile": True,
        "mobile_code_challenge": challenge,
        "link_user_id": link_user_id,
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
            patch.object(email_route.oauth, "_build_oauth_flow", return_value=flow),
            patch.object(
                email_route.oauth,
                "_consume_oauth_state",
                return_value=_missing_state(),
            ),
        ):
            response = self.client.get(
                "/api/email/oauth2callback?state=attacker-state&code=fake"
            )

        self.assertEqual("invalid_oauth_state", _error_from_redirect(response))
        flow.fetch_token.assert_not_called()

    def test_matching_browser_session_proves_issued_state(self):
        flow = MagicMock()
        flow.fetch_token.side_effect = RuntimeError("exchange stopped for test")
        with self.client.session_transaction() as browser_session:
            browser_session["oauth_state"] = "browser-state"

        with (
            patch.object(email_route.oauth, "_build_oauth_flow", return_value=flow),
            patch.object(
                email_route.oauth,
                "_consume_oauth_state",
                return_value=_missing_state(),
            ),
        ):
            response = self.client.get(
                "/api/email/oauth2callback?state=browser-state&code=fake"
            )

        self.assertEqual("token_fetch_failed", _error_from_redirect(response))
        flow.fetch_token.assert_called_once()

    def test_consumed_mobile_state_cannot_be_replayed(self):
        flow = MagicMock()
        flow.fetch_token.side_effect = RuntimeError("exchange stopped for test")
        with (
            patch.object(email_route.oauth, "_build_oauth_flow", return_value=flow),
            patch.object(
                email_route.oauth,
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

        self.assertEqual("token_fetch_failed", _error_from_redirect(first))
        self.assertEqual("invalid_oauth_state", _error_from_redirect(replay))
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

    def _mock_successful_google_exchange(self, existing_owner="mobile-user"):
        """Patches applied by every test that needs oauth2callback to reach
        its success path (past flow.fetch_token) instead of short-circuiting
        early like the tests above.

        existing_owner is what lookup_google_identity_owner resolves to --
        i.e. this Google identity is already linked to that FlowMate user.
        None simulates a Google identity nobody has ever linked before.
        """
        flow = MagicMock()
        flow.credentials = MagicMock()
        gmail_service = MagicMock()
        gmail_service.users.return_value.getProfile.return_value.execute.return_value = {
            "emailAddress": "person@example.com"
        }
        return flow, [
            patch.object(email_route.oauth, "_build_oauth_flow", return_value=flow),
            patch.object(email_route.oauth, "build", return_value=gmail_service),
            patch.object(email_route.oauth, "_fetch_google_userinfo", return_value={}),
            patch.object(email_route.oauth, "_fetch_google_people_profile", return_value={}),
            patch.object(email_route.oauth, "lookup_google_identity_owner", return_value=existing_owner),
            patch.object(email_route.oauth, "upsert_google_identity"),
            patch.object(email_route.oauth, "persist_google_credentials", return_value="/tmp/token"),
            patch.object(email_route.oauth, "get_user_db_path", return_value="/tmp/mobile-user.db"),
            patch.object(email_route.oauth.User, "get_or_create", return_value={}),
            patch.object(email_route.oauth.User, "update"),
            patch.object(email_route.oauth.Schedule, "init_db"),
            patch.object(email_route.oauth.History, "init_db"),
            patch.object(email_route.oauth.Cache, "clear_pattern"),
            patch.object(email_route.oauth, "issue_mobile_token", return_value="fake-mobile-token"),
        ]

    def test_updated_app_gets_exchange_code_not_the_real_token_in_the_redirect(self):
        challenge = email_route.oauth._pkce_s256_challenge("app-generated-verifier")
        flow, patches = self._mock_successful_google_exchange()
        with tempfile.TemporaryDirectory() as temp_dir, (
            patch.object(email_route.oauth.pg, "enabled", return_value=False)
        ), patch.object(email_route.Config, "DATA_DIR", temp_dir), patch.object(
            email_route.oauth,
            "_consume_oauth_state",
            return_value=_issued_mobile_state_with_challenge(challenge),
        ):
            for p in patches:
                p.start()
            try:
                response = self.client.get(
                    "/api/email/oauth2callback?state=mobile-state&code=fake"
                )
            finally:
                for p in patches:
                    p.stop()

        self.assertEqual(302, response.status_code)
        location = response.headers["Location"]
        self.assertIn("exchange_code=", location)
        self.assertNotIn("access_token=", location)
        self.assertNotIn("fake-mobile-token", location)

    def test_not_yet_updated_app_still_gets_the_token_directly_in_the_redirect(self):
        """No code_challenge was ever sent (older installed app build) --
        oauth2callback must fall back to the pre-PKCE behavior rather than
        breaking sign-in for it."""
        flow, patches = self._mock_successful_google_exchange()
        with tempfile.TemporaryDirectory() as temp_dir, (
            patch.object(email_route.oauth.pg, "enabled", return_value=False)
        ), patch.object(email_route.Config, "DATA_DIR", temp_dir), patch.object(
            email_route.oauth,
            "_consume_oauth_state",
            return_value=_issued_mobile_state(),
        ):
            for p in patches:
                p.start()
            try:
                response = self.client.get(
                    "/api/email/oauth2callback?state=mobile-state&code=fake"
                )
            finally:
                for p in patches:
                    p.stop()

        self.assertEqual(302, response.status_code)
        location = response.headers["Location"]
        self.assertIn("access_token=fake-mobile-token", location)
        self.assertNotIn("exchange_code=", location)


class MobilePkceExchangeTests(unittest.TestCase):
    """Covers gmail_auth_url's code_challenge storage and the new
    POST /oauth-token-exchange route -- the app-side half of the PKCE
    protection added around the flowmateai:// deep-link handoff."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.app.register_blueprint(email_route.email_bp)
        self.client = self.app.test_client()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pg_patch = patch.object(email_route.oauth.pg, "enabled", return_value=False)
        self.pg_patch.start()
        self.data_dir_patch = patch.object(email_route.Config, "DATA_DIR", self.temp_dir.name)
        self.data_dir_patch.start()

    def tearDown(self):
        self.data_dir_patch.stop()
        self.pg_patch.stop()
        self.temp_dir.cleanup()

    def test_pkce_s256_challenge_matches_rfc7636_test_vector(self):
        # RFC 7636 appendix B's worked example.
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        self.assertEqual(
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            email_route.oauth._pkce_s256_challenge(verifier),
        )

    def test_exchange_code_redeems_exactly_once(self):
        challenge = email_route.oauth._pkce_s256_challenge("device-verifier")
        email_route.oauth._store_oauth_exchange(
            "one-time-code", challenge, {"access_token": "tok", "user_id": "u1", "email": "u1@example.com"}
        )

        first = email_route.oauth._consume_oauth_exchange("one-time-code")
        replay = email_route.oauth._consume_oauth_exchange("one-time-code")

        self.assertIsNotNone(first)
        self.assertEqual("tok", first["payload"]["access_token"])
        self.assertIsNone(replay)

    def test_exchange_route_rejects_mismatched_verifier(self):
        challenge = email_route.oauth._pkce_s256_challenge("real-verifier")
        email_route.oauth._store_oauth_exchange(
            "code-1", challenge, {"access_token": "tok", "user_id": "u1", "email": "u1@example.com"}
        )

        response = self.client.post(
            "/api/email/oauth-token-exchange",
            json={"exchange_code": "code-1", "code_verifier": "attacker-guess"},
        )

        self.assertEqual(400, response.status_code)
        self.assertEqual("code_verifier_mismatch", response.get_json()["error"])

    def test_exchange_route_accepts_the_matching_verifier_and_is_single_use(self):
        challenge = email_route.oauth._pkce_s256_challenge("real-verifier")
        email_route.oauth._store_oauth_exchange(
            "code-2", challenge, {"access_token": "tok", "user_id": "u1", "email": "u1@example.com"}
        )

        response = self.client.post(
            "/api/email/oauth-token-exchange",
            json={"exchange_code": "code-2", "code_verifier": "real-verifier"},
        )
        replay = self.client.post(
            "/api/email/oauth-token-exchange",
            json={"exchange_code": "code-2", "code_verifier": "real-verifier"},
        )

        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertEqual("tok", body["access_token"])
        self.assertEqual("u1", body["user_id"])
        self.assertEqual(400, replay.status_code)
        self.assertEqual("invalid_or_expired_exchange_code", replay.get_json()["error"])

    def test_exchange_route_rejects_unknown_code(self):
        response = self.client.post(
            "/api/email/oauth-token-exchange",
            json={"exchange_code": "never-issued", "code_verifier": "whatever"},
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual("invalid_or_expired_exchange_code", response.get_json()["error"])

    def test_exchange_route_requires_both_fields(self):
        response = self.client.post(
            "/api/email/oauth-token-exchange",
            json={"exchange_code": "code-only"},
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual("invalid_request", response.get_json()["error"])

    def test_auth_url_stores_code_challenge_for_updated_mobile_app(self):
        flow = MagicMock()
        flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth", "state-123")
        with patch.object(email_route.oauth, "_build_oauth_flow", return_value=flow), \
             patch.object(email_route.oauth, "_get_flow_code_verifier", return_value=None):
            response = self.client.get(
                "/api/email/auth_url?intent=recover&platform=mobile&code_challenge=" + ("a" * 43)
            )

        self.assertEqual(200, response.status_code)
        state = email_route.oauth._consume_oauth_state("state-123")
        self.assertEqual("a" * 43, state["mobile_code_challenge"])

    def test_auth_url_ignores_an_out_of_range_code_challenge(self):
        flow = MagicMock()
        flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth", "state-456")
        with patch.object(email_route.oauth, "_build_oauth_flow", return_value=flow), \
             patch.object(email_route.oauth, "_get_flow_code_verifier", return_value=None):
            response = self.client.get(
                "/api/email/auth_url?intent=recover&platform=mobile&code_challenge=too-short"
            )

        self.assertEqual(200, response.status_code)
        state = email_route.oauth._consume_oauth_state("state-456")
        self.assertIsNone(state["mobile_code_challenge"])


class OAuthIntentGatingTests(unittest.TestCase):
    """Google OAuth is no longer a login mechanism on its own: /auth_url and
    /auth require an explicit intent, 'link' requires an existing FlowMate
    session, and oauth2callback must never mint a new account for 'recover'
    (only resolve to one that already linked this Google identity)."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.app.register_blueprint(email_route.email_bp)
        self.client = self.app.test_client()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pg_patch = patch.object(email_route.oauth.pg, "enabled", return_value=False)
        self.pg_patch.start()
        self.data_dir_patch = patch.object(email_route.Config, "DATA_DIR", self.temp_dir.name)
        self.data_dir_patch.start()

    def tearDown(self):
        self.data_dir_patch.stop()
        self.pg_patch.stop()
        self.temp_dir.cleanup()

    def _mock_flow(self, state="state-xyz"):
        flow = MagicMock()
        flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth", state)
        return flow

    def test_auth_url_rejects_a_missing_or_unknown_intent(self):
        response = self.client.get("/api/email/auth_url")
        self.assertEqual(400, response.status_code)
        self.assertEqual("invalid_intent", response.get_json()["error"])

        response = self.client.get("/api/email/auth_url?intent=login")
        self.assertEqual(400, response.status_code)
        self.assertEqual("invalid_intent", response.get_json()["error"])

    def test_auth_url_link_requires_an_existing_session(self):
        with patch.object(email_route.oauth, "authenticated_user_id", return_value=None):
            response = self.client.get("/api/email/auth_url?intent=link")
        self.assertEqual(401, response.status_code)
        self.assertEqual("login_required", response.get_json()["error"])

    def test_auth_url_link_stores_the_current_user_as_link_user_id(self):
        flow = self._mock_flow("state-link-1")
        with patch.object(email_route.oauth, "_build_oauth_flow", return_value=flow), \
             patch.object(email_route.oauth, "_get_flow_code_verifier", return_value=None), \
             patch.object(email_route.oauth, "authenticated_user_id", return_value="alice"):
            response = self.client.get("/api/email/auth_url?intent=link")

        self.assertEqual(200, response.status_code)
        state = email_route.oauth._consume_oauth_state("state-link-1")
        self.assertEqual("alice", state["link_user_id"])

    def test_auth_url_recover_does_not_require_a_session(self):
        flow = self._mock_flow("state-recover-1")
        with patch.object(email_route.oauth, "_build_oauth_flow", return_value=flow), \
             patch.object(email_route.oauth, "_get_flow_code_verifier", return_value=None):
            response = self.client.get("/api/email/auth_url?intent=recover")
        self.assertEqual(200, response.status_code)
        state = email_route.oauth._consume_oauth_state("state-recover-1")
        self.assertIsNone(state["link_user_id"])

    def _mock_successful_exchange(self, existing_owner, existing_user=None):
        flow = MagicMock()
        flow.credentials = MagicMock()
        gmail_service = MagicMock()
        gmail_service.users.return_value.getProfile.return_value.execute.return_value = {
            "emailAddress": "person@example.com"
        }
        return [
            patch.object(email_route.oauth, "_build_oauth_flow", return_value=flow),
            patch.object(email_route.oauth, "build", return_value=gmail_service),
            patch.object(email_route.oauth, "_fetch_google_userinfo", return_value={}),
            patch.object(email_route.oauth, "_fetch_google_people_profile", return_value={}),
            patch.object(email_route.oauth, "lookup_google_identity_owner", return_value=existing_owner),
            patch.object(email_route.oauth, "upsert_google_identity"),
            patch.object(email_route.oauth, "persist_google_credentials", return_value="/tmp/token"),
            patch.object(email_route.oauth, "get_user_db_path", return_value="/tmp/u.db"),
            patch.object(email_route.oauth.User, "get_or_create", return_value=existing_user or {}),
            patch.object(email_route.oauth.User, "update"),
            patch.object(email_route.oauth.Schedule, "init_db"),
            patch.object(email_route.oauth.History, "init_db"),
            patch.object(email_route.oauth.Cache, "clear_pattern"),
        ]

    def test_callback_rejects_linking_a_google_account_already_owned_by_someone_else(self):
        patches = self._mock_successful_exchange(existing_owner="bob")
        with patch.object(
            email_route.oauth, "_consume_oauth_state",
            return_value=_issued_mobile_state(link_user_id="alice"),
        ):
            for p in patches:
                p.start()
            try:
                response = self.client.get("/api/email/oauth2callback?state=s&code=fake")
            finally:
                for p in patches:
                    p.stop()
        self.assertEqual("google_account_already_linked_elsewhere", _error_from_redirect(response))
        # The conflicting Google address rides along so the client can show
        # a specific "X is already linked elsewhere" message instead of a
        # generic one -- see _oauth_error_redirect's email param.
        query = parse_qs(urlparse(response.headers["Location"]).query)
        self.assertEqual("person@example.com", query.get("email", [None])[0])

    def test_callback_link_succeeds_when_unowned_or_owned_by_the_same_user(self):
        for existing_owner in (None, "alice"):
            patches = self._mock_successful_exchange(existing_owner=existing_owner)
            with patch.object(
                email_route.oauth, "_consume_oauth_state",
                return_value=_issued_mobile_state(link_user_id="alice"),
            ), patch.object(email_route.oauth, "issue_mobile_token", return_value="tok"):
                for p in patches:
                    p.start()
                try:
                    response = self.client.get("/api/email/oauth2callback?state=s&code=fake")
                finally:
                    for p in patches:
                        p.stop()
            self.assertEqual(302, response.status_code, msg=f"existing_owner={existing_owner!r}")
            self.assertIn("access_token=", response.headers["Location"])

    def test_callback_recover_rejects_a_google_identity_nobody_ever_linked(self):
        """Recovery must never mint a new account -- that would silently
        reintroduce Google-as-signup."""
        patches = self._mock_successful_exchange(existing_owner=None)
        with patch.object(
            email_route.oauth, "_consume_oauth_state",
            return_value=_issued_mobile_state(link_user_id=None),
        ):
            for p in patches:
                p.start()
            try:
                response = self.client.get("/api/email/oauth2callback?state=s&code=fake")
            finally:
                for p in patches:
                    p.stop()
        self.assertEqual("no_flowmate_account_for_google_identity", _error_from_redirect(response))

    def test_callback_recover_succeeds_for_a_previously_linked_identity(self):
        patches = self._mock_successful_exchange(existing_owner="alice")
        with patch.object(
            email_route.oauth, "_consume_oauth_state",
            return_value=_issued_mobile_state(link_user_id=None),
        ), patch.object(email_route.oauth, "issue_mobile_token", return_value="tok"):
            for p in patches:
                p.start()
            try:
                response = self.client.get("/api/email/oauth2callback?state=s&code=fake")
            finally:
                for p in patches:
                    p.stop()
        self.assertEqual(302, response.status_code)
        self.assertIn("access_token=", response.headers["Location"])

    def test_callback_flags_needs_password_for_an_account_with_no_password_set(self):
        patches = self._mock_successful_exchange(
            existing_owner="alice", existing_user={"password_hash": None},
        )
        with patch.object(
            email_route.oauth, "_consume_oauth_state",
            return_value=_issued_mobile_state(link_user_id=None),
        ), patch.object(email_route.oauth, "issue_mobile_token", return_value="tok"):
            for p in patches:
                p.start()
            try:
                response = self.client.get("/api/email/oauth2callback?state=s&code=fake")
            finally:
                for p in patches:
                    p.stop()
        self.assertEqual(302, response.status_code)
        self.assertIn("needs_password=1", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
