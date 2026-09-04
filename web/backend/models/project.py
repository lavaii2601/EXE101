"""Shared Business-workspace projects (Phase 3 "Work Hub").

See WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md section 8.4 and
database/migrations/20260904_work_hub.sql for the schema this implements.
Postgres-only, same justification as models/workspace.py: project data is
inherently cross-user (a project must be visible to every member who can
see it, not just its creator), unlike per-user models such as
models/schedule.py.

Permission model: the design doc says a worker sees a project "theo
membership hoac quyen du an" (workspace membership OR a distinct
per-project permission). Rather than a separate project_members join
table, this module reuses `owner_user_id` as the single per-project
delegate -- a worker who owns a project can manage it without being
workspace admin/owner. Workspace membership (models/workspace.py) already
gates whether the caller can see the workspace at all; visibility='private'
projects are additionally restricted to their owner/creator plus
workspace owner/admin. See the plan doc / migration comment for the
full rationale and the deliberately deferred multi-member ACL follow-up.
"""

from models import postgres_db as pg

STATUSES = ("planning", "active", "on_hold", "completed", "archived")
VISIBILITIES = ("workspace", "private")


class ProjectError(RuntimeError):
    """Raised for expected, user-facing failures (bad status, not found, etc.)."""

    def __init__(self, code, **extra):
        super().__init__(code)
        self.code = code
        self.extra = extra


def _require_pg():
    if not pg.enabled():
        raise RuntimeError("Projects require Postgres (DATABASE_URL)")


def _record_audit_event(conn, workspace_id, actor_user_id, event_type,
                         target_type=None, target_id=None, metadata=None):
    """Insert an audit row using an already-open connection/transaction.

    Duplicated from models/workspace.py rather than imported, so the insert
    stays inside the caller's own transaction -- same rationale documented
    in models/workspace_subscription.py.
    """
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


def create_project(workspace_id, actor_user_id, name, description=None, status="planning",
                    visibility="workspace", owner_user_id=None, start_date=None, due_date=None):
    name = (name or "").strip()
    if not name:
        raise ProjectError("project_name_required")
    if status not in STATUSES:
        raise ProjectError("invalid_project_status")
    if visibility not in VISIBILITIES:
        raise ProjectError("invalid_visibility")
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO projects (
                workspace_id, name, description, status, visibility,
                owner_user_id, start_date, due_date,
                created_by_user_id, updated_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (workspace_id, name, description, status, visibility,
             owner_user_id, start_date, due_date, actor_user_id, actor_user_id),
        ).fetchone()
        project = pg.normalize_row(row)
        _record_audit_event(
            conn, workspace_id, actor_user_id, "project_created",
            target_type="project", target_id=str(project["id"]),
            metadata={"name": name},
        )
        return project


def get_project(workspace_id, project_id):
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM projects
            WHERE id = %s AND workspace_id = %s AND deleted_at IS NULL
            """,
            (project_id, workspace_id),
        ).fetchone()
        return pg.normalize_row(row)


def can_manage_project(project, caller_user_id, caller_role):
    """Whether the caller may PATCH/DELETE this project."""
    if caller_role in ("owner", "admin"):
        return True
    return project.get("owner_user_id") == caller_user_id


def is_project_visible(project, caller_user_id, caller_role):
    if caller_role in ("owner", "admin"):
        return True
    if project.get("visibility") == "workspace":
        return True
    return project.get("owner_user_id") == caller_user_id or project.get("created_by_user_id") == caller_user_id


def update_project(workspace_id, project_id, actor_user_id, name=None, description=None,
                    status=None, visibility=None, owner_user_id=None, start_date=None, due_date=None):
    if status is not None and status not in STATUSES:
        raise ProjectError("invalid_project_status")
    if visibility is not None and visibility not in VISIBILITIES:
        raise ProjectError("invalid_visibility")
    _require_pg()
    fields = ["updated_by_user_id = %s"]
    params = [actor_user_id]
    for column, value in (
        ("name", name), ("description", description), ("status", status),
        ("visibility", visibility), ("owner_user_id", owner_user_id),
        ("start_date", start_date), ("due_date", due_date),
    ):
        if value is not None:
            fields.append(f"{column} = %s")
            params.append(value)
    params.extend([project_id, workspace_id])
    with pg.connection() as conn:
        row = conn.execute(
            f"""
            UPDATE projects SET {', '.join(fields)}
            WHERE id = %s AND workspace_id = %s AND deleted_at IS NULL
            RETURNING *
            """,
            tuple(params),
        ).fetchone()
        if row is None:
            return None
        project = pg.normalize_row(row)
        _record_audit_event(
            conn, workspace_id, actor_user_id, "project_updated",
            target_type="project", target_id=str(project_id),
        )
        return project


def delete_project(workspace_id, project_id, actor_user_id):
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            """
            UPDATE projects SET deleted_at = NOW(), updated_by_user_id = %s
            WHERE id = %s AND workspace_id = %s AND deleted_at IS NULL
            RETURNING id
            """,
            (actor_user_id, project_id, workspace_id),
        ).fetchone()
        if row is None:
            return False
        _record_audit_event(
            conn, workspace_id, actor_user_id, "project_deleted",
            target_type="project", target_id=str(project_id),
        )
        return True


def list_projects(workspace_id, caller_user_id, caller_role, status=None):
    _require_pg()
    query = "SELECT * FROM projects WHERE workspace_id = %s AND deleted_at IS NULL"
    params = [workspace_id]
    if caller_role not in ("owner", "admin"):
        query += " AND (visibility = 'workspace' OR owner_user_id = %s OR created_by_user_id = %s)"
        params.extend([caller_user_id, caller_user_id])
    if status:
        query += " AND status = %s"
        params.append(status)
    query += " ORDER BY created_at DESC"
    with pg.connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return pg.normalize_rows(rows)
