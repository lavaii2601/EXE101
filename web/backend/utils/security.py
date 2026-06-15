import time
from collections import defaultdict, deque

from flask import current_app, request, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


_request_buckets = defaultdict(deque)


def _serializer():
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="flowmate-mobile-auth-v1",
    )


def issue_mobile_token(user_id):
    return _serializer().dumps({"sub": user_id, "type": "mobile"})


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
    return payload.get("sub")


def bearer_user_id():
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    return verify_mobile_token(authorization[7:].strip())


def authenticated_user_id():
    return bearer_user_id() or session.get("gmail_user_email") or session.get("user_id")


def enforce_rate_limit():
    if request.method == "OPTIONS":
        return None

    limit = current_app.config.get("RATE_LIMIT_PER_MINUTE", 180)
    if request.path.startswith("/api/chat/") or request.path.startswith("/api/email/summary"):
        limit = current_app.config.get("AI_RATE_LIMIT_PER_MINUTE", 30)

    identity = bearer_user_id() or request.remote_addr or "unknown"
    key = (identity, request.path)
    now = time.monotonic()
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
    if bearer_user_id():
        return True
    if request.path == "/api/email/google-auth":
        return True

    origin = request.headers.get("Origin")
    if not origin:
        return False
    return origin in current_app.config.get("ALLOWED_ORIGINS", [])
