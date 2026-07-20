from pathlib import Path

from web.backend.utils.google_service_cache import (
    get_cached_service,
    invalidate_cached_service,
)


class _FakeGoogleService:
    def __init__(self, kind):
        self.kind = kind
        self.service = object()


def test_cache_separates_gmail_and_calendar_for_the_same_token(tmp_path):
    token_file = Path(tmp_path) / 'google-token.pickle'
    token_file.write_bytes(b'token')

    gmail = get_cached_service(
        token_file,
        lambda: _FakeGoogleService('gmail'),
        service_kind='gmail',
    )
    calendar = get_cached_service(
        token_file,
        lambda: _FakeGoogleService('calendar'),
        service_kind='calendar',
    )

    assert gmail.kind == 'gmail'
    assert calendar.kind == 'calendar'
    assert gmail is not calendar


def test_invalidation_clears_every_service_for_the_token(tmp_path):
    token_file = Path(tmp_path) / 'google-token.pickle'
    token_file.write_bytes(b'token')

    first_gmail = get_cached_service(
        token_file,
        lambda: _FakeGoogleService('gmail'),
        service_kind='gmail',
    )
    first_calendar = get_cached_service(
        token_file,
        lambda: _FakeGoogleService('calendar'),
        service_kind='calendar',
    )

    invalidate_cached_service(token_file)

    next_gmail = get_cached_service(
        token_file,
        lambda: _FakeGoogleService('gmail'),
        service_kind='gmail',
    )
    next_calendar = get_cached_service(
        token_file,
        lambda: _FakeGoogleService('calendar'),
        service_kind='calendar',
    )

    assert next_gmail is not first_gmail
    assert next_calendar is not first_calendar
