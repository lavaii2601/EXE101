import logging
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from flask import current_app, g, request, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


_request_buckets = defaultdict(deque)
# Railway runs gunicorn with --workers 1 --threads 4 (railpack.json), so
# concurrent requests really do share this process/dict -- without a lock,
# two threads can both read len(bucket) < limit before either appends,
# letting the limit be exceeded by a few requests right at the boundary.
_request_buckets_lock = threading.Lock()
_security_logger = logging.getLogger('flowmate.security')

# The WorkspaceError codes that mean "this request was denied access to a
# tenant/role it wasn't entitled to" -- Phase 5 runtime security monitoring
# (WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md section 15). Not every WorkspaceError
# is security-relevant (e.g. 'project_name_required' is just a validation
# error), so callers pass only these three codes through this path.
WORKSPACE_ACCESS_DENIED_CODES = frozenset({
    'membership_required', 'insufficient_role', 'workspace_not_found',
})


def log_workspace_access_denied(code, actor_user_id, requested_workspace_id):
    """One structured log line per denied cross-tenant/role attempt, so an
    operator can grep/alert on repeated attempts from one actor against a
    workspace they don't belong to. No new DB table this pass -- see
    routes/admin.py's audit-log endpoint for the separate, already-written
    workspace_audit_events trail of *successful* business-data mutations."""
    _security_logger.warning(
        "workspace_access_denied code=%s actor=%s workspace=%s endpoint=%s method=%s correlation_id=%s",
        code, actor_user_id, requested_workspace_id or '-', request.endpoint,
        request.method, getattr(g, 'correlation_id', '-'),
    )


def _serializer():
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="flowmate-mobile-auth-v1",
    )


def issue_mobile_token(user_id):
    # Embeds the account's *current* token_version so a later
    # increment_token_version() call (password change, "log out all
    # devices", suspected device loss) makes every token issued before that
    # point fail verify_mobile_token's check in active_authenticated_user_id
    # below -- without this, a signed mobile token has no revocation story
    # for its whole 30-day validity window.
    from models.user import User

    user = User.get(user_id)
    version = int((user or {}).get("token_version") or 0)
    return _serializer().dumps({"sub": user_id, "type": "mobile", "ver": version})


def verify_mobile_token(token):
    try:
        payload = _serializer().loads(
            token,
            max_age=current_app.config.get("MOBILE_TOKEN_MAX_AGE", 30 * 24 * 3600),
        )
    except (BadSignature, SignatureExpired):
        return None
    if payload.get("type") != "mobile":
        return None
    # Stashed for active_authenticated_user_id, which already fetches the
    # user row to check the account still exists -- comparing token_version
    # there costs no extra query. A token signed before this field existed
    # has no "ver" key, treated as version 0 (matches every account's
    # DEFAULT 0 column value, so no pre-existing token is force-invalidated
    # by this change alone).
    g._mobile_token_version = int(payload.get("ver") or 0)
    return payload.get("sub")


def bearer_user_id():
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    return verify_mobile_token(authorization[7:].strip())


def header_user_id():
    if not current_app.config.get("MOBILE_USER_HEADER_ENABLED", False):
        return None
    value = (request.headers.get("X-User-Id") or "").strip()
    if not value or len(value) > 256:
        return None
    return value


def header_workspace_id():
    """The active tenant, sent by every client as X-Workspace-Id once a
    workspace exists (see web/frontend/js/utils.js's apiFetch, mobile/src/api/
    client.js, mobile_flutter/lib/api/client.dart). Unlike header_user_id
    this isn't an identity bypass -- it only selects which already-
    authenticated caller's workspace to operate in -- so it needs no
    MOBILE_USER_HEADER_ENABLED gate. Membership is still verified downstream
    by models.workspace.resolve_context; a header naming a workspace the
    caller doesn't belong to is rejected there, not here.
    """
    value = (request.headers.get("X-Workspace-Id") or "").strip()
    if not value or len(value) > 64:
        return None
    return value


