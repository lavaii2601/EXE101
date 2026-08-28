"""Multi-tenant workspace, membership and invitation model.

See WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md section 9 for the full design
this implements the Phase 1 ("Foundation") slice of. Workspaces are
inherently cross-user (a membership row must be visible to both the invited
worker and the owner/admin who query it), so -- unlike per-user models such
as models/schedule.py -- there is no SQLite fallback here. This matches
models/subscription.py, which is Postgres-only for the same reason.

Naming note: this is unrelated to models/workspace_sync.py (WorkspaceSync),
which is a pre-existing per-user cross-device cache-invalidation cursor.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from models import postgres_db as pg

ROLES = ("owner", "admin", "worker")
INVITABLE_ROLES = ("admin", "worker")
MEMBERSHIP_ACTIVE_STATUSES = ("active",)
INVITATION_DEFAULT_TTL_DAYS = 14


class WorkspaceError(RuntimeError):
    """Raised for expected, user-facing failures (bad role, capacity, etc.)."""

    def __init__(self, code, **extra):
        super().__init__(code)
        self.code = code
        self.extra = extra


def _require_pg():
    if not pg.enabled():
        raise RuntimeError("Workspaces require Postgres (DATABASE_URL)")


def _hash_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def normalize_email(email):
    return (email or "").strip().lower()


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

def get_personal_workspace(user_id):
    """Return the caller's personal workspace row, or None if not yet created."""
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM workspaces
            WHERE owner_user_id = %s AND type = 'personal'
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return pg.normalize_row(row)


def ensure_personal_workspace(user_id, name=None):
    """Get-or-create the caller's personal workspace, idempotently.

    Relies on the partial unique index on (owner_user_id) WHERE type =
    'personal' to make concurrent calls safe: a second INSERT racing the
    first fails uniqueness and falls through to the SELECT below instead of
    creating a duplicate.
    """
    _require_pg()
    pg.ensure_user(user_id)
    with pg.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO workspaces (type, name, owner_user_id, status)
            VALUES ('personal', %s, %s, 'active')
            ON CONFLICT (owner_user_id) WHERE type = 'personal' DO NOTHING
            RETURNING *
            """,
            (name or "Personal", user_id),
        ).fetchone()
        if row is None:
            row = conn.execute(
                """
                SELECT * FROM workspaces
                WHERE owner_user_id = %s AND type = 'personal'
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        else:
            conn.execute(
                """
                INSERT INTO workspace_memberships (workspace_id, user_id, role, status)
                VALUES (%s, %s, 'owner', 'active')
                ON CONFLICT (workspace_id, user_id) DO NOTHING
                """,
                (row["id"], user_id),
            )
        return pg.normalize_row(row)


def create_business_workspace(owner_user_id, name):
    """Create a new Business workspace with its owner membership, atomically."""
    _require_pg()
    name = (name or "").strip()
    if not name:
        raise WorkspaceError("workspace_name_required")
    pg.ensure_user(owner_user_id)
    with pg.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO workspaces (type, name, owner_user_id, status)
            VALUES ('business', %s, %s, 'active')
            RETURNING *
            """,
            (name, owner_user_id),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO workspace_memberships (workspace_id, user_id, role, status)
            VALUES (%s, %s, 'owner', 'active')
            """,
            (row["id"], owner_user_id),
        )
        workspace = pg.normalize_row(row)
        _record_audit_event(conn, workspace["id"], owner_user_id, "workspace_created")
        return workspace


def get_workspace(workspace_id):
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            "SELECT * FROM workspaces WHERE id = %s",
            (workspace_id,),
        ).fetchone()
        return pg.normalize_row(row)


