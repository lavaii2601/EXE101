"""Schedule-domain chat agents: create/update/delete/list plus the shared
suggest-a-day-plan agent, and the private calendar/time-window helpers they
use."""
import os
import logging
from datetime import datetime, timedelta

from services.calendar_service import CalendarService
from models.history import History
from models.schedule import Schedule, LOCAL_TZ
from utils.user_context import get_user_token_file
from routes.schedule import (
    _clear_schedule_cache,
    _sync_schedule_to_calendar_async,
    _delete_calendar_event_async,
    _prune_stale_duplicate_after_move_async,
    _build_suggested_day_plan,
)

from .common import (
    intent_orchestrator,
    AgentResult,
    _wrap_direct_result,
    _normalize_intent_text,
)

logger = logging.getLogger(__name__)


def _calendar_window(message):
    normalized = _normalize_intent_text(message)
    now = datetime.now().astimezone()
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Reuse IntentOrchestrator's date parser (handles "20/7", "20/07/2026",
    # and "ngay 20 thang 7") instead of duplicating that regex here -- this
    # is the fallback path used when no window entity made it through (see
    # _window_override_from_entities), so it must recognize the same explicit
    # dates the orchestrator does, not just the today/this-week keywords below.
    explicit_date = intent_orchestrator._explicit_date_from_text(normalized)
    if explicit_date:
        start = datetime.combine(explicit_date, datetime.min.time()).replace(tzinfo=LOCAL_TZ)
        label = f"NGÀY {start.strftime('%d/%m/%Y')}"
        return start, start + timedelta(days=1), label

    if 'tuan truoc' in normalized or 'last week' in normalized:
        return monday - timedelta(days=7), monday, 'TUẦN TRƯỚC'
    if 'tuan nay' in normalized or 'this week' in normalized:
        return monday, monday + timedelta(days=7), 'TUẦN NÀY'
    if 'tuan sau' in normalized or 'next week' in normalized:
        return monday + timedelta(days=7), monday + timedelta(days=14), 'TUẦN SAU'
    if 'hom qua' in normalized or 'yesterday' in normalized:
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1), 'HÔM QUA'
    if 'hom nay' in normalized or 'today' in normalized:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1), 'HÔM NAY'

    return now, now + timedelta(days=30), 'SẮP TỚI'


def _parse_schedule_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TZ)
        return parsed.astimezone(LOCAL_TZ)
    except (TypeError, ValueError):
        return None


def _format_user_datetime(value, fallback='Khong xac dinh'):
    parsed = _parse_schedule_datetime(value)
    if not parsed:
        return fallback
    return parsed.strftime('%d/%m/%Y. %H:%M')


def _format_user_date(value, fallback='Khong xac dinh'):
    parsed = _parse_schedule_datetime(value)
    if parsed:
        return parsed.strftime('%d/%m/%Y')
    try:
        return datetime.fromisoformat(str(value)).date().strftime('%d/%m/%Y')
    except (TypeError, ValueError):
        return fallback


def _schedule_response_key(title, start_value):
    start_dt = _parse_schedule_datetime(start_value)
    normalized_title = ' '.join(str(title or '').strip().lower().split())
    normalized_start = start_dt.strftime('%Y-%m-%dT%H:%M') if start_dt else str(start_value or '').strip()
    return normalized_title, normalized_start


def _format_schedule_response_time(start_value, end_value):
    start_dt = _parse_schedule_datetime(start_value)
    end_dt = _parse_schedule_datetime(end_value)
    if not start_dt:
        return 'Khong xac dinh'
    start_text = _format_user_datetime(start_value)
    if end_dt:
        if end_dt.date() == start_dt.date():
            return f'{start_text} - {end_dt.strftime("%H:%M")} (GMT+7)'
        return f'{start_text} - {_format_user_datetime(end_value)} (GMT+7)'
    return f'{start_text} (GMT+7)'


