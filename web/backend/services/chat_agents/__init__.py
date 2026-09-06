"""Chat agent dispatch table.

Package split of the former monolithic chat_agents.py: this module owns
get_agent()'s dispatch table plus MultiIntentWorkflowAgent (the cross-domain
workflow dispatcher, which must be able to reach every domain agent) and the
two thin execute_direct wrappers (HistoryListAgent, SettingsUpdateModeAgent)
that don't belong to any one domain module.

Re-exports the exact names routes/chat.py imports so that file needs no
changes: ai_service, intent_orchestrator, get_agent, ChatContext,
learn_from_exchange_async, learn_from_mentors_async,
normalize_agent_result_language.

Also re-exports several private helpers and models.* classes that the test
suite reaches into directly by their pre-split dotted path
(services.chat_agents.<name>) -- kept so those tests need no changes beyond
their patch targets for helpers that moved into a submodule (see each
test's own history for the ones whose patch string had to follow the
function to its new module).
"""
import logging
from dataclasses import replace
from datetime import datetime

from services import tool_catalog
from models.history import History
from models.user import User
from models.session_memory import SessionMemory
from models.schedule import LOCAL_TZ

from .common import (
    ai_service,
    intent_orchestrator,
    ChatContext,
    AgentResult,
    _wrap_direct_result,
    _build_agent_system_prompt,
    _preserves_grounded_values,
    learn_from_exchange_async,
    learn_from_mentors_async,
    normalize_agent_result_language,
)
from .email_agents import (
    EmailLatestSummaryAgent,
    EmailSearchAgent,
    EmailMarkReadAgent,
    EmailMarkUnreadAgent,
    _email_lookup_query,
    _query_override_from_entities,
    _email_result_reference,
    _mark_emails_propose,
)
from .schedule_agents import (
    ScheduleCreateAgent,
    ScheduleUpdateAgent,
    ScheduleDeleteAgent,
    ScheduleListAgent,
    DayPlanSuggestAgent,
    _direct_current_time_response,
)
from .checklist_agents import ChecklistCreateAgent
from .freeform_agent import (
    FreeformChatAgent,
    _valid_freeform_synthesis,
    _web_research_fallback_response,
    _build_workspace_context,
)

logger = logging.getLogger(__name__)


class HistoryListAgent:
    """AGENT_CAPABILITIES: roughly 'history.audit'."""

    def handle(self, ctx):
        direct_result = intent_orchestrator.execute_direct(
            ctx.intent_result, ctx.user_id, ctx.db_path, workspace_id=ctx.workspace_id
        )
        return _wrap_direct_result(direct_result, ctx)


class SettingsUpdateModeAgent:
    """AGENT_CAPABILITIES: roughly 'settings.profile_mode'. Write tool --
    always proposes the mode change first and only calls User.update() once
    the user has explicitly confirmed (see tool_catalog.WRITE_TOOL_NAMES).
    Can return None (when the mode entity couldn't be resolved), signalling
    the caller to fall through to FreeformChatAgent."""

    def handle(self, ctx):
        if ctx.action_confirm and (ctx.action_override or {}).get('mode'):
            return self._handle_confirmed(ctx)
        direct_result = intent_orchestrator.execute_direct(
            ctx.intent_result, ctx.user_id, ctx.db_path, workspace_id=ctx.workspace_id
        )
        return _wrap_direct_result(direct_result, ctx)

    def _handle_confirmed(self, ctx):
        mode = str(ctx.action_override.get('mode') or '').strip().lower()
        if mode not in intent_orchestrator.MODE_ALIASES:
            return AgentResult(
                response="Chế độ được xác nhận không hợp lệ; mình chưa thay đổi cài đặt.",
                workspace_sources=['profile'],
                refresh_targets=['settings', 'profile'],
                action='Từ chối chế độ làm việc không hợp lệ',
            )
        User.get_or_create(ctx.user_id)
        User.update(
            ctx.user_id,
            user_mode=mode,
            user_mode_selected_at=datetime.now().isoformat(),
        )
        label = intent_orchestrator.MODE_LABELS.get(mode, mode)
        History.create(
            f"Doi che do lam viec sang {label}",
            "Che do duoc doi qua xac nhan trong chat",
            action_type='settings_updated',
            db_path=ctx.db_path,
            workspace_id=ctx.workspace_id,
        )
        return AgentResult(
            response=f"Đã cập nhật chế độ làm việc sang {label}.",
            workspace_sources=['profile'],
            refresh_targets=['settings', 'profile', 'history'],
            action_applied={'tool': 'settings.update_mode', 'mode': mode},
            action='Đã đổi chế độ làm việc sau xác nhận',
        )


