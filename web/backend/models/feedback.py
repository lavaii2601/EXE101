"""User feedback: free-text feedback a logged-in user submits from the app.

Written by routes/feedback.py, read by routes/admin.py for the read-only
admin dashboard list. Postgres-only -- no SQLite parity needed for this
table, matching models/notification.py's precedent.
"""

from models import postgres_db as pg


def create(user_id, message):
    """No-op (not an error) when Postgres isn't configured, matching every
    other Postgres-only model in this codebase."""
    if not pg.enabled():
        return
    with pg.connection() as conn:
        conn.execute(
            "INSERT INTO feedback (user_id, message) VALUES (%s, %s)",
            (user_id, message),
        )


def list_recent(limit=200):
    """Newest first. 200 is generous for an admin skimming the inbox-style
    list while still bounding one query -- this feature has no pagination
    UI yet, so the cap is the only thing standing between a slow month and
    an unbounded SELECT."""
    if not pg.enabled():
        return []
    with pg.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM feedback ORDER BY created_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
        return pg.normalize_rows(rows)