def authenticated_user_id():
    # Public auth-status requests may resolve the anonymous fallback as the
    # literal string ``default``. Never let that sentinel turn into an app
    # session accepted by the global API guard.
    for candidate in (
        bearer_user_id(),
        session.get("gmail_user_email"),
        session.get("user_id"),
        header_user_id(),
    ):
        value = str(candidate or "").strip()
        if value and value.lower() != "default":
            return value
    return None


def active_authenticated_user_id():
    """Return an authenticated principal only while its account exists.

    Mobile tokens and Flask cookies are signed but otherwise stateless. After
    permanent account deletion, an old token from another device must not be
    able to pass the global API guard and let a route recreate the user row.
    The result is cached for the request because rate limiting and the auth
    guard may both resolve identity.
    """
    cache_key = '_flowmate_active_authenticated_user_id'
    if hasattr(g, cache_key):
        return getattr(g, cache_key)

    candidate = authenticated_user_id()
    if not candidate:
        setattr(g, cache_key, None)
        return None

    # The explicitly enabled X-User-Id development escape hatch historically
    # creates users lazily. Keep that local/test behavior; production bearer
    # and cookie identities must resolve to an existing account.
    if (
        header_user_id() == candidate
        and not bearer_user_id()
        and not session.get('user_id')
        and not session.get('gmail_user_email')
    ):
        setattr(g, cache_key, candidate)
        return candidate

    try:
        from models.user import User

        user_row = User.get(candidate)
        active = candidate if user_row else None
        # Only bearer-token requests carry an embedded version (see
        # verify_mobile_token) -- cookie-session browser logins have no
        # token_version concept and skip this check entirely. A mismatch
        # means the token was issued before the account's last
        # increment_token_version() call (password change, "log out all
        # devices"), so treat it exactly like a deleted account: not
        # authenticated, rather than letting a stale token keep working for
        # the rest of its 30-day signature validity.
        if active and hasattr(g, '_mobile_token_version'):
            current_version = int((user_row or {}).get('token_version') or 0)
            if getattr(g, '_mobile_token_version') != current_version:
                active = None
    except Exception:
        _security_logger.exception(
            'Could not validate authenticated account existence for %s',
            candidate,
        )
        active = None
    setattr(g, cache_key, active)
    return active


def enforce_rate_limit():
    if request.method == "OPTIONS":
        return None

    limit = current_app.config.get("RATE_LIMIT_PER_MINUTE", 180)
    if request.path.startswith("/api/chat/") or request.path.startswith("/api/email/summary"):
        limit = current_app.config.get("AI_RATE_LIMIT_PER_MINUTE", 30)

    # authenticated_user_id() (not a standalone bearer/header check) so a
    # cookie-session browser login -- the primary auth path for this app --
    # is keyed by its own identity too, not lumped in with every other
    # cookie-session user behind the same IP (shared office/school NAT,
    # CGNAT, VPN exit). Falls back to the resolved client IP only for
    # truly unauthenticated requests (e.g. the login endpoint itself).
    identity = authenticated_user_id() or request.remote_addr or "unknown"
    key = (identity, request.path)
    now = time.monotonic()
    with _request_buckets_lock:
        bucket = _request_buckets[key]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= limit:
            return {"error": "rate_limit_exceeded"}, 429
        bucket.append(now)
    return None


def valid_request_origin():
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return True
    if bearer_user_id() or header_user_id():
        return True
    if request.path in ("/api/email/google-auth", "/api/auth/register", "/api/auth/login"):
        return True

    origin = request.headers.get("Origin")
    if not origin:
        return False
    if origin in current_app.config.get("ALLOWED_ORIGINS", []):
        return True

    parsed_origin = urlparse(origin)
    origin_host = parsed_origin.netloc.lower()
    request_hosts = {
        (request.host or "").lower(),
        (request.headers.get("X-Forwarded-Host") or "").split(",")[0].strip().lower(),
    }
    railway_domain = (current_app.config.get("RAILWAY_PUBLIC_DOMAIN") or "").lower()
    if railway_domain:
        request_hosts.add(railway_domain)

    return bool(origin_host and origin_host in request_hosts)
