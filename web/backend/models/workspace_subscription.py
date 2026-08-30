"""Business workspace subscriptions: seats, grace period, access state.

Phase 2 ("Subscription/Seat/Entitlement Foundation") of
WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md, sections 6 and 9.4-9.5. Extends the
same `subscriptions` table models/subscription.py already uses for personal
Premium -- a row belongs to exactly one of user_id (personal) or
workspace_id (business), enforced by the subscriptions_subject_check
constraint. This module only ever touches workspace_id rows;
models/subscription.py is untouched and keeps owning personal Premium
exactly as before.

Deliberately self-contained (no import of models.workspace) so
models/workspace.py can import this module for the seat-capacity check in
accept_invitation without a circular import.
"""

from datetime import datetime, timedelta, timezone

from models import postgres_db as pg

ACCESS_ACTIVE = "active"
ACCESS_GRACE = "grace"
ACCESS_READ_ONLY = "read_only"
ACCESS_NONE = "none"

GRACE_PERIOD_DAYS = 7
# A Business workspace gets 10 seats just by existing (design doc section
# 6.3), even before any subscription row has been granted -- so a fresh
# workspace can invite its first teammates without an admin/payment step
# first. Once a subscription row exists, its own included_seats/extra_seats
# take over entirely (see _seat_capacity).
DEFAULT_BUSINESS_INCLUDED_SEATS = 10
PURCHASE_ACTIONS = ("purchase", "renew")


class WorkspaceSubscriptionError(RuntimeError):
    """Raised for expected, user-facing failures (capacity, bad state, etc.)."""

    def __init__(self, code, **extra):
        super().__init__(code)
        self.code = code
        self.extra = extra


def _require_pg():
    if not pg.enabled():
        raise RuntimeError("Workspace subscriptions require Postgres (DATABASE_URL)")