def _format_calendar_context(message, user_id, db_path, window_override=None):
    if window_override:
        window_start, window_end, window_label = window_override
    else:
        window_start, window_end, window_label = _calendar_window(message)
    lines = [
        f"LICH VA SU KIEN {window_label}",
        f"Khoang thoi gian: {_format_user_date(window_start)} den {_format_user_date(window_end - timedelta(days=1))}",
    ]
    token_file = get_user_token_file(user_id)
    google_events = []
    if token_file and os.path.exists(token_file):
        google_events = CalendarService(token_file=token_file).get_events(
            max_results=50,
            time_min=window_start.replace(tzinfo=LOCAL_TZ).isoformat(),
            time_max=window_end.replace(tzinfo=LOCAL_TZ).isoformat()
        )
    local_schedules = Schedule.get_between(
        window_start.isoformat(),
        window_end.isoformat(),
        limit=100,
        db_path=db_path
    )

    if not google_events and not local_schedules:
        return "\n".join(lines + [f"Khong co lich hoac su kien trong {window_label.lower()}."])

    items_by_key = {}
    for event in google_events:
        key = _schedule_response_key(event.get('title'), event.get('start'))
        if key not in items_by_key:
            items_by_key[key] = {
                'title': event.get('title') or '(Khong co tieu de)',
                'start': event.get('start'),
                'end': event.get('end'),
                'location': event.get('location') or '',
                'status': '',
            }

    for schedule in local_schedules:
        key = _schedule_response_key(schedule.get('title'), schedule.get('start_time'))
        if key in items_by_key:
            existing = items_by_key[key]
            existing['status'] = existing.get('status') or schedule.get('status') or ''
            existing['location'] = existing.get('location') or schedule.get('location') or ''
            continue
        items_by_key[key] = {
            'title': schedule.get('title') or '(Khong co tieu de)',
            'start': schedule.get('start_time'),
            'end': schedule.get('end_time'),
            'location': schedule.get('location') or '',
            'status': schedule.get('status') or '',
        }

    items = sorted(
        items_by_key.values(),
        key=lambda item: (
            _parse_schedule_datetime(item.get('start')) or datetime.max.replace(tzinfo=LOCAL_TZ),
            item.get('title') or ''
        )
    )
    if not items:
        return "\n".join(lines + [f"Khong co lich hoac su kien trong {window_label.lower()}."])

    for item_index, item in enumerate(items, start=1):
        lines.append(f"{item_index}. {item.get('title')}")
        lines.append(f"   Thoi gian: {_format_schedule_response_time(item.get('start'), item.get('end'))}")
        if item.get('location'):
            lines.append(f"   Dia diem: {item.get('location')}")
        if item.get('status') and item.get('status') != 'pending':
            lines.append(f"   Trang thai: {item.get('status')}")
    return "\n".join(lines)


_SCHEDULE_ACTION_STOPWORDS = (
    'doi', 'sua', 'cap nhat', 'thay doi', 'chuyen', 'xoa', 'huy', 'bo lich',
    'cancel', 'delete', 'tao', 'dat', 'them', 'add', 'book', 'nhac toi', 'remind',
)
_SCHEDULE_NOUN_STOPWORDS = (
    'lich', 'su kien', 'hen', 'hop', 'meeting', 'appointment', 'calendar',
)


def _find_matching_schedules(message, db_path, window_days=14):
    """Best-effort keyword match against existing schedules in a date window --
    NEVER used to act directly. Callers must always show the matched
    schedule's current title+time back to the user for confirmation before
    mutating anything (see ScheduleUpdateAgent/ScheduleDeleteAgent)."""
    normalized = _normalize_intent_text(message)
    for phrase in _SCHEDULE_ACTION_STOPWORDS + _SCHEDULE_NOUN_STOPWORDS:
        normalized = normalized.replace(phrase, ' ')
    significant_words = [w for w in normalized.split() if len(w) >= 3]
    if not significant_words:
        return []

    now = datetime.now()
    window_start = now - timedelta(days=1)
    window_end = now + timedelta(days=window_days)
    candidates = Schedule.get_between(window_start.isoformat(), window_end.isoformat(), limit=100, db_path=db_path)

    scored = []
    for schedule in candidates:
        title_normalized = _normalize_intent_text(schedule.get('title') or '')
        score = sum(1 for word in significant_words if word in title_normalized)
        if score > 0:
            item = dict(schedule)
            item['_score'] = score
            scored.append(item)

    scored.sort(key=lambda item: item['_score'], reverse=True)
    return scored