class MultiIntentWorkflowAgent:
    """Run read steps together and queue confirmation-gated writes.

    Current clients render one confirmation card at a time. A workflow may
    therefore execute all read-only steps immediately, but exposes only the
    first write proposal; later writes remain visibly queued.
    """

    @staticmethod
    def _confirmed_tool(ctx):
        tool = (ctx.action_override or {}).get('tool')
        if tool:
            return tool
        if ctx.client_confirm:
            action = (ctx.schedule_override or {}).get('action')
            if action == 'update':
                return 'schedule.update'
            if action == 'delete':
                return 'schedule.delete'
            return 'schedule.create'
        return None

    def handle(self, ctx):
        steps = list(ctx.intent_result.get('steps') or [])[:8]
        confirmed_tool = self._confirmed_tool(ctx)
        write_result = None
        responses = []
        sources = set()
        refresh_targets = set(ctx.refresh_targets)
        suggested_actions = []
        email_sources = []
        queued_writes = []
        completed_results = []

        for index, step in enumerate(steps, start=1):
            intent = step.get('intent')
            if not intent or intent == 'workflow.multi':
                continue
            is_write = intent in tool_catalog.WRITE_TOOL_NAMES
            if is_write and (
                (confirmed_tool and intent != confirmed_tool)
                or write_result is not None
            ):
                queued_writes.append(intent)
                continue

            subctx = replace(
                ctx,
                user_message=(
                    step.get('resolved_message')
                    or step.get('message')
                    or ctx.user_message
                ),
                original_user_message=(
                    step.get('message')
                    or ctx.original_user_message
                    or ctx.user_message
                ),
                intent_result=step,
                refresh_targets=list(step.get('refresh_targets') or []),
                action_confirm=bool(ctx.action_confirm and confirmed_tool == intent),
                client_confirm=bool(ctx.client_confirm and confirmed_tool == intent),
            )
            result = get_agent(intent).handle(subctx)
            if result is None:
                continue
            completed_results.append(result)
            responses.append(f"{index}. {result.response}")
            sources.update(result.workspace_sources or [])
            refresh_targets.update(result.refresh_targets or [])
            suggested_actions.extend(result.suggested_actions or [])
            email_sources.extend(result.email_sources or [])
            if is_write:
                write_result = result

        if queued_writes:
            labels = [
                tool_catalog.CATALOG[name].user_label
                for name in queued_writes if name in tool_catalog.CATALOG
            ]
            responses.append(
                "Các bước ghi tiếp theo đang chờ xử lý lần lượt: " + ", ".join(labels) + "."
            )
        if not responses:
            return AgentResult(
                response="Mình chưa tách được các bước đủ rõ. Hãy nêu từng hành động cụ thể hơn.",
                refresh_targets=sorted(refresh_targets),
                action='Workflow chưa đủ dữ liệu',
            )

        anchor = write_result or (completed_results[0] if completed_results else None)
        return AgentResult(
            response="Mình đã tách yêu cầu thành các bước:\n" + "\n".join(responses),
            workspace_sources=sorted(sources),
            refresh_targets=sorted(refresh_targets),
            schedule_created=getattr(anchor, 'schedule_created', None),
            schedule_suggestion=getattr(anchor, 'schedule_suggestion', None),
            day_plan_suggestion=getattr(anchor, 'day_plan_suggestion', None),
            suggested_actions=suggested_actions or None,
            action='Xử lý workflow nhiều ý định',
            ai_used=any(result.ai_used for result in completed_results),
            grounded=all(result.grounded for result in completed_results),
            provider=getattr(anchor, 'provider', None),
            demo_mode=any(result.demo_mode for result in completed_results),
            email_source=getattr(anchor, 'email_source', None),
            email_sources=email_sources or None,
            pending_action=getattr(anchor, 'pending_action', None),
            action_applied=getattr(anchor, 'action_applied', None),
        )


_FREEFORM_AGENT = FreeformChatAgent()

_AGENT_REGISTRY = {
    'workflow.multi': MultiIntentWorkflowAgent(),
    'email.latest_summary': EmailLatestSummaryAgent(),
    'schedule.create': ScheduleCreateAgent(),
    'schedule.update': ScheduleUpdateAgent(),
    'schedule.delete': ScheduleDeleteAgent(),
    'schedule.list': ScheduleListAgent(),
    'email.search': EmailSearchAgent(),
    'email.mark_read': EmailMarkReadAgent(),
    'email.mark_unread': EmailMarkUnreadAgent(),
    'history.list': HistoryListAgent(),
    'settings.update_mode': SettingsUpdateModeAgent(),
    'checklist.create': ChecklistCreateAgent(),
    'schedule.suggest_plan': DayPlanSuggestAgent(),
}


def get_agent(intent):
    return _AGENT_REGISTRY.get(intent, _FREEFORM_AGENT)
