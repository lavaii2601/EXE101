"""Shared Business-workspace tasks (Phase 3 "Work Hub").

See WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md section 8.4 and
database/migrations/20260904_work_hub.sql. Postgres-only, same
justification as models/project.py. Every task belongs to a project;
its own visibility narrows (never widens) the project's visibility --
a 'private' task inside an otherwise 'workspace'-visible project stays
restricted to its assignee/creator/owner-admin, but a 'workspace' task
inside a 'private' project is still only visible to whoever can see that
project.
"""

from models import postgres_db as pg
from models import project as project_model

STATUSES = ("todo", "in_progress", "blocked", "done", "cancelled")
PRIORITIES = ("low", "medium", "high", "urgent")
VISIBILITIES = ("workspace", "private")


class TaskError(RuntimeError):
    """Raised for expected, user-facing failures (bad status, not found, etc.)."""

    def __init__(self, code, **extra):
        super().__init__(code)
        self.code = code
        self.extra = extra


def _require_pg():
    if not pg.enabled():
        raise RuntimeError("Tasks require Postgres (DATABASE_URL)")


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


def create_task(workspace_id, project_id, actor_user_id, title, description=None, status="todo",
                 priority="medium", visibility="workspace", assignee_user_id=None,
                 due_date=None, blocker=None):
    title = (title or "").strip()
    if not title:
        raise TaskError("task_title_required")
    if status not in STATUSES:
        raise TaskError("invalid_task_status")
    if priority not in PRIORITIES:
        raise TaskError("invalid_task_priority")
    if visibility not in VISIBILITIES:
        raise TaskError("invalid_visibility")
    _require_pg()
    project = project_model.get_project(workspace_id, project_id)
    if project is None:
        raise TaskError("project_not_found")
    with pg.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO tasks (
                workspace_id, project_id, title, description, status, priority,
                visibility, assignee_user_id, due_date, blocker,
                created_by_user_id, updated_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (workspace_id, project_id, title, description, status, priority,
             visibility, assignee_user_id, due_date, blocker if status == "blocked" else None,
             actor_user_id, actor_user_id),
        ).fetchone()
        task = pg.normalize_row(row)
        _record_audit_event(
            conn, workspace_id, actor_user_id, "task_created",
            target_type="task", target_id=str(task["id"]),
            metadata={"title": title, "project_id": str(project_id)},
        )
        return task


def get_task(workspace_id, task_id):
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM tasks
            WHERE id = %s AND workspace_id = %s AND deleted_at IS NULL
            """,
            (task_id, workspace_id),
        ).fetchone()
        return pg.normalize_row(row)


def can_manage_task(task, project, caller_user_id, caller_role):
    if caller_role in ("owner", "admin"):
        return True
    if project_model.can_manage_project(project, caller_user_id, caller_role):
        return True
    return task.get("assignee_user_id") == caller_user_id or task.get("created_by_user_id") == caller_user_id


def is_task_visible(task, project, caller_user_id, caller_role):
    if caller_role in ("owner", "admin"):
        return True
    if task.get("assignee_user_id") == caller_user_id or task.get("created_by_user_id") == caller_user_id:
        return True
    if task.get("visibility") != "workspace":
        return False
    return project_model.is_project_visible(project, caller_user_id, caller_role)


def update_task(workspace_id, task_id, actor_user_id, title=None, description=None, status=None,
                 priority=None, visibility=None, assignee_user_id=None, due_date=None, blocker=None):
    if status is not None and status not in STATUSES:
        raise TaskError("invalid_task_status")
    if priority is not None and priority not in PRIORITIES:
        raise TaskError("invalid_task_priority")
    if visibility is not None and visibility not in VISIBILITIES:
        raise TaskError("invalid_visibility")
    _require_pg()
    fields = ["updated_by_user_id = %s"]
    params = [actor_user_id]
    for column, value in (
        ("title", title), ("description", description), ("priority", priority),
        ("visibility", visibility), ("assignee_user_id", assignee_user_id), ("due_date", due_date),
    ):
        if value is not None:
            fields.append(f"{column} = %s")
            params.append(value)
    if status is not None:
        fields.append("status = %s")
        params.append(status)
        # A task leaving 'blocked' no longer has a live blocker reason.
        if status != "blocked":
            fields.append("blocker = NULL")
        elif blocker is not None:
            fields.append("blocker = %s")
            params.append(blocker)
    elif blocker is not None:
        fields.append("blocker = %s")
        params.append(blocker)
    params.extend([task_id, workspace_id])
    with pg.connection() as conn:
        row = conn.execute(
            f"""
            UPDATE tasks SET {', '.join(fields)}
            WHERE id = %s AND workspace_id = %s AND deleted_at IS NULL
            RETURNING *
            """,
            tuple(params),
        ).fetchone()
        if row is None:
            return None
        task = pg.normalize_row(row)
        _record_audit_event(
            conn, workspace_id, actor_user_id, "task_updated",
            target_type="task", target_id=str(task_id),
        )
        return task


def delete_task(workspace_id, task_id, actor_user_id):
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            """
            UPDATE tasks SET deleted_at = NOW(), updated_by_user_id = %s
            WHERE id = %s AND workspace_id = %s AND deleted_at IS NULL
            RETURNING id
            """,
            (actor_user_id, task_id, workspace_id),
        ).fetchone()
        if row is None:
            return False
        _record_audit_event(
            conn, workspace_id, actor_user_id, "task_deleted",
            target_type="task", target_id=str(task_id),
        )
        return True


def list_tasks(workspace_id, caller_user_id, caller_role, project_id=None, status=None, assignee_user_id=None):
    _require_pg()
    query = """
        SELECT t.* FROM tasks t
        JOIN projects p ON p.id = t.project_id
        WHERE t.workspace_id = %s AND t.deleted_at IS NULL AND p.deleted_at IS NULL
    """
    params = [workspace_id]
    if caller_role not in ("owner", "admin"):
        query += """
            AND (
                t.assignee_user_id = %s OR t.created_by_user_id = %s
                OR (
                    t.visibility = 'workspace'
                    AND (p.visibility = 'workspace' OR p.owner_user_id = %s OR p.created_by_user_id = %s)
                )
            )
        """
        params.extend([caller_user_id, caller_user_id, caller_user_id, caller_user_id])
    if project_id:
        query += " AND t.project_id = %s"
        params.append(project_id)
    if status:
        query += " AND t.status = %s"
        params.append(status)
    if assignee_user_id:
        query += " AND t.assignee_user_id = %s"
        params.append(assignee_user_id)
    query += " ORDER BY t.due_date ASC NULLS LAST, t.created_at DESC"
    with pg.connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return pg.normalize_rows(rows)