def _direct_schedule_list_response(message, user_id, db_path, window_override=None):
    context = _format_calendar_context(message, user_id, db_path, window_override=window_override)
    return (
        context
        + "\n\nMình chỉ liệt kê dữ liệu lịch đang có trong Calendar/FlowMate, "
        "không tự suy đoán thêm sự kiện ngoài dữ liệu này."
    )


_CURRENT_TIME_TERMS = (
    'may gio', 'bay gio la may gio', 'hien tai may gio', 'gio hien tai',
    'hom nay ngay may', 'hom nay la ngay may', 'hom nay ngay bao nhieu',
    'hom nay la ngay bao nhieu', 'hom nay la ngay nao', 'ngay hien tai',
    'bay gio la ngay may', 'bay gio la ngay bao nhieu', 'ngay thang hom nay',
    'what time', 'current time', 'time now', 'what date', "today's date",
)


def _direct_current_time_response(message):
    normalized = _normalize_intent_text(message)
    if not any(term in normalized for term in _CURRENT_TIME_TERMS):
        return None

    now = datetime.now(LOCAL_TZ)
    weekday = (
        'thứ Hai', 'thứ Ba', 'thứ Tư', 'thứ Năm', 'thứ Sáu', 'thứ Bảy', 'Chủ nhật'
    )[now.weekday()]
    date_time_text = now.strftime('%d/%m/%Y. %H:%M')
    tz_key = getattr(LOCAL_TZ, 'key', None)
    tz_label = f"{tz_key}, UTC+7" if tz_key else "UTC+7"

    if any(term in normalized for term in ('what time', 'current time', 'time now', 'what date', "today's date")):
        return (
            f"In Vietnam ({tz_label}), it is {date_time_text} ({weekday})."
        )
    return (
        f"Hiện tại ở Việt Nam ({tz_label}) là {date_time_text} ({weekday})."
    )


WINDOW_LABELS_VN = {
    'today': 'HÔM NAY',
    'yesterday': 'HÔM QUA',
    'this_week': 'TUẦN NÀY',
    'next_week': 'TUẦN SAU',
    'last_week': 'TUẦN TRƯỚC',
}


def _window_override_from_entities(entities):
    """Turn an AI-classified `window` entity into the (start, end, label) tuple
    that _format_calendar_context expects, so an AI-assisted schedule.list
    intent actually changes which range gets queried -- not just the label.
    """
    window = (entities or {}).get('window')
    if not isinstance(window, dict):
        return None
    try:
        start = datetime.fromisoformat(str(window.get('start'))).replace(tzinfo=LOCAL_TZ)
        end = datetime.fromisoformat(str(window.get('end'))).replace(tzinfo=LOCAL_TZ)
    except (TypeError, ValueError):
        return None
    if end < start:
        return None
    if end == start:
        # IntentOrchestrator._calendar_window represents a single inclusive
        # day as start == end (e.g. 'today', 'specific_date'); expand to the
        # half-open range the calendar/schedule queries below expect. Without
        # this, every single-day window -- including the everyday 'today'
        # case -- silently failed this function and fell back to re-parsing
        # the raw message from scratch.
        end = start + timedelta(days=1)
    raw_label = window.get('label')
    if raw_label == 'specific_date':
        label = f"NGÀY {start.strftime('%d/%m/%Y')}"
    else:
        label = WINDOW_LABELS_VN.get(raw_label, 'KHOẢNG THỜI GIAN ĐÃ CHỌN')
    return start, end, label


