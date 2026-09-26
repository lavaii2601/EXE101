"""Package split of the former monolithic schedule.py: this module imports
every submodule (so their @schedule_bp.route decorators actually register)
and re-exports schedule_bp plus every private name external modules import
today:
  - services/chat_agents/checklist_agents.py: _checklist_cache_key,
    _normalize_checklist_payload, _sort_custom_items,
    _CHECKLIST_CACHE_TTL_SECONDS
  - services/chat_agents/schedule_agents.py: _clear_schedule_cache,
    _sync_schedule_to_calendar_async, _delete_calendar_event_async,
    _prune_stale_duplicate_after_move_async, _build_suggested_day_plan
  - services/intent_orchestrator.py (deferred imports): _split_day_plan_entries,
    _extract_quick_time
  - app.py: schedule_bp
"""
from .shared import schedule_bp, _clear_schedule_cache
from .checklist import (
    _checklist_cache_key,
    _normalize_checklist_payload,
    _sort_custom_items,
    _CHECKLIST_CACHE_TTL_SECONDS,
)
from .gcal_sync import (
    _sync_schedule_to_calendar_async,
    _delete_calendar_event_async,
    _prune_stale_duplicate_after_move_async,
)
from .quickplan import (
    _build_suggested_day_plan,
    _split_day_plan_entries,
    _extract_quick_time,
)
from . import crud  # noqa: F401  (registers create/list/get/update/delete routes)

__all__ = [
    'schedule_bp',
    '_clear_schedule_cache',
    '_checklist_cache_key',
    '_normalize_checklist_payload',
    '_sort_custom_items',
    '_CHECKLIST_CACHE_TTL_SECONDS',
    '_sync_schedule_to_calendar_async',
    '_delete_calendar_event_async',
    '_prune_stale_duplicate_after_move_async',
    '_build_suggested_day_plan',
    '_split_day_plan_entries',
    '_extract_quick_time',
]
