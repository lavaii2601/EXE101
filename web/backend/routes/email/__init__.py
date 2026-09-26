"""Email routes package: OAuth login, Smart Inbox classification, meeting-
suggestion extraction, inbox listing/detail, mailbox actions, reply compose,
and the daily digest report.

Split of the former monolithic routes/email.py (2368 lines) into one
submodule per concern, all registering their routes against the single
shared `email_bp` Blueprint defined in shared.py:

- shared.py: the Blueprint, cache-key builders, TTL constants, and the
  text/date utilities shared by Smart Inbox + meeting extraction.
- oauth.py: OAuth state/PKCE storage, the Google Flow builder, profile
  fetch helpers, and the auth/login/logout routes.
- smart_inbox.py: the Action required/Waiting/FYI/Low priority heuristic.
- meeting.py: meeting-suggestion extraction/dedup/persistence and the
  /meeting-suggestions* routes.
- list.py: the /get-unread scan+cache+paginate pipeline, new-mail-check
  poll target, body/attachment/summary fetch, and cache admin endpoints.
- actions.py: mark read/unread, archive, trash.
- compose.py: send-reply.
- report.py: summarize-by-date.

Importing every submodule below is what actually registers their
`@email_bp.route(...)` decorators; nothing else in this file does that.
Python's import system also automatically binds each submodule as an
attribute of this package once imported (e.g. `routes.email.list`,
`routes.email.oauth`), independently of the `as _x` aliases below -- the
test suite relies on that for `patch.object(routes.email.<submodule>,
'<name>', ...)` targets (see note below).

Re-exports the names other modules reach into by their pre-split dotted
path (routes.email.<name>), so those call sites need no changes:
- `email_bp`: imported by web/backend/app.py to register the blueprint.
- `_clear_email_list_cache`: services/chat_agents/email_agents.py does a
  deferred `from routes.email import _clear_email_list_cache` inside
  `_mark_emails_apply` to avoid a circular import.
- `_extract_meeting_suggestion`, `_is_meeting_suggestion_stale`,
  `_prune_existing_meeting_suggestions`, `_store_meeting_suggestions`,
  `_gmail_query_for_email_list`, `_get_cache_key`, `_smart_inbox_bucket`,
  `_store_oauth_code_verifier`, `_mark_oauth_mobile`, `_consume_oauth_state`,
  and the `MeetingSuggestion`/`Cache`/`User`/`Config` classes plus the `pg`
  module: several tests (test_email_meeting_detection.py,
  test_email_search.py, test_oauth_state_security.py,
  test_sharing_management.py, test_admin_security.py,
  test_password_auth_parity.py) call or patch these by their pre-split
  dotted path. A class/module attribute patch (`MeetingSuggestion.<method>`,
  `Cache.<method>`, `User.<method>`, `Config.<attr>`, `pg.<attr>`) works
  unchanged once re-exported here, since it mutates the one shared
  class/module object every submodule's own reference also points to. A
  *function* patched via `patch.object(routes.email, 'name', ...)` would
  NOT work that way (the route handler that used to live in this flat
  module now does its own bare-name lookup inside whichever submodule it
  moved to), so those tests' patch targets were updated to the owning
  submodule instead (e.g. `routes.email.oauth._build_oauth_flow`,
  `routes.email.list._load_gmail_service`) -- the same pattern
  services/chat_agents' split used for `_build_workspace_context`. A
  *direct* call to a pure function (e.g. `routes.email._get_cache_key(...)`)
  has no such issue and keeps working once re-exported here, since the
  function's own body still resolves its own dependencies via its
  defining module's globals regardless of which name was used to call it.
"""
from config import Config  # noqa: F401
from models import postgres_db as pg  # noqa: F401
from models.cache import Cache  # noqa: F401
from models.meeting_suggestion import MeetingSuggestion  # noqa: F401
from models.user import User  # noqa: F401

from routes.email.shared import (  # noqa: F401
    email_bp,
    _clear_email_list_cache,
    _gmail_query_for_email_list,
    _get_cache_key,
)
from routes.email import oauth  # noqa: F401
from routes.email import smart_inbox  # noqa: F401
from routes.email import meeting  # noqa: F401
from routes.email import list as _list  # noqa: F401
from routes.email import actions  # noqa: F401
from routes.email import compose  # noqa: F401
from routes.email import report  # noqa: F401

from routes.email.smart_inbox import _smart_inbox_bucket  # noqa: F401
from routes.email.meeting import (  # noqa: F401
    _extract_meeting_suggestion,
    _is_meeting_suggestion_stale,
    _prune_existing_meeting_suggestions,
    _store_meeting_suggestions,
)
from routes.email.oauth import (  # noqa: F401
    _store_oauth_code_verifier,
    _mark_oauth_mobile,
    _consume_oauth_state,
)
