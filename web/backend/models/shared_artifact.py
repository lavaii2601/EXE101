"""Privacy-first sharing: a user explicitly shares one piece of their own
personal data (an email summary, calendar event, etc.) into a Business
workspace (Phase 4, design doc section 9.7).

Nothing reaches this table without the sharer's own explicit
confirm-before-sharing step on the client (see routes/sharing.py) -- Bob
never auto-shares. Once a row exists, it is workspace content like any
other: owner/admin see it the same as project/report content (matches
models/project.py / models/status_report.py's visibility precedent). What
stays private is everything upstream of that -- owner/admin can never
query the source mailbox/calendar directly (routes/email.py and
routes/calendar.py have no workspace_id concept at all).

Content is immutable after creation (no update function) -- a shared
artifact is a point-in-time snapshot the user confirmed, like a published
status report. revoked_at is the only lifecycle transition, and revoke is
sharer-only: unlike workspace-authored content, this is someone's personal
data, so only the person who shared it can un-share it, not workspace
owner/admin.
"""

from models import postgres_db as pg

SOURCE_TYPES = ("email_summary", "calendar_event", "note", "document_reference")
VISIBILITIES = ("workspace", "private")


class ArtifactError(RuntimeError):
    """Raised for expected, user-facing failures (not found, wrong role, etc.)."""

    def __init__(self, code, **extra):
        super().__init__(code)
        self.code = code
        self.extra = extra


def _require_pg():
    if not pg.enabled():
        raise RuntimeError("Shared artifacts require Postgres (DATABASE_URL)")


def _record_audit_event(conn, workspace_id, actor_user_id, event_type,
                         target_type=None, target_id=None, metadata=None):
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


def create_artifact(workspace_id, actor_user_id, source_type, title, content, visibility="workspace"):
    if source_type not in SOURCE_TYPES:
        raise ArtifactError("invalid_source_type")
    if visibility not in VISIBILITIES:
        raise ArtifactError("invalid_visibility")
    title = (title or "").strip()
    if not title:
        raise ArtifactError("artifact_title_required")
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO shared_artifacts (
                workspace_id, source_type, source_owner_user_id, created_by_user_id,
                title, content, visibility
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (workspace_id, source_type, actor_user_id, actor_user_id,
             title, pg.json_value(content or {}), visibility),
        ).fetchone()
        artifact = pg.normalize_row(row)
        _record_audit_event(
            conn, workspace_id, actor_user_id, "artifact_shared",
            target_type="shared_artifact", target_id=str(artifact["id"]),
            metadata={"source_type": source_type, "title": title},
        )
        return artifact


def get_artifact(workspace_id, artifact_id):
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM shared_artifacts
            WHERE id = %s AND workspace_id = %s AND revoked_at IS NULL
            """,
            (artifact_id, workspace_id),
        ).fetchone()
        return pg.normalize_row(row)


def is_artifact_visible(artifact, caller_user_id, caller_role):
    if caller_role in ("owner", "admin"):
        return True
    if artifact.get("source_owner_user_id") == caller_user_id:
        return True
    return artifact.get("visibility") == "workspace"


def revoke_artifact(workspace_id, artifact_id, actor_user_id):
    _require_pg()
    existing = get_artifact(workspace_id, artifact_id)
    if existing is None:
        raise ArtifactError("artifact_not_found")
    if existing["source_owner_user_id"] != actor_user_id:
        raise ArtifactError("insufficient_role")
    with pg.connection() as conn:
        row = conn.execute(
            """
            UPDATE shared_artifacts SET revoked_at = NOW()
            WHERE id = %s AND workspace_id = %s AND revoked_at IS NULL
            RETURNING id
            """,
            (artifact_id, workspace_id),
        ).fetchone()
        if row is None:
            return False
        _record_audit_event(
            conn, workspace_id, actor_user_id, "artifact_revoked",
            target_type="shared_artifact", target_id=str(artifact_id),
        )
        return True


def list_artifacts(workspace_id, caller_user_id, caller_role, source_type=None):
    _require_pg()
    query = "SELECT * FROM shared_artifacts WHERE workspace_id = %s AND revoked_at IS NULL"
    params = [workspace_id]
    if caller_role not in ("owner", "admin"):
        query += " AND (source_owner_user_id = %s OR visibility = 'workspace')"
        params.append(caller_user_id)
    if source_type:
        query += " AND source_type = %s"
        params.append(source_type)
    query += " ORDER BY created_at DESC"
    with pg.connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return pg.normalize_rows(rows)


def list_my_shares(user_id):
    """Every artifact the caller has shared, across all their workspaces --
    the "Trung tam chia se" (Sharing Center) view. Not workspace-scoped:
    this is the user's own record of what they've shared, wherever they
    shared it."""
    _require_pg()
    with pg.connection() as conn:
        rows = conn.execute(
            """
            SELECT sa.*, w.name AS workspace_name
            FROM shared_artifacts sa
            JOIN workspaces w ON w.id = sa.workspace_id
            WHERE sa.source_owner_user_id = %s AND sa.revoked_at IS NULL
            ORDER BY sa.created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return pg.normalize_rows(rows)
