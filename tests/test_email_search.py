import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes import email as email_route  # noqa: E402


class GmailQueryForEmailListTests(unittest.TestCase):
    """_gmail_query_for_email_list is what routes the `search` box into
    Gmail's own server-side search instead of only locally re-filtering
    whatever the plain is:unread/in:inbox scan already happened to fetch
    (the bug: a keyword only "worked" when the matching email was already
    among the most recent ~25 messages)."""

    def test_no_search_keeps_the_plain_unread_scan(self):
        self.assertEqual('is:unread', email_route._gmail_query_for_email_list(''))

    def test_search_reaches_gmail_and_widens_to_the_whole_inbox(self):
        query = email_route._gmail_query_for_email_list('invoice')
        self.assertEqual('in:inbox invoice', query)
        # Whole-inbox (not unread-only), regardless of the include_read
        # toggle -- a user searching for a specific email wants it found
        # even if they already read it.
        self.assertNotIn('is:unread', query)

    def test_multi_word_search_is_passed_through_for_gmails_own_and_semantics(self):
        # Gmail treats space-separated terms as an AND search across
        # subject/sender/body -- exactly the "keyword search" behavior
        # being restored, so the terms must reach Gmail unquoted/unsplit.
        query = email_route._gmail_query_for_email_list('nguyen van a')
        self.assertEqual('in:inbox nguyen van a', query)


class EmailSearchCacheKeyTests(unittest.TestCase):
    """A search re-queries Gmail with entirely different scope than the
    plain "most recent N unread/inbox messages" cache, so it must never be
    served from, or overwrite, that cache entry."""

    def test_search_uses_a_distinct_cache_namespace(self):
        plain = email_route._get_cache_key('alice', 'all', include_read=False, scan_limit=25)
        searched = email_route._get_cache_key(
            'alice', 'all', include_read=False, scan_limit=25, search='invoice',
        )
        self.assertNotEqual(plain, searched)
        self.assertIn('search', searched)

    def test_different_search_terms_get_different_cache_keys(self):
        first = email_route._get_cache_key('alice', 'all', search='invoice')
        second = email_route._get_cache_key('alice', 'all', search='receipt')
        self.assertNotEqual(first, second)

    def test_search_key_is_case_and_accent_insensitive(self):
        # Matches _normalize_search_text's own lowercase + NFKD
        # strip-combining-marks behavior, so "HOA DON" and "hóa don" --
        # which a user would expect to mean the same search -- reuse the
        # same cache entry. (Vietnamese "d with stroke" specifically has no
        # NFKD decomposition to plain "d", a separate, narrower quirk of
        # _normalize_search_text that's outside this fix's scope.)
        accented = email_route._get_cache_key('alice', 'all', search='hóa don')
        plain = email_route._get_cache_key('alice', 'all', search='HOA DON')
        self.assertEqual(accented, plain)


class GetUnreadEmailsSearchRouteTests(unittest.TestCase):
    """End-to-end: a cache-miss search request must call Gmail with the
    search term in the query, and must not apply a local post-filter that
    could drop a Gmail match whose only hit was in body text this route's
    email dicts don't carry."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='test-secret')
        self.app.register_blueprint(email_route.email_bp)
        self.client = self.app.test_client()

    def test_search_request_queries_gmail_with_the_keyword_and_keeps_its_matches(self):
        service = MagicMock()
        gmail_match = {
            'id': 'm1', 'sender': 'a@x.com', 'subject': 'Unrelated subject',
            'snippet': 'no keyword here', 'date': '', 'body': '',
        }
        service.get_emails.return_value = [gmail_match]
        # _hydrate_email_for_list does its own DB/cache-detail lookups
        # unrelated to what this test is about (whether the search term
        # reaches Gmail, and whether the result Gmail returned survives to
        # the response) -- stub it as a passthrough so those internals
        # can't make this test fragile.
        with (
            patch.object(email_route, 'get_current_user_id', return_value='alice'),
            patch.object(email_route, 'get_user_db_path', return_value='alice.db'),
            patch.object(email_route, '_get_cached_emails', return_value=(None, None)),
            patch.object(email_route.Cache, 'get', return_value=None),
            patch.object(email_route.Cache, 'set'),
            patch.object(email_route.Cache, 'get_many', return_value={}),
            patch.object(email_route, '_cache_emails'),
            patch.object(email_route, '_load_gmail_service', return_value=service),
            patch.object(email_route, '_store_meeting_suggestions', return_value=[]),
            patch.object(email_route, '_safe_pending_meeting_suggestions', return_value=[]),
            patch.object(email_route, '_hydrate_email_for_list', side_effect=lambda email, *a, **k: email),
        ):
            response = self.client.get('/api/email/get-unread?search=invoice&max_results=20&filter=all')

        self.assertEqual(200, response.status_code)
        service.get_emails.assert_called_once()
        called_query = service.get_emails.call_args.kwargs['query']
        self.assertIn('invoice', called_query)
        # The one email Gmail returned doesn't literally contain "invoice"
        # in any locally-checked field -- proving there's no local
        # re-filter silently dropping it (it's kept because Gmail already
        # decided it matched, e.g. on body text this route never inspects
        # locally).
        body = response.get_json()
        self.assertEqual(['m1'], [e['id'] for e in body['emails']])


if __name__ == '__main__':
    unittest.main()