def update_workspace(workspace_id, actor_user_id, name=None, settings=None):
    """Update mutable workspace fields. Caller must already be checked as owner/admin."""
    _require_pg()
    fields = []
    params = []
    if name is not None:
        fields.append("name = %s")
        params.append(name)
    if settings is not None:
        fields.append("settings = %s")
        params.append(pg.json_value(settings))
    if not fields:
        return get_workspace(workspace_id)
    params.append(workspace_id)
    with pg.connection() as conn:
        row = conn.execute(
            f"UPDATE workspaces SET {', '.join(fields)} WHERE id = %s RETURNING *",
            tuple(params),
        ).fetchone()
        if row is None:
            return None
        workspace = pg.normalize_row(row)
        _record_audit_event(
            conn, workspace_id, actor_user_id, "workspace_updated",
            metadata={"fields": [f.split(" = ")[0] for f in fields]},
        )
        return workspace


def list_workspaces_for_user(user_id):
    """Every workspace the user has an active membership in, personal first."""
    _require_pg()
    with pg.connection() as conn:
        rows = conn.execute(
            """
            SELECT w.*, m.role AS member_role, m.status AS member_status
            FROM workspaces w
            JOIN workspace_memberships m ON m.workspace_id = w.id
            WHERE m.user_id = %s AND m.status = 'active'
            ORDER BY (w.type = 'personal') DESC, w.created_at ASC
            """,
            (user_id,),
        ).fetchall()
        return pg.normalize_rows(rows)


# ---------------------------------------------------------------------------
# Memberships
# ---------------------------------------------------------------------------

def get_membership(workspace_id, user_id):
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM workspace_memberships
            WHERE workspace_id = %s AND user_id = %s
            """,
            (workspace_id, user_id),
        ).fetchone()
        return pg.normalize_row(row)


def list_members(workspace_id):
    _require_pg()
    with pg.connection() as conn:
        rows = conn.execute(
            """
            SELECT m.*, u.name, u.email, u.avatar_url
            FROM workspace_memberships m
            JOIN users u ON u.user_id = m.user_id
            WHERE m.workspace_id = %s AND m.status = 'active'
            ORDER BY (m.role = 'owner') DESC, (m.role = 'admin') DESC, m.joined_at ASC
            """,
            (workspace_id,),
        ).fetchall()
        return pg.normalize_rows(rows)


def disable_member(workspace_id, target_user_id, actor_user_id):
    """Remove a member's access. Cannot disable the workspace owner this way."""
    _require_pg()
    with pg.connection() as conn:
        target = conn.execute(
            """
            SELECT * FROM workspace_memberships
            WHERE workspace_id = %s AND user_id = %s
            FOR UPDATE
            """,
            (workspace_id, target_user_id),
        ).fetchone()
        if target is None:
            raise WorkspaceError("membership_not_found")
        if target["role"] == "owner":
            raise WorkspaceError("cannot_disable_owner")
        row = conn.execute(
            """
            UPDATE workspace_memberships
            SET status = 'disabled', disabled_at = NOW()
            WHERE workspace_id = %s AND user_id = %s
            RETURNING *
            """,
            (workspace_id, target_user_id),
        ).fetchone()
        membership = pg.normalize_row(row)
        _record_audit_event(
            conn, workspace_id, actor_user_id, "member_disabled",
            target_type="user", target_id=target_user_id,
        )
        return membership


def update_member_role(workspace_id, target_user_id, new_role, actor_user_id):
    """Change a member's role. Cannot change the owner's role or grant owner."""
    _require_pg()
    if new_role not in INVITABLE_ROLES:
        raise WorkspaceError("invalid_role")
    with pg.connection() as conn:
        target = conn.execute(
            """
            SELECT * FROM workspace_memberships
            WHERE workspace_id = %s AND user_id = %s AND status = 'active'
            FOR UPDATE
            """,
            (workspace_id, target_user_id),
        ).fetchone()
        if target is None:
            raise WorkspaceError("membership_not_found")
        if target["role"] == "owner":
            raise WorkspaceError("cannot_change_owner_role")
        row = conn.execute(
            """
            UPDATE workspace_memberships
            SET role = %s
            WHERE workspace_id = %s AND user_id = %s
            RETURNING *
            """,
            (new_role, workspace_id, target_user_id),
        ).fetchone()
        membership = pg.normalize_row(row)
        _record_audit_event(
            conn, workspace_id, actor_user_id, "member_role_changed",
            target_type="user", target_id=target_user_id,
            metadata={"old_role": target["role"], "new_role": new_role},
        )
        return membership


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

