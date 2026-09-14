"""Phase 6 ("Billing automation and production hardening", design doc
section 15/9.11): the one scheduled job the subscription lifecycle needs.

Access-state correctness never depended on this job -- get_access_state()
(models/workspace_subscription.py) and get_active() (models/subscription.py)
both compute live from current_period_end/grace_period_ends_at on every
read. This job exists purely for:
  1. status-column hygiene (flip 'active' to 'expired' once a subscription
     is truly done, so admin views/queries filtering on status aren't
     permanently stale), and
  2. in-app renewal reminders and grace/read-only-entered notifications
     (email delivery is explicitly deferred per design doc section 16's
     already-approved decision -- v1 is in-app only).

Mirrors services/overview_scheduler.py's exact shape: a daemon thread,
started once per process (guarded against Flask's debug-mode double-start),
looping with a plain time.sleep. Idempotency comes entirely from
notifications' UNIQUE(recipient_user_id, dedupe_key) constraint (see
models/notification.create), not from this module tracking state itself --
every pass re-derives "what's true right now" from the subscriptions table
and lets the constraint decide whether a notification is actually new.
"""

import logging
import os
import threading
import time
from datetime import datetime, timezone

from config import Config
from models import notification as notification_model
from models import subscription as subscription_model
from models import workspace_subscription as workspace_subscription_model
from models.workspace_subscription import ACCESS_ACTIVE, ACCESS_GRACE, ACCESS_READ_ONLY

logger = logging.getLogger(__name__)
_started = False
_started_lock = threading.Lock()

RUN_INTERVAL_SECONDS = 60 * 60
REMINDER_WINDOW_DAYS = 3


def start_subscription_lifecycle_scheduler():
    global _started
    if Config.DEBUG and os.getenv('WERKZEUG_RUN_MAIN') != 'true':
        return False
    with _started_lock:
        if _started:
            return False
        _started = True

    threading.Thread(target=_scheduler_loop, daemon=True).start()
    return True


def _scheduler_loop():
    while True:
        try:
            run_lifecycle_pass()
        except Exception:
            logger.warning("Subscription lifecycle scheduler pass failed", exc_info=True)
        time.sleep(RUN_INTERVAL_SECONDS)


def run_lifecycle_pass():
    """One full pass. Split out from _scheduler_loop so it can be called
    directly (e.g. from tests) without waiting on the sleep loop."""
    _expire_lapsed_personal()
    _remind_personal_expiring_soon()
    _process_workspace_subscriptions()


def _as_aware(value):
    """Duplicated from models/workspace_subscription.py's identical private
    helper rather than imported -- same cross-module-private-helper
    avoidance already established for _record_audit_event in that file."""
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


def _period_end_date(value):
    """ISO date string for a dedupe key -- stable across repeated passes
    within the same billing period, changes on renewal, so a subscription
    that later laps again (new current_period_end) gets a fresh reminder
    instead of being permanently suppressed by an old dedupe_key."""
    parsed = _as_aware(value)
    return parsed.date().isoformat() if parsed else "none"


def _expire_lapsed_personal():
    lapsed = subscription_model.list_lapsed()
    if not lapsed:
        return
    updated = subscription_model.mark_expired([row["id"] for row in lapsed])
    if updated:
        logger.info("Subscription lifecycle: expired %s lapsed personal subscription(s)", updated)


def _remind_personal_expiring_soon():
    for row in subscription_model.list_expiring_soon(days=REMINDER_WINDOW_DAYS):
        period_end = _period_end_date(row.get("current_period_end"))
        plan_label = row.get("plan_name") or row.get("plan_code") or "Premium"
        notification_model.create(
            recipient_user_id=row["user_id"],
            dedupe_key=f"sub_reminder:{row['id']}:{period_end}",
            type_="subscription_renewal_reminder",
            severity="warning",
            title="Gói Premium sắp hết hạn",
            body=f"Gói {plan_label} của bạn sẽ hết hạn vào {period_end}. Gia hạn ngay để không bị gián đoạn.",
            action_url="/app?page=settings",
        )


def _process_workspace_subscriptions():
    to_expire = []
    for row in workspace_subscription_model.list_all_with_owner():
        owner_id = row.get("workspace_owner_user_id")
        workspace_id = row.get("workspace_id")
        if not owner_id or not workspace_id:
            continue
        state = row.get("access_state")
        period_end = _period_end_date(row.get("current_period_end"))

        if state == ACCESS_GRACE:
            notification_model.create(
                recipient_user_id=owner_id,
                workspace_id=workspace_id,
                dedupe_key=f"workspace_grace:{row['id']}:{period_end}",
                type_="workspace_subscription_grace",
                severity="warning",
                title="Subscription doanh nghiệp đã hết hạn",
                body="Không gian doanh nghiệp của bạn đang trong 7 ngày gia hạn. Gia hạn trước khi hết hạn để tránh chuyển sang chế độ chỉ đọc.",
                action_url="/app?page=settings",
            )
        elif state == ACCESS_READ_ONLY:
            notification_model.create(
                recipient_user_id=owner_id,
                workspace_id=workspace_id,
                dedupe_key=f"workspace_read_only:{row['id']}:{period_end}",
                type_="workspace_subscription_read_only",
                severity="critical",
                title="Subscription doanh nghiệp đã chuyển sang chỉ đọc",
                body="Thời gian gia hạn đã hết. Không gian doanh nghiệp hiện chỉ đọc cho tới khi gia hạn.",
                action_url="/app?page=settings",
            )
            to_expire.append(row["id"])
        elif state == ACCESS_ACTIVE:
            end = _as_aware(row.get("current_period_end"))
            if end and (end - datetime.now(timezone.utc)).days <= REMINDER_WINDOW_DAYS:
                notification_model.create(
                    recipient_user_id=owner_id,
                    workspace_id=workspace_id,
                    dedupe_key=f"workspace_reminder:{row['id']}:{period_end}",
                    type_="workspace_subscription_renewal_reminder",
                    severity="warning",
                    title="Subscription doanh nghiệp sắp hết hạn",
                    body=f"Subscription của không gian doanh nghiệp sẽ hết hạn vào {period_end}. Gia hạn ngay để giữ quyền truy cập đầy đủ cho cả nhóm.",
                    action_url="/app?page=settings",
                )

    if to_expire:
        updated = workspace_subscription_model.mark_expired(to_expire)
        if updated:
            logger.info("Subscription lifecycle: expired %s past-grace workspace subscription(s)", updated)
