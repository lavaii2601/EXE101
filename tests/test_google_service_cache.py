import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.google_service_cache import (  # noqa: E402
    get_cached_service,
    invalidate_cached_service,
)


class _FakeGoogleService:
    def __init__(self, kind):
        self.kind = kind
        self.service = object()


class GoogleServiceCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.token_file = Path(self.temp_dir.name) / 'google-token.json'
        self.token_file.write_bytes(b'token')

    def test_cache_separates_gmail_and_calendar_for_the_same_token(self):
        gmail = get_cached_service(
            self.token_file, lambda: _FakeGoogleService('gmail'), service_kind='gmail',
        )
        calendar = get_cached_service(
            self.token_file, lambda: _FakeGoogleService('calendar'), service_kind='calendar',
        )

        self.assertEqual('gmail', gmail.kind)
        self.assertEqual('calendar', calendar.kind)
        self.assertIsNot(gmail, calendar)

    def test_invalidation_clears_every_service_for_the_token(self):
        first_gmail = get_cached_service(
            self.token_file, lambda: _FakeGoogleService('gmail'), service_kind='gmail',
        )
        first_calendar = get_cached_service(
            self.token_file, lambda: _FakeGoogleService('calendar'), service_kind='calendar',
        )

        invalidate_cached_service(self.token_file)

        next_gmail = get_cached_service(
            self.token_file, lambda: _FakeGoogleService('gmail'), service_kind='gmail',
        )
        next_calendar = get_cached_service(
            self.token_file, lambda: _FakeGoogleService('calendar'), service_kind='calendar',
        )

        self.assertIsNot(first_gmail, next_gmail)
        self.assertIsNot(first_calendar, next_calendar)

    def test_same_thread_reuses_the_same_instance(self):
        # The whole point of this cache: a thread handling several requests
        # in a row for the same user shouldn't pay a fresh auth/TLS cost
        # each time.
        first = get_cached_service(
            self.token_file, lambda: _FakeGoogleService('gmail'), service_kind='gmail',
        )
        second = get_cached_service(
            self.token_file, lambda: _FakeGoogleService('gmail'), service_kind='gmail',
        )
        self.assertIs(first, second)

    def test_different_threads_never_share_the_same_service_instance(self):
        # Regression test: gunicorn runs this app with multiple gthread
        # worker threads in one process. The cache used to key only on
        # (token_file, service_kind), so two threads handling concurrent
        # requests for the same user got back the SAME service instance --
        # and therefore the same underlying httplib2 Http object. httplib2
        # is not safe for concurrent use of one instance from multiple
        # threads; sharing it corrupted the connection's C-level state and
        # crashed the whole worker process ("double free or corruption"),
        # taking every other in-flight request down with it. Each thread
        # must get its own instance.
        results = {}
        barrier = threading.Barrier(2)

        def worker(name):
            barrier.wait()
            results[name] = get_cached_service(
                self.token_file, lambda: _FakeGoogleService('gmail'), service_kind='gmail',
            )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertIsNot(results[0], results[1])

    def test_a_missing_token_file_returns_none_without_caching(self):
        missing = Path(self.temp_dir.name) / 'does-not-exist.json'
        result = get_cached_service(
            missing, lambda: _FakeGoogleService('gmail'), service_kind='gmail',
        )
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