def create_invitation(workspace_id, email, role, invited_by_user_id, ttl_days=INVITATION_DEFAULT_TTL_DAYS):
    if role not in INVITABLE_ROLES:
        raise WorkspaceError("invalid_role")
    email_normalized = normalize_email(email)
    if not email_normalized or "@" not in email_normalized:
        raise WorkspaceError("invalid_email")
    _require_pg()
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    with pg.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO workspace_invitations (
                workspace_id, email_normalized, role, status,
                token_hash, invited_by_user_id, expires_at
            )
            VALUES (%s, %s, %s, 'pending', %s, %s, %s)
            RETURNING *
            """,
            (workspace_id, email_normalized, role, token_hash, invited_by_user_id, expires_at),
        ).fetchone()
        invitation = pg.normalize_row(row)
        _record_audit_event(
            conn, workspace_id, invited_by_user_id, "invitation_created",
            target_type="invitation", target_id=str(invitation["id"]),
            metadata={"email": email_normalized, "role": role},
        )
        # The raw token is only ever available here -- only its hash is
        # persisted, so it can't be recovered from the database later.
        invitation["token"] = raw_token
        return invitation


def get_invitation(invitation_id):
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            "SELECT * FROM workspace_invitations WHERE id = %s",
            (invitation_id,),
        ).fetchone()
        return pg.normalize_row(row)


def find_invitation_by_token(raw_token):
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            "SELECT * FROM workspace_invitations WHERE token_hash = %s",
            (_hash_token(raw_token),),
        ).fetchone()
        return pg.normalize_row(row)


def accept_invitation(raw_token, user_id, user_email):
    """Accept an invitation. The invitee's verified login email must match it.

    Capacity checks (design doc section 6.4-6.5) are Phase 2 scope -- this
    Phase 1 version activates membership unconditionally once the invitation
    itself is valid.
    """
    _require_pg()
    pg.ensure_user(user_id)
    token_hash = _hash_token(raw_token)
    with pg.connection() as conn:
        invitation = conn.execute(
            "SELECT * FROM workspace_invitations WHERE token_hash = %s FOR UPDATE",
            (token_hash,),
        ).fetchone()
        if invitation is None:
            raise WorkspaceError("invitation_not_found")
        if invitation["status"] != "pending":
            raise WorkspaceError("invitation_not_pending", status=invitation["status"])
        expires_at = invitation["expires_at"]
        if expires_at and expires_at < datetime.now(timezone.utc):
            conn.execute(
                "UPDATE workspace_invitations SET status = 'expired' WHERE id = %s",
                (invitation["id"],),
            )
            raise WorkspaceError("invitation_expired")
        if normalize_email(user_email) != invitation["email_normalized"]:
            raise WorkspaceError("invitation_email_mismatch")

        conn.execute(
            """
            INSERT INTO workspace_memberships (workspace_id, user_id, role, status)
            VALUES (%s, %s, %s, 'active')
            ON CONFLICT (workspace_id, user_id) DO UPDATE
            SET role = EXCLUDED.role, status = 'active', disabled_at = NULL, removed_at = NULL
            """,
            (invitation["workspace_id"], user_id, invitation["role"]),
        )
        row = conn.execute(
            """
            UPDATE workspace_invitations
            SET status = 'accepted', accepted_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (invitation["id"],),
        ).fetchone()
        result = pg.normalize_row(row)
        _record_audit_event(
            conn, invitation["workspace_id"], user_id, "invitation_accepted",
            target_type="invitation", target_id=str(invitation["id"]),
        )
        return result