def _as_aware(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _record_audit_event(conn, workspace_id, actor_user_id, event_type,
                         target_type=None, target_id=None, metadata=None):
    """Insert an audit row using an already-open connection/transaction.

    Duplicated from models/workspace.py's identical helper rather than
    imported, to keep this module import-free of models.workspace (see
    module docstring)."""
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


def get_access_state(subscription):
    """Compute Business access state from a subscription row (section 6.6-6.8).

    Always derived from current_period_end/grace_period_ends_at at call
    time, per section 6.7's explicit requirement that access must be
    correct even if the scheduled expiry job hasn't run yet -- callers must
    not cache this beyond a single request.
    """
    if subscription is None:
        return ACCESS_NONE
    if subscription.get("status") == "suspended":
        return ACCESS_READ_ONLY
    period_end = _as_aware(subscription.get("current_period_end"))
    if period_end is None:
        # No expiry set (e.g. an indefinite manual grant) -- treat as active.
        return ACCESS_ACTIVE
    now = datetime.now(timezone.utc)
    if now <= period_end:
        return ACCESS_ACTIVE
    grace_end = _as_aware(subscription.get("grace_period_ends_at")) or (
        period_end + timedelta(days=GRACE_PERIOD_DAYS)
    )
    if now <= grace_end:
        return ACCESS_GRACE
    return ACCESS_READ_ONLY


def _decorate(row):
    normalized = pg.normalize_row(row)
    if not normalized:
        return None
    normalized["access_state"] = get_access_state(normalized)
    normalized["seat_capacity"] = (
        (normalized.get("included_seats") or 0) + (normalized.get("extra_seats") or 0)
    )
    return normalized


def get_current(workspace_id):
    """Most recent Business subscription row for a workspace, regardless of
    lapsed/canceled status -- access state is computed separately from this
    row's period_end/grace fields, not by filtering on status here."""
    if not workspace_id or not pg.enabled():
        return None
    with pg.connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM subscriptions
            WHERE workspace_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()
        return _decorate(row)


def _seat_capacity(conn, workspace_id):
    """Read seat capacity using an already-open connection/transaction."""
    row = conn.execute(
        """
        SELECT included_seats, extra_seats FROM subscriptions
        WHERE workspace_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (workspace_id,),
    ).fetchone()
    if row is None:
        return DEFAULT_BUSINESS_INCLUDED_SEATS
    return (row["included_seats"] or 0) + (row["extra_seats"] or 0)


def get_seat_capacity(workspace_id):
    _require_pg()
    with pg.connection() as conn:
        return _seat_capacity(conn, workspace_id)


def count_active_seats(workspace_id):
    _require_pg()
    with pg.connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM workspace_memberships
            WHERE workspace_id = %s AND status = 'active'
            """,
            (workspace_id,),
        ).fetchone()
        return int(pg.normalize_row(row)["n"])


def check_seat_capacity_locked(conn, workspace_id):
    """Lock the workspace row, then return (active_seats, capacity, has_room).

    Call inside a transaction that will insert/activate a membership row
    right after, so two concurrent invitation acceptances for the same
    workspace serialize on this lock instead of both slipping past capacity
    (design doc section 6.5). The `workspaces` row is used as the lock
    target -- unlike the subscriptions row, it always exists, even for a
    Business workspace that hasn't been granted a subscription yet and is
    still on the default seat count. Mirrors models/subscription.py's
    grant_manual, which locks the `users` row for the same reason.
    """
    conn.execute("SELECT id FROM workspaces WHERE id = %s FOR UPDATE", (workspace_id,))
    capacity = _seat_capacity(conn, workspace_id)
    active = conn.execute(
        """
        SELECT COUNT(*) AS n FROM workspace_memberships
        WHERE workspace_id = %s AND status = 'active'
        """,
        (workspace_id,),
    ).fetchone()["n"]
    return active, capacity, active < capacity


def ensure_seat_request(conn, workspace_id, invitation_id, requested_by_user_id, requested_seats=1):
    """Idempotently record that this workspace needs more seats.

    Re-attempting acceptance of the same capacity-blocked invitation must
    not create duplicate pending_owner rows (section 6.5's idempotency
    requirement) -- reuse the existing pending_owner request tied to this
    invitation if there is one.
    """
    existing = conn.execute(
        """
        SELECT * FROM workspace_seat_requests
        WHERE invitation_id = %s AND status = 'pending_owner'
        LIMIT 1
        """,
        (invitation_id,),
    ).fetchone()
    if existing is not None:
        return pg.normalize_row(existing)
    row = conn.execute(
        """
        INSERT INTO workspace_seat_requests (
            workspace_id, invitation_id, requested_seats, requested_by_user_id, status
        )
        VALUES (%s, %s, %s, %s, 'pending_owner')
        RETURNING *
        """,
        (workspace_id, invitation_id, requested_seats, requested_by_user_id),
    ).fetchone()
    return pg.normalize_row(row)


def list_seat_requests(workspace_id, status=None):
    _require_pg()
    query = "SELECT * FROM workspace_seat_requests WHERE workspace_id = %s"
    params = [workspace_id]
    if status:
        query += " AND status = %s"
        params.append(status)
    query += " ORDER BY created_at DESC"
    with pg.connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return pg.normalize_rows(rows)


def approve_seat_request(request_id, approved_by_user_id, added_seats=None):
    """Grant additional seats and let the blocked invitation be retried.

    The invitation goes back to 'pending' rather than being auto-activated
    here -- the invitee still completes acceptance themselves through the
    normal accept_invitation path, so the email-match check always runs.
    """
    _require_pg()
    with pg.connection() as conn:
        request = conn.execute(
            "SELECT * FROM workspace_seat_requests WHERE id = %s FOR UPDATE",
            (request_id,),
        ).fetchone()
        if request is None:
            raise WorkspaceSubscriptionError("seat_request_not_found")
        if request["status"] != "pending_owner":
            raise WorkspaceSubscriptionError("seat_request_not_pending", status=request["status"])
        seats = int(added_seats or request["requested_seats"])

        subscription = conn.execute(
            """
            SELECT * FROM subscriptions
            WHERE workspace_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            FOR UPDATE
            """,
            (request["workspace_id"],),
        ).fetchone()
        if subscription is None:
            raise WorkspaceSubscriptionError("workspace_subscription_not_found")
        conn.execute(
            "UPDATE subscriptions SET extra_seats = extra_seats + %s WHERE id = %s",
            (seats, subscription["id"]),
        )
        row = conn.execute(
            """
            UPDATE workspace_seat_requests
            SET status = 'approved', approved_by_user_id = %s
            WHERE id = %s
            RETURNING *
            """,
            (approved_by_user_id, request_id),
        ).fetchone()
        if request["invitation_id"]:
            conn.execute(
                """
                UPDATE workspace_invitations
                SET status = 'pending'
                WHERE id = %s AND status = 'capacity_blocked'
                """,
                (request["invitation_id"],),
            )
        result = pg.normalize_row(row)
        _record_audit_event(
            conn, request["workspace_id"], approved_by_user_id, "seat_request_approved",
            target_type="seat_request", target_id=str(request_id),
            metadata={"added_seats": seats},
        )
        return result


def reject_seat_request(request_id, actor_user_id):
    _require_pg()
    with pg.connection() as conn:
        request = conn.execute(
            "SELECT * FROM workspace_seat_requests WHERE id = %s FOR UPDATE",
            (request_id,),
        ).fetchone()
        if request is None:
            raise WorkspaceSubscriptionError("seat_request_not_found")
        if request["status"] != "pending_owner":
            raise WorkspaceSubscriptionError("seat_request_not_pending", status=request["status"])
        row = conn.execute(
            "UPDATE workspace_seat_requests SET status = 'rejected' WHERE id = %s RETURNING *",
            (request_id,),
        ).fetchone()
        result = pg.normalize_row(row)
        _record_audit_event(
            conn, request["workspace_id"], actor_user_id, "seat_request_rejected",
            target_type="seat_request", target_id=str(request_id),
        )
        return result


def grant_manual(workspace_id, plan_code, plan_name=None, billing_interval="monthly",
                  unit_amount=0, currency="VND", included_seats=DEFAULT_BUSINESS_INCLUDED_SEATS,
                  days=30, action=None, actor_user_id=None):
    """Purchase or renew a Business subscription (admin-manual path).

    Mirrors models/subscription.py's grant_manual for personal Premium --
    same provider='manual' placeholder until a real payment gateway is
    wired up, at which point a webhook would insert/update rows the same
    shape this produces.
    """
    _require_pg()
    requested_action = str(action or "").strip().lower() or None
    if requested_action and requested_action not in PURCHASE_ACTIONS:
        raise ValueError("invalid_subscription_action")

    with pg.connection() as conn:
        # The workspace row is the per-workspace transaction lock, exactly
        # like check_seat_capacity_locked -- it serializes two grant/renew
        # requests that arrive before either creates a row.
        conn.execute("SELECT id FROM workspaces WHERE id = %s FOR UPDATE", (workspace_id,))
        current = conn.execute(
            """
            SELECT * FROM subscriptions
            WHERE workspace_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            FOR UPDATE
            """,
            (workspace_id,),
        ).fetchone()
        current_normalized = pg.normalize_row(current) if current else None
        active = current if (
            current_normalized and get_access_state(current_normalized) in (ACCESS_ACTIVE, ACCESS_GRACE)
        ) else None

        allowed_action = "renew" if active else "purchase"
        if requested_action and requested_action != allowed_action:
            code = (
                "subscription_already_active"
                if allowed_action == "renew"
                else "no_active_subscription"
            )
            raise WorkspaceSubscriptionError(
                code, allowed_action=allowed_action, subscription=_decorate(active),
            )

        if active:
            row = conn.execute(
                """
                UPDATE subscriptions
                SET plan_code = %s,
                    plan_name = %s,
                    status = 'active',
                    billing_interval = %s,
                    currency = %s,
                    unit_amount = %s,
                    current_period_end =
                        GREATEST(COALESCE(current_period_end, NOW()), NOW())
                        + (%s || ' days')::INTERVAL,
                    grace_period_ends_at = NULL,
                    included_seats = GREATEST(included_seats, %s),
                    cancel_at_period_end = FALSE,
                    canceled_at = NULL
                WHERE id = %s
                RETURNING *
                """,
                (plan_code, plan_name, billing_interval, currency, unit_amount, days,
                 included_seats, active["id"]),
            ).fetchone()
            entitlement_action = "renew"
        else:
            row = conn.execute(
                """
                INSERT INTO subscriptions (
                    workspace_id, provider, plan_code, plan_name, status,
                    billing_interval, currency, unit_amount, included_seats,
                    current_period_start, current_period_end
                )
                VALUES (
                    %s, 'manual', %s, %s, 'active',
                    %s, %s, %s, %s,
                    NOW(), NOW() + (%s || ' days')::INTERVAL
                )
                RETURNING *
                """,
                (workspace_id, plan_code, plan_name, billing_interval, currency,
                 unit_amount, included_seats, days),
            ).fetchone()
            entitlement_action = "purchase"

        result = _decorate(row)
        result["entitlement_action"] = entitlement_action
        event_type = "subscription_renewed" if entitlement_action == "renew" else "subscription_purchased"
        _record_audit_event(
            conn, workspace_id, actor_user_id, event_type,
            metadata={"plan_code": plan_code, "included_seats": included_seats},
        )
        return result


def revoke(workspace_id, actor_user_id=None):
    """Cancel the workspace's current subscription, if any."""
    _require_pg()
    with pg.connection() as conn:
        cur = conn.execute(
            """
            UPDATE subscriptions
            SET status = 'canceled', canceled_at = NOW()
            WHERE workspace_id = %s AND status IN ('trialing', 'active', 'past_due')
            """,
            (workspace_id,),
        )
        if cur.rowcount > 0:
            _record_audit_event(conn, workspace_id, actor_user_id, "subscription_canceled")
        return cur.rowcount > 0
