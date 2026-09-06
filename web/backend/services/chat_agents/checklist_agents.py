"""Checklist chat agent: turns a freeform message into scored/prioritized
checklist entries, sharing the same cache the Overview checklist widget
reads/writes."""
import uuid
from datetime import datetime

from models.cache import Cache
from models.history import History
from models.schedule import LOCAL_TZ
from routes.schedule import (
    _checklist_cache_key,
    _normalize_checklist_payload,
    _sort_custom_items,
    _CHECKLIST_CACHE_TTL_SECONDS,
)

from .common import AgentResult

_CHECKLIST_PRIORITY_SCORE = {'high': 95, 'normal': 60, 'low': 30}
_CHECKLIST_PRIORITY_REASON = {
    'high': 'Việc gấp/quan trọng theo yêu cầu của bạn.',
    'normal': 'Thêm từ yêu cầu trong chat.',
    'low': 'Không gấp, có thể làm khi rảnh.',
}


def _normalize_checklist_entries(raw_items):
    normalized_items = []
    for entry in raw_items or []:
        if isinstance(entry, dict):
            title = str(entry.get('title') or '').strip()
            priority = str(entry.get('priority') or 'normal').strip().lower()
        else:
            title = str(entry or '').strip()
            priority = 'normal'
        if not title:
            continue
        if priority not in _CHECKLIST_PRIORITY_SCORE:
            priority = 'normal'
        normalized_items.append((title, priority))
    return normalized_items


class ChecklistCreateAgent:
    """AGENT_CAPABILITIES: roughly 'overview.daily_brief'. Write tool --
    always proposes the parsed item list first and only writes to the
    checklist once the user confirms (see tool_catalog.WRITE_TOOL_NAMES).
    Each item carries its own urgency (extracted per-item by the intent
    orchestrator, not one flat priority for the whole list) so wording like
    'gap'/'khong gap' in the original message actually changes where it
    lands in the checklist."""

    def handle(self, ctx):
        if ctx.action_confirm and (ctx.action_override or {}).get('items'):
            return self._apply(ctx, ctx.action_override.get('items'))
        return self._propose(ctx)

    def _propose(self, ctx):
        raw_items = (ctx.intent_result.get('entities') or {}).get('items') or []
        normalized_items = _normalize_checklist_entries(raw_items)
        if not normalized_items:
            return None

        titles = [title for title, _ in normalized_items]
        response = (
            "Mình sẽ thêm vào checklist hôm nay:\n"
            + "\n".join(f"- {title}" for title in titles)
            + "\nXác nhận nhé?"
        )
        return AgentResult(
            response=response,
            pending_action={
                'tool': 'checklist.create',
                'arguments': {
                    'items': [{'title': title, 'priority': priority} for title, priority in normalized_items],
                },
            },
            workspace_sources=['overview'],
            action='Đề xuất thêm việc vào checklist, cần xác nhận',
        )
    def _apply(self, ctx, raw_items):
        normalized_items = _normalize_checklist_entries(raw_items)
        if not normalized_items:
            return AgentResult(
                response="Không có việc nào để thêm.",
                workspace_sources=['overview'],
                action='Không có việc cần thêm',
            )

        date_value = datetime.now(LOCAL_TZ).date().isoformat()
        cache_key = _checklist_cache_key(ctx.user_id, date_value)
        cached = Cache.get(cache_key, db_path=ctx.db_path)
        payload = _normalize_checklist_payload(cached)
        existing_titles = {entry['title'].strip().lower() for entry in payload['custom_items']}

        added = []
        for title, priority in normalized_items:
            if title.lower() in existing_titles:
                continue
            payload['custom_items'].append({
                'id': f"manual:{uuid.uuid4().hex[:12]}",
                'title': title[:240],
                'completed': False,
                'created_at': datetime.utcnow().isoformat(),
                'source': 'manual',
                'item_type': 'task',
                'due_date': date_value,
                'due_at': '',
                'ai_reason': _CHECKLIST_PRIORITY_REASON[priority],
                'priority_score': _CHECKLIST_PRIORITY_SCORE[priority],
                'pinned': priority == 'high',
            })
            existing_titles.add(title.lower())
            added.append(title)

        if not added:
            return AgentResult(
                response="Các việc này đã có trong checklist hôm nay rồi.",
                workspace_sources=['overview'],
                refresh_targets=ctx.refresh_targets,
                action='Checklist đã có sẵn các việc này',
            )

        payload['custom_items'] = _sort_custom_items(payload['custom_items'])
        Cache.set(cache_key, payload, ttl=_CHECKLIST_CACHE_TTL_SECONDS, db_path=ctx.db_path)
        History.create(
            "Them viec vao checklist: " + ", ".join(added),
            "Them qua xac nhan trong chat",
            action_type='chat',
            db_path=ctx.db_path,
            workspace_id=ctx.workspace_id,
        )
        response = "Mình đã thêm vào checklist hôm nay:\n" + "\n".join(f"- {title}" for title in added)
        return AgentResult(
            response=response,
            workspace_sources=['overview'],
            refresh_targets=sorted(set(ctx.refresh_targets) | {'overview'}),
            action_applied={'tool': 'checklist.create', 'added': added},
            action='Đã thêm việc vào checklist sau xác nhận',
        )
