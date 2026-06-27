import logging
import os
import threading
import time
from datetime import datetime

from config import Config
from models.schedule import LOCAL_TZ
from models.user import User
from services.overview_service import check_and_refresh_if_new, refresh_daily_overview_async

logger = logging.getLogger(__name__)
_started = False
_started_lock = threading.Lock()

LIVE_CHECK_INTERVAL_SECONDS = 5 * 60


def start_overview_scheduler():
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
    last_run_date = None
    last_live_check = 0.0
    while True:
        try:
            now = datetime.now(LOCAL_TZ)
            if now.hour == 6 and now.minute == 30 and last_run_date != now.date():
                last_run_date = now.date()
                _refresh_all_users(now.date())

            if time.monotonic() - last_live_check >= LIVE_CHECK_INTERVAL_SECONDS:
                last_live_check = time.monotonic()
                _check_new_mail_for_active_overviews(now.date())
        except Exception:
            logger.warning("Overview scheduler loop failed", exc_info=True)
        time.sleep(60)


def _refresh_all_users(day):
    user_ids = User.list_user_ids(connected_only=False, limit=500)
    logger.info("Refreshing daily overview for %s users on %s", len(user_ids), day)
    for user_id in user_ids:
        refresh_daily_overview_async(user_id, day=day, force=True)


def _check_new_mail_for_active_overviews(day):
    """Top up today's cached overview for users who already have one (i.e.
    opened the Overview tab today) -- only re-runs the AI summary when new
    mail actually arrived, so idle days cost nothing.
    """
    user_ids = User.list_user_ids(connected_only=True, limit=500)
    for user_id in user_ids:
        try:
            check_and_refresh_if_new(user_id, day=day)
        except Exception:
            logger.warning("Live overview check failed for %s", user_id, exc_info=True)
