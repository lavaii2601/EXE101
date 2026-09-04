"""Manual Status Reports (Phase 3, design doc section 8.5).

Template is Done/Doing/Blocked/Next/Risks. No Bob-AI-drafting in this
slice -- every report starts as a draft the author fills in and edits
themselves; wiring a chat-agent that pre-fills a draft from task/project
data is deferred to a later slice.

Publish is one-way: once `status` flips to 'published' the five text
fields become immutable (update_draft refuses to touch a published
report). This is what makes "nguoi dung phai review truoc khi gui" (the
user must review before publishing) meaningful -- the review gate is the
only chance to change the content, matching how workspace_audit_events is
append-only elsewhere in this codebase. A draft may only be deleted by its
own author; a published report may only be deleted by workspace
owner/admin (never the original author), so an author can't quietly erase
business-record evidence after publishing.
"""

from models import postgres_db as pg

STATUSES = ("draft", "published")
VISIBILITIES = ("workspace", "private")
_TEXT_FIELDS = ("done_text", "doing_text", "blocked_text", "next_text", "risks_text")


class StatusReportError(RuntimeError):
    """Raised for expected, user-facing failures (not found, not editable, etc.)."""

    def __init__(self, code, **extra):
        super().__init__(code)
        self.code = code
        self.extra = extra


def _require_pg():
    if not pg.enabled():
        raise RuntimeError("Status reports require Postgres (DATABASE_URL)")


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


def create_draft(workspace_id, author_user_id, project_id=None, report_date=None,
                  visibility="workspace", done_text="", doing_text="", blocked_text="",
                  next_text="", risks_text=""):
    if visibility not in VISIBILITIES:
        raise StatusReportError("invalid_visibility")
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO status_reports (
                workspace_id, project_id, author_user_id, report_date, visibility,
                done_text, doing_text, blocked_text, next_text, risks_text,
                created_by_user_id, updated_by_user_id
            )
            VALUES (%s, %s, %s, COALESCE(%s, CURRENT_DATE), %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (workspace_id, project_id, author_user_id, report_date, visibility,
             done_text, doing_text, blocked_text, next_text, risks_text,
             author_user_id, author_user_id),
        ).fetchone()
        report = pg.normalize_row(row)
        _record_audit_event(
            conn, workspace_id, author_user_id, "status_report_drafted",
            target_type="status_report", target_id=str(report["id"]),
        )
        return report


def get_report(workspace_id, report_id):
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM status_reports
            WHERE id = %s AND workspace_id = %s AND deleted_at IS NULL
            """,
            (report_id, workspace_id),
        ).fetchone()
        return pg.normalize_row(row)


def is_report_visible(report, caller_user_id, caller_role):
    if caller_role in ("owner", "admin"):
        return True
    if report.get("author_user_id") == caller_user_id:
        return True
    return report.get("status") == "published" and report.get("visibility") == "workspace"


def update_draft(workspace_id, report_id, actor_user_id, project_id=None, report_date=None,
                  visibility=None, done_text=None, doing_text=None, blocked_text=None,
                  next_text=None, risks_text=None):
    if visibility is not None and visibility not in VISIBILITIES:
        raise StatusReportError("invalid_visibility")
    _require_pg()
    existing = get_report(workspace_id, report_id)
    if existing is None:
        raise StatusReportError("report_not_found")
    if existing["author_user_id"] != actor_user_id or existing["status"] != "draft":
        raise StatusReportError("report_not_editable")
    fields = ["updated_by_user_id = %s"]
    params = [actor_user_id]
    for column, value in (
        ("project_id", project_id), ("report_date", report_date), ("visibility", visibility),
        ("done_text", done_text), ("doing_text", doing_text), ("blocked_text", blocked_text),
        ("next_text", next_text), ("risks_text", risks_text),
    ):
        if value is not None:
            fields.append(f"{column} = %s")
            params.append(value)
    params.extend([report_id, workspace_id])
    with pg.connection() as conn:
        row = conn.execute(
            f"""
            UPDATE status_reports SET {', '.join(fields)}
            WHERE id = %s AND workspace_id = %s AND status = 'draft' AND deleted_at IS NULL
            RETURNING *
            """,
            tuple(params),
        ).fetchone()
        return pg.normalize_row(row)


def publish_report(workspace_id, report_id, actor_user_id):
    _require_pg()
    existing = get_report(workspace_id, report_id)
    if existing is None:
        raise StatusReportError("report_not_found")
    if existing["author_user_id"] != actor_user_id or existing["status"] != "draft":
        raise StatusReportError("report_not_editable")
    if not any((existing.get(field) or "").strip() for field in _TEXT_FIELDS):
        raise StatusReportError("report_empty")
    with pg.connection() as conn:
        row = conn.execute(
            """
            UPDATE status_reports
            SET status = 'published', published_at = NOW(), updated_by_user_id = %s
            WHERE id = %s AND workspace_id = %s AND status = 'draft' AND deleted_at IS NULL
            RETURNING *
            """,
            (actor_user_id, report_id, workspace_id),
        ).fetchone()
        if row is None:
            raise StatusReportError("report_not_editable")
        report = pg.normalize_row(row)
        _record_audit_event(
            conn, workspace_id, actor_user_id, "status_report_published",
            target_type="status_report", target_id=str(report_id),
        )
        return report


def delete_report(workspace_id, report_id, actor_user_id, caller_role):
    _require_pg()
    existing = get_report(workspace_id, report_id)
    if existing is None:
        raise StatusReportError("report_not_found")
    if existing["status"] == "draft":
        if existing["author_user_id"] != actor_user_id:
            raise StatusReportError("report_not_author")
    elif caller_role not in ("owner", "admin"):
        raise StatusReportError("insufficient_role")
    with pg.connection() as conn:
        row = conn.execute(
            """
            UPDATE status_reports SET deleted_at = NOW(), updated_by_user_id = %s
            WHERE id = %s AND workspace_id = %s AND deleted_at IS NULL
            RETURNING id
            """,
            (actor_user_id, report_id, workspace_id),
        ).fetchone()
        if row is None:
            return False
        _record_audit_event(
            conn, workspace_id, actor_user_id, "status_report_deleted",
            target_type="status_report", target_id=str(report_id),
        )
        return True


def list_reports(workspace_id, caller_user_id, caller_role, project_id=None, author_user_id=None, status=None):
    _require_pg()
    query = "SELECT * FROM status_reports WHERE workspace_id = %s AND deleted_at IS NULL"
    params = [workspace_id]
    if caller_role not in ("owner", "admin"):
        query += " AND (author_user_id = %s OR (status = 'published' AND visibility = 'workspace'))"
        params.append(caller_user_id)
    if project_id:
        query += " AND project_id = %s"
        params.append(project_id)
    if author_user_id:
        query += " AND author_user_id = %s"
        params.append(author_user_id)
    if status:
        query += " AND status = %s"
        params.append(status)
    query += " ORDER BY report_date DESC, created_at DESC"
    with pg.connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return pg.normalize_rows(rows)