def decline_invitation(invitation_id, user_id, user_email):
    _require_pg()
    with pg.connection() as conn:
        invitation = conn.execute(
            "SELECT * FROM workspace_invitations WHERE id = %s FOR UPDATE",
            (invitation_id,),
        ).fetchone()
        if invitation is None:
            raise WorkspaceError("invitation_not_found")
        if normalize_email(user_email) != invitation["email_normalized"]:
            raise WorkspaceError("invitation_email_mismatch")
        if invitation["status"] != "pending":
            raise WorkspaceError("invitation_not_pending", status=invitation["status"])
        row = conn.execute(
            "UPDATE workspace_invitations SET status = 'declined' WHERE id = %s RETURNING *",
            (invitation_id,),
        ).fetchone()
        result = pg.normalize_row(row)
        _record_audit_event(
            conn, invitation["workspace_id"], user_id, "invitation_declined",
            target_type="invitation", target_id=str(invitation_id),
        )
        return result


def revoke_invitation(invitation_id, actor_user_id):
    _require_pg()
    with pg.connection() as conn:
        invitation = conn.execute(
            "SELECT * FROM workspace_invitations WHERE id = %s FOR UPDATE",
            (invitation_id,),
        ).fetchone()
        if invitation is None:
            raise WorkspaceError("invitation_not_found")
        if invitation["status"] != "pending":
            raise WorkspaceError("invitation_not_pending", status=invitation["status"])
        row = conn.execute(
            "UPDATE workspace_invitations SET status = 'revoked' WHERE id = %s RETURNING *",
            (invitation_id,),
        ).fetchone()
        result = pg.normalize_row(row)
        _record_audit_event(
            conn, invitation["workspace_id"], actor_user_id, "invitation_revoked",
            target_type="invitation", target_id=str(invitation_id),
        )
        return result


def list_invitations(workspace_id, status=None):
    _require_pg()
    query = "SELECT * FROM workspace_invitations WHERE workspace_id = %s"
    params = [workspace_id]
    if status:
        query += " AND status = %s"
        params.append(status)
    query += " ORDER BY created_at DESC"
    with pg.connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return pg.normalize_rows(rows)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def _record_audit_event(conn, workspace_id, actor_user_id, event_type,
                         target_type=None, target_id=None, metadata=None):
    """Insert an audit row using an already-open connection/transaction."""
    conn.execute(
        """
        INSERT INTO workspace_audit_events (
            workspace_id, actor_user_id, event_type, target_type, target_id, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (workspace_id, actor_user_id, event_type, target_type, target_id,
         pg.json_value(metadata or {})),
    )


def record_audit_event(workspace_id, actor_user_id, event_type,
                        target_type=None, target_id=None, metadata=None):
    """Insert an audit row in its own transaction (for callers outside one)."""
    _require_pg()
    with pg.connection() as conn:
        _record_audit_event(conn, workspace_id, actor_user_id, event_type,
                             target_type, target_id, metadata)


def list_audit_events(workspace_id, limit=100):
    _require_pg()
    with pg.connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM workspace_audit_events
            WHERE workspace_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (workspace_id, limit),
        ).fetchall()
        return pg.normalize_rows(rows)


# ---------------------------------------------------------------------------
# Tenant context resolution (used by every workspace-scoped route)
# ---------------------------------------------------------------------------

def resolve_context(user_id, requested_workspace_id=None):
    """Resolve which workspace a request should act on, and the caller's role.

    Mirrors design doc section 10.4's `resolve_access` shape for Phase 1
    (membership + role only -- subscription/feature-limit/ACL layers are
    Phase 2+). Backward-compatible: a client that sends no workspace_id is
    scoped to its personal workspace (creating it on first touch), matching
    section 13's migration-1 compatibility requirement.

    Returns (workspace, membership) or raises WorkspaceError with a stable
    `code` the caller can map to an HTTP status.
    """
    if not requested_workspace_id:
        workspace = ensure_personal_workspace(user_id)
        membership = get_membership(workspace["id"], user_id)
        return workspace, membership

    workspace = get_workspace(requested_workspace_id)
    if workspace is None:
        raise WorkspaceError("workspace_not_found")
    membership = get_membership(requested_workspace_id, user_id)
    if membership is None or membership["status"] != "active":
        raise WorkspaceError("membership_required")
    return workspace, membership