class ScheduleCreateAgent:
    """AGENT_CAPABILITIES: roughly 'schedule.manage'. Owns both sub-paths
    that today live in two separate locations in chat.py: the "already
    confirmed" create flow, and the "not yet confirmed" propose flow
    (delegated to IntentOrchestrator.execute_direct via _wrap_direct_result)."""

    def handle(self, ctx):
        # Overrides may edit a pending proposal, but cannot confirm a write.
        if ctx.client_confirm:
            return self._handle_confirmed(ctx)
        direct_result = intent_orchestrator.execute_direct(
            ctx.intent_result, ctx.user_id, ctx.db_path, workspace_id=ctx.workspace_id
        )
        return _wrap_direct_result(direct_result, ctx)

    def _handle_confirmed(self, ctx):
        schedule_created = None
        calendar_sync_pending = False
        response = "Minh chua tao duoc lich vi thieu ngay/gio bat dau."
        try:
            schedule_created = intent_orchestrator.create_schedule_from_intent(
                ctx.intent_result,
                ctx.schedule_override,
                ctx.db_path
            )
            if schedule_created:
                calendar_sync_pending = _sync_schedule_to_calendar_async(
                    ctx.user_id,
                    schedule_created.get('id'),
                    ctx.db_path,
                )
                schedule_created['calendar_sync_pending'] = calendar_sync_pending
                response = (
                    f"Da tao lich: {schedule_created.get('title')} luc "
                    f"{_format_user_datetime(schedule_created.get('start_time'))}."
                )
                if calendar_sync_pending:
                    response += " Minh dang dong bo len Google Calendar."
                History.create(
                    f"Tao lich hen: {schedule_created.get('title')}",
                    "Lich hen duoc tao tu xac nhan cua nguoi dung",
                    action_type='schedule_created',
                    related_id=schedule_created.get('id'),
                    db_path=ctx.db_path,
                    workspace_id=ctx.workspace_id,
                )
        except Exception as e:
            logger.exception("Failed to create schedule through intent orchestrator")
            response = f"Khong the tao lich: {e}"

        return AgentResult(
            response=response,
            workspace_sources=['calendar'],
            refresh_targets=['schedule', 'calendar', 'overview', 'history'],
            schedule_created=schedule_created,
            schedule_suggestion=None if schedule_created else (ctx.intent_result.get('entities') or {}).get('schedule'),
            action='Tạo lịch sau xác nhận' if schedule_created else 'Cần bổ sung thông tin lịch',
        )
def _format_match_list(matches, verb):
    lines = [f"Mình thấy vài lịch khớp, bạn muốn {verb} cái nào? Hãy nói rõ hơn nhé."]
    for index, sched in enumerate(matches[:5], start=1):
        lines.append(f"{index}. {sched.get('title')} - {_format_user_datetime(sched.get('start_time'))}")
    return "\n".join(lines)


