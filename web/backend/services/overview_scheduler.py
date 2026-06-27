import logging
import os
import threading
import time
from datetime import datetime

from config import Config
from models.schedule import LOCAL_TZ
from models.user import User
from services.overview_service import refresh_daily_overview_async

logger = logging.getLogger(__name__)
_started = False
_started_lock = threading.Lock()


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
    while True:
        try:
            now = datetime.now(LOCAL_TZ)
            if now.hour == 6 and now.minute == 30 and last_run_date != now.date():
                last_run_date = now.date()
                _refresh_all_users(now.date())
        except Exception:
            logger.warning("Overview scheduler loop failed", exc_info=True)
        time.sleep(60)


def _refresh_all_users(day):
    user_ids = User.list_user_ids(connected_only=False, limit=500)
    logger.info("Refreshing daily overview for %s users on %s", len(user_ids), day)
    for user_id in user_ids:
        refresh_daily_overview_async(user_id, day=day, force=True)
