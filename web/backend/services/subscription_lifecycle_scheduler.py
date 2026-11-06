"""Phase 6 ("Billing automation and production hardening", design doc
section 15/9.11): the one scheduled job the subscription lifecycle needs.

Access-state correctness never depended on this job -- get_active()
(models/subscription.py) computes live from current_period_end on every
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
