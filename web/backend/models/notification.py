"""In-app notifications (Phase 6, design doc section 9.9).

Written by services/subscription_lifecycle_scheduler.py (renewal reminders,
grace/read-only transitions) and read by routes/notifications.py. Postgres-
only, same justification as every other workspace-era table this session:
notifications are a production/Business concern, no SQLite parity needed.
"""

from models import postgres_db as pg

SEVERITIES = ("info", "warning", "critical")


def create(recipient_user_id, dedupe_key, type_, title, body=None, severity="info",
           workspace_id=None, action_url=None, expires_at=None):
    """Idempotent fire-and-forget insert. ON CONFLICT DO NOTHING means a
    caller never needs to pre-check whether this exact (recipient,
    dedupe_key) notification already exists -- the constraint does that.
    No-op (not an error) when Postgres isn't configured, matching every
    other Postgres-only model in this codebase."""
    if not pg.enabled():
        return
    if severity not in SEVERITIES:
        severity = "info"
    with pg.connection() as conn:
        conn.execute(
            """
            INSERT INTO notifications (
                recipient_user_id, workspace_id, type, severity, title, body,
                action_url, dedupe_key, expires_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (recipient_user_id, dedupe_key) DO NOTHING
            """,
            (recipient_user_id, workspace_id, type_, severity, title, body,
             action_url, dedupe_key, expires_at),
        )


def list_for_user(user_id, limit=50, unread_only=False):
    """Unread first, then newest first. Excludes expired rows."""
    if not pg.enabled() or not user_id:
        return []
    query = (
        "SELECT * FROM notifications WHERE recipient_user_id = %s "
        "AND (expires_at IS NULL OR expires_at > NOW())"
    )
    params = [user_id]
    if unread_only:
        query += " AND read_at IS NULL"
    query += " ORDER BY (read_at IS NULL) DESC, created_at DESC LIMIT %s"
    params.append(limit)
    with pg.connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return pg.normalize_rows(rows)


def count_unread(user_id):
    if not pg.enabled() or not user_id:
        return 0
    with pg.connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total FROM notifications
            WHERE recipient_user_id = %s AND read_at IS NULL
              AND (expires_at IS NULL OR expires_at > NOW())
            """,
            (user_id,),
        ).fetchone()
        return int(row["total"]) if row else 0


def mark_read(user_id, notification_id):
    """True if notification_id exists and belongs to user_id (idempotent --
    an already-read notification still reports True, keeping its original
    read_at rather than bumping it). False for "not found" or "belongs to
    someone else" alike, so the route layer never leaks which case it was."""
    if not pg.enabled() or not user_id:
        return False
    with pg.connection() as conn:
        row = conn.execute(
            """
            UPDATE notifications SET read_at = COALESCE(read_at, NOW())
            WHERE id = %s AND recipient_user_id = %s
            RETURNING id
            """,
            (notification_id, user_id),
        ).fetchone()
        return row is not None
