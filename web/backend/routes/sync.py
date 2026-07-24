import os

from flask import Blueprint, current_app, g, jsonify, request, session

from models.workspace_sync import WORKSPACE_SYNC_DOMAINS, WorkspaceSync
from utils.security import authenticated_user_id
from utils.user_context import get_current_user_id, get_user_db_path, sanitize_user_id


sync_bp = Blueprint("workspace_sync", __name__, url_prefix="/api/sync")

_OAUTH_COMPLETION_PATHS = {
    "/api/email/google-auth",
    "/api/email/oauth2callback",
}
_SYNC_STATE_PATH = "/api/sync/state"
_MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_DOMAIN_SET = frozenset(WORKSPACE_SYNC_DOMAINS)


def _poll_after_ms():
    try:
        configured = int(os.getenv("WORKSPACE_SYNC_POLL_AFTER_MS", "10000"))
    except (TypeError, ValueError):
        configured = 10000
    return max(2000, min(configured, 60000))


def _parse_since(value, current_revision):
    try:
        since = int(value)
    except (TypeError, ValueError):
        since = 0
    if since < 0 or since > current_revision:
        return 0
    return since


def _json_payload(response):
    try:
        payload = response.get_json(silent=True)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ordered_domains(values):
    selected = {
        str(value or "").strip().lower()
        for value in (values or ())
        if str(value or "").strip().lower() in _DOMAIN_SET
    }
    return tuple(domain for domain in WORKSPACE_SYNC_DOMAINS if domain in selected)


def mutation_domains_for_response(response):
    """Map a successful API mutation to workspace domains it invalidates."""
    path = request.path.rstrip("/") or "/"
    method = request.method.upper()
    is_oauth_completion = path in _OAUTH_COMPLETION_PATHS

    if path == _SYNC_STATE_PATH:
        return ()
    if method not in _MUTATION_METHODS and not (
        method == "GET" and is_oauth_completion
    ):
        return ()
    if response.status_code < 200 or response.status_code >= 400:
        return ()

    payload = _json_payload(response)
    if payload.get("success") is False:
        return ()

    domains = set()
    if path == "/api/chat/message":
        domains.update(("chat", "history"))
        domains.update(_ordered_domains(payload.get("refresh_targets")))
        if payload.get("schedule_created"):
            domains.update(("schedule", "calendar", "overview"))
        if payload.get("action_applied"):
            domains.update(_ordered_domains(payload.get("refresh_targets")))
    elif path in {
        "/api/chat/summarize-email",
        "/api/chat/generate-reply",
    }:
        domains.add("history")
    elif path == "/api/chat/send-drafted-reply":
        domains.update(("email", "history", "overview"))
    elif path.startswith("/api/chat/sessions/"):
        domains.update(("chat", "history"))
    elif path in {"/api/chat/clear", "/api/chat/clear-all"}:
        domains.update(("chat", "history"))
    elif path in _OAUTH_COMPLETION_PATHS or path == "/api/email/logout":
        domains.update(
            (
                "email",
                "schedule",
                "calendar",
                "overview",
                "profile",
                "settings",
            )
        )
    elif path == "/api/email/cache/clear":
        # Cache eviction changes no durable workspace data.
        return ()
    elif path.startswith("/api/email/meeting-suggestions"):
        domains.update(("email", "schedule", "overview"))
    elif path.startswith("/api/email/"):
        domains.update(("email", "history", "overview"))
    elif path == "/api/user/profile":
        domains.update(("profile", "settings"))
    elif path in {
        "/api/user/gmail-connected",
        "/api/user/gmail-disconnected",
    }:
        domains.update(
            (
                "email",
                "schedule",
                "calendar",
                "overview",
                "profile",
                "settings",
            )
        )
    elif path == "/api/schedule/checklist":
        domains.add("overview")
    elif path in {"/api/schedule/plan-day", "/api/schedule/parse-draft"}:
        # These endpoints only parse/suggest; applying a plan has its own URL.
        return ()
    elif path == "/api/schedule/quick-add":
        if payload.get("schedule_id") or payload.get("kind") == "activity":
            domains.update(("schedule", "calendar", "overview", "history"))
        elif payload.get("kind") == "task":
            domains.add("overview")
        else:
            return ()
    elif path.startswith("/api/schedule/"):
        domains.update(("schedule", "calendar", "overview", "history"))
    elif path.startswith("/api/calendar/"):
        domains.update(("schedule", "calendar", "overview", "history"))
    elif path == "/api/knowledge" or path.startswith("/api/knowledge/"):
        domains.add("knowledge")
    elif path.startswith("/api/_background/"):
        domains.update(("schedule", "calendar", "overview"))

    return _ordered_domains(domains)


def _captured_user_id():
    value = str(getattr(g, "workspace_sync_user_id", "") or "").strip()
    if value and value != "default":
        return value
    return ""


def _post_oauth_user_id():
    # OAuth callbacks can establish or switch identity during the route, after
    # the normal before_request capture ran. Prefer the newly written session
    # value over a stale pre-callback identity.
    value = session.get("user_id") or session.get("gmail_user_email")
    value = sanitize_user_id(value)
    return "" if value == "default" else value


def install_workspace_sync_hooks(app):
    """Install request identity capture and best-effort mutation invalidation."""
    if app.extensions.get("workspace_sync_hooks"):
        return
    app.extensions["workspace_sync_hooks"] = True

    @app.before_request
    def capture_workspace_sync_user():
        if not request.path.startswith("/api/"):
            return None
        if authenticated_user_id():
            user_id = get_current_user_id(request)
            if user_id and user_id != "default":
                g.workspace_sync_user_id = user_id
        return None

    @app.after_request
    def bump_workspace_sync_revision(response):
        domains = mutation_domains_for_response(response)
        if not domains:
            return response

        user_id = (
            _post_oauth_user_id()
            if request.path.rstrip("/") in _OAUTH_COMPLETION_PATHS
            else _captured_user_id()
        )
        if not user_id:
            return response

        try:
            WorkspaceSync.bump(
                user_id,
                domains,
                db_path=get_user_db_path(user_id),
            )
        except Exception:
            # The business mutation has already succeeded. Sync invalidation is
            # advisory and must not convert that success into a client retry.
            current_app.logger.exception(
                "Could not advance workspace sync revision for %s",
                request.path,
            )
        return response


@sync_bp.route("/state", methods=["GET"])
def get_workspace_sync_state():
    if not authenticated_user_id():
        return jsonify({"error": "not_authenticated"}), 401

    user_id = get_current_user_id(request)
    if not user_id or user_id == "default":
        return jsonify({"error": "not_authenticated"}), 401

    state = WorkspaceSync.get_state(
        user_id,
        db_path=get_user_db_path(user_id),
    )
    revision = state["revision"]
    since = _parse_since(request.args.get("since"), revision)
    domains = state["domains"]
    changed = [
        domain
        for domain in WORKSPACE_SYNC_DOMAINS
        if domains.get(domain, 0) > since
    ]
    return jsonify(
        {
            "success": True,
            "revision": revision,
            "domains": domains,
            "changed": changed,
            "poll_after_ms": _poll_after_ms(),
        }
    )