class ScheduleUpdateAgent:
    """AGENT_CAPABILITIES: roughly 'schedule.manage'. Only handles new
    start_time/end_time/attendees from the message -- deliberately does not
    attempt to infer a new title from freeform text (too ambiguous, risks
    silently overwriting the wrong field)."""

    def handle(self, ctx):
        if ctx.client_confirm and (ctx.schedule_override or {}).get('schedule_id'):
            return self._handle_confirmed(ctx)
        return self._propose(ctx)

    def _propose(self, ctx):
        # Prefer the AI-classified new time (handles paraphrases/relative
        # dates like "thu 5 tuan sau" that the regex fallback can't) when
        # the AI-assisted path actually ran; otherwise fall back to the same
        # regex-based extraction the rule-based path always uses.
        ai_new_values = (ctx.intent_result.get('entities') or {}).get('new_values')
        if ai_new_values and (ai_new_values.get('start_time') or ai_new_values.get('end_time')):
            new_values = ai_new_values
        else:
            new_values = intent_orchestrator.extract_schedule(ctx.user_message)
        has_change = bool(new_values.get('start_time') or new_values.get('end_time'))
        if not has_change:
            return AgentResult(
                response="Mình chưa hiểu bạn muốn đổi sang ngày/giờ nào, bạn nói rõ hơn giúp mình nhé.",
                action='Cần thêm thông tin để sửa lịch',
            )
        matches = _find_matching_schedules(ctx.user_message, ctx.db_path)
        if not matches:
            return AgentResult(
                response="Mình không tìm thấy lịch hẹn phù hợp trong 14 ngày tới. Bạn cho mình biết rõ tên lịch hẹn nhé.",
                workspace_sources=['calendar'],
                action='Không tìm thấy lịch cần sửa',
            )
        if len(matches) > 1:
            return AgentResult(
                response=_format_match_list(matches, 'sửa'),
                workspace_sources=['calendar'],
                action='Nhiều lịch khớp, cần xác định rõ',
            )
        sched = matches[0]
        suggestion = {
            'action': 'update',
            'schedule_id': sched.get('id'),
            'title': sched.get('title'),
            'start_time': sched.get('start_time'),
            'end_time': sched.get('end_time'),
            'new_start_time': new_values.get('start_time'),
            'new_end_time': new_values.get('end_time'),
        }
        return AgentResult(
            response=(
                f"Mình tìm thấy lịch '{sched.get('title')}' lúc {_format_user_datetime(sched.get('start_time'))}. "
                "Xác nhận đổi sang thời gian mới?"
            ),
            schedule_suggestion=suggestion,
            workspace_sources=['calendar'],
            action='Đề xuất sửa lịch cần xác nhận',
        )
    def _handle_confirmed(self, ctx):
        schedule_id = ctx.schedule_override.get('schedule_id')
        previous = Schedule.get_by_id(schedule_id, db_path=ctx.db_path)
        if not previous:
            return AgentResult(
                response="Lịch hẹn này không còn tồn tại, có thể đã bị xóa trước đó.",
                workspace_sources=['calendar'],
                action='Lịch không còn tồn tại',
            )

        update_data = {}
        if ctx.schedule_override.get('new_start_time'):
            update_data['start_time'] = ctx.schedule_override['new_start_time']
        if ctx.schedule_override.get('new_end_time'):
            update_data['end_time'] = ctx.schedule_override['new_end_time']

        if not update_data:
            return AgentResult(
                response="Không có thay đổi nào để cập nhật.",
                workspace_sources=['calendar'],
                action='Không có thay đổi',
            )

        try:
            Schedule.update(schedule_id, db_path=ctx.db_path, **update_data)
            _clear_schedule_cache(ctx.db_path)
            updated = Schedule.get_by_id(schedule_id, db_path=ctx.db_path)
            _sync_schedule_to_calendar_async(ctx.user_id, schedule_id, ctx.db_path)
            _prune_stale_duplicate_after_move_async(ctx.user_id, ctx.db_path, schedule_id, previous, updated)
            History.create(
                f"Chinh sua lich hen: {previous.get('title')}",
                f"Cap nhat: {', '.join(update_data.keys())}",
                action_type='schedule_updated',
                related_id=schedule_id,
                db_path=ctx.db_path,
                workspace_id=ctx.workspace_id,
            )
            response = f"Đã cập nhật lịch '{updated.get('title')}' sang {_format_user_datetime(updated.get('start_time'))}."
        except Exception as e:
            logger.exception("Failed to update schedule %s via chat", schedule_id)
            response = f"Không thể cập nhật lịch: {e}"

        return AgentResult(
            response=response,
            workspace_sources=['calendar'],
            refresh_targets=['schedule', 'history'],
            action='Đã cập nhật lịch',
        )


class ScheduleDeleteAgent:
    """AGENT_CAPABILITIES: roughly 'schedule.manage'."""

    def handle(self, ctx):
        if ctx.client_confirm and (ctx.schedule_override or {}).get('schedule_id'):
            return self._handle_confirmed(ctx)
        return self._propose(ctx)

    def _propose(self, ctx):
        matches = _find_matching_schedules(ctx.user_message, ctx.db_path)
        if not matches:
            return AgentResult(
                response="Mình không tìm thấy lịch hẹn phù hợp để xóa trong 14 ngày tới.",
                workspace_sources=['calendar'],
                action='Không tìm thấy lịch cần xóa',
            )
        if len(matches) > 1:
            return AgentResult(
                response=_format_match_list(matches, 'xóa'),
                workspace_sources=['calendar'],
                action='Nhiều lịch khớp, cần xác định rõ',
            )
        sched = matches[0]
        suggestion = {
            'action': 'delete',
            'schedule_id': sched.get('id'),
            'title': sched.get('title'),
            'start_time': sched.get('start_time'),
            'end_time': sched.get('end_time'),
        }
        return AgentResult(
            response=f"Mình tìm thấy lịch '{sched.get('title')}' lúc {_format_user_datetime(sched.get('start_time'))}. Xác nhận xóa?",
            schedule_suggestion=suggestion,
            workspace_sources=['calendar'],
            action='Đề xuất xóa lịch cần xác nhận',
        )

    def _handle_confirmed(self, ctx):
        schedule_id = ctx.schedule_override.get('schedule_id')
        schedule = Schedule.get_by_id(schedule_id, db_path=ctx.db_path)
        if not schedule:
            return AgentResult(
                response="Lịch hẹn này không còn tồn tại, có thể đã bị xóa trước đó.",
                workspace_sources=['calendar'],
                action='Lịch không còn tồn tại',
            )

        try:
            calendar_event_id = schedule.get('calendar_event_id')
            Schedule.delete(schedule_id, db_path=ctx.db_path)
            _clear_schedule_cache(ctx.db_path)
            if calendar_event_id:
                _delete_calendar_event_async(ctx.user_id, calendar_event_id, ctx.db_path)
            History.create(
                f"Xoa lich hen: {schedule.get('title')}",
                "Lich hen da bi xoa qua chat",
                action_type='schedule_deleted',
                related_id=schedule_id,
                db_path=ctx.db_path,
                workspace_id=ctx.workspace_id,
            )
            response = f"Đã xóa lịch '{schedule.get('title')}'."
        except Exception as e:
            logger.exception("Failed to delete schedule %s via chat", schedule_id)
            response = f"Không thể xóa lịch: {e}"

        return AgentResult(
            response=response,
            workspace_sources=['calendar'],
            refresh_targets=['schedule', 'history'],
            action='Đã xóa lịch',
        )


class ScheduleListAgent:
    """AGENT_CAPABILITIES: roughly 'calendar.sync'."""

    def handle(self, ctx):
        window_override = _window_override_from_entities(ctx.intent_result.get('entities'))
        response = _direct_schedule_list_response(
            ctx.user_message, ctx.user_id, ctx.db_path, window_override=window_override
        )
        return AgentResult(
            response=response,
            workspace_sources=['calendar'],
            refresh_targets=ctx.refresh_targets,
            action='Liệt kê lịch từ dữ liệu thật',
        )


class DayPlanSuggestAgent:
    """AGENT_CAPABILITIES: roughly 'schedule.manage'. Suggests calendar time
    slots for the activities listed in the chat message, reusing the exact
    same day-plan engine (_build_suggested_day_plan) as the Overview
    quick-add box -- same per-activity time/duration profiles, same
    conflict-aware slot search against existing schedules. Deliberately
    does NOT create anything itself: creating schedules always needs
    explicit confirmation, and the chat UI lets the user review/edit the
    suggestion and apply it through the existing, already-tested
    /schedule/plan-day/apply endpoint -- the same confirm-before-create
    path Overview already uses, instead of building a second one in chat."""

    def handle(self, ctx):
        date_value = datetime.now(LOCAL_TZ).date().isoformat()
        plan = _build_suggested_day_plan(ctx.user_id, ctx.db_path, ctx.user_message, date_value)
        if not plan:
            return None

        lines = [f"Mình gợi ý khung giờ sau cho {len(plan['items'])} hoạt động hôm nay, bạn xem và bấm áp dụng nếu hợp lý:"]
        for item in plan['items']:
            time_label = _format_schedule_response_time(item.get('start_time'), item.get('end_time'))
            lines.append(f"- {item.get('title')}: {time_label}")

        return AgentResult(
            response="\n".join(lines),
            day_plan_suggestion=plan,
            workspace_sources=['calendar'],
            refresh_targets=ctx.refresh_targets,
            action='Đề xuất lịch theo hoạt động, cần xác nhận',
        )
