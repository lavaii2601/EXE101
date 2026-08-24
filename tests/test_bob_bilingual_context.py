import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from services.ai_service import AIService  # noqa: E402
from services.chat_agents import (  # noqa: E402
    AgentResult,
    ChatContext,
    FreeformChatAgent,
    MultiIntentWorkflowAgent,
    ScheduleCreateAgent,
    SettingsUpdateModeAgent,
    _build_agent_system_prompt,
    _email_lookup_query,
    _preserves_grounded_values,
    _query_override_from_entities,
    normalize_agent_result_language,
)
from services.conversation_context import (  # noqa: E402
    detect_language_profile,
    is_context_dependent_followup,
    latest_user_language,
)
from services.intent_orchestrator import IntentOrchestrator  # noqa: E402
from services.knowledge_service import KnowledgeService  # noqa: E402
from services import tool_catalog  # noqa: E402
from services.training_intent_classifier import TrainingIntentClassifier  # noqa: E402
from models.schedule import LOCAL_TZ  # noqa: E402


class BobLanguagePolicyTests(unittest.TestCase):
    def test_explicit_language_and_code_switch_policy(self):
        cases = (
            ("Please tóm tắt email này in English", "en", "en"),
            ("Answer in Vietnamese: summarize the latest email", "vi", "vi"),
            (
                "Trả lời bằng cả tiếng Việt và English",
                "vi",
                "bilingual",
            ),
            ("Ban this sender", "en", "en"),
            ("co mail nao gap ko", "vi", "vi"),
            ("Thanks nhé", "vi", "vi"),
        )
        for prompt, primary, response_mode in cases:
            profile = detect_language_profile(prompt)
            self.assertEqual(primary, profile["primary"], prompt)
            self.assertEqual(response_mode, profile["response_mode"], prompt)
        self.assertTrue(
            detect_language_profile("Please answer in English")["explicit"]
        )
        self.assertTrue(
            detect_language_profile("Please tìm email from Lan")["code_switched"]
        )

    def test_neutral_followup_inherits_same_session_language(self):
        self.assertEqual(
            "en",
            detect_language_profile("OK", fallback_language="en")["primary"],
        )
        records = [
            {
                "action_type": "chat",
                "user_message": "OK",
            },
            {
                "action_type": "chat",
                "user_message": "Please find emails from Lan",
            },
        ]
        self.assertEqual("en", latest_user_language(records))
        self.assertEqual(
            "en",
            latest_user_language(
                [{"action_type": "chat", "user_message": "Meeting Friday"}]
            ),
        )

    def test_ordinary_english_does_not_collide_with_vietnamese_tokens(self):
        prompts = (
            "The meeting is on Friday",
            "Do it tomorrow",
            "I need the latest status",
            "Please review the email",
            "Meeting Friday",
            "deploy now",
        )
        for prompt in prompts:
            profile = detect_language_profile(prompt, fallback_language="vi")
            self.assertEqual("en", profile["primary"], prompt)
            self.assertFalse(profile["inherited"], prompt)

    def test_context_dependent_followups_in_both_languages(self):
        dependent = (
            "đổi nó sang 4 giờ",
            "cái thứ hai",
            "do it",
            "Move it to Friday at 3pm",
            "mark the second one unread",
            "đánh dấu cái thứ 2 chưa đọc",
            "mark those unread",
            "what about tomorrow?",
        )
        for prompt in dependent:
            self.assertTrue(is_context_dependent_followup(prompt), prompt)
        self.assertFalse(is_context_dependent_followup("The report is ready"))
        self.assertFalse(is_context_dependent_followup("Find emails from Lan"))

    def test_system_prompt_contains_always_on_language_and_context_contract(self):
        prompt = _build_agent_system_prompt("Worker mode.", [])
        self.assertIn("LANGUAGE POLICY", prompt)
        self.assertIn("CONVERSATION POLICY", prompt)
        self.assertIn("code-switching", prompt)
        self.assertIn("newest correction", prompt)
        self.assertIn("Tiếng Việt:", prompt)

    def test_explicit_bilingual_output_uses_two_grounded_sections(self):
        original = "Đã tìm thấy email ID mail-123 lúc 09:30."
        result = AgentResult(response=original)
        with patch(
            "services.chat_agents.ai_service.generate_response",
        ) as generate:
            normalized = normalize_agent_result_language(
                result,
                "Trả lời bằng cả tiếng Việt và English",
                user_id="test-user",
            )
        generate.assert_not_called()
        self.assertEqual(original, normalized.response)
        self.assertIn("mail-123", normalized.response)
        self.assertIn("09:30", normalized.response)

    def test_demo_translation_cannot_replace_a_grounded_tool_result(self):
        original = "Found email Phoenix ID mail-123 at 09:30."
        result = AgentResult(response=original)
        with patch(
            "services.chat_agents.ai_service.configured_providers",
            ["openai"],
        ), patch(
            "services.chat_agents.ai_service.last_provider_used",
            "demo",
        ), patch(
            "services.chat_agents.ai_service.generate_response",
            return_value="Xin chào! Tôi là Lunex ở chế độ Demo.",
        ):
            normalized = normalize_agent_result_language(
                result,
                "Hãy trả lời bằng tiếng Việt",
                user_id="test-user",
            )
        self.assertEqual(original, normalized.response)

    def test_translation_cannot_drop_grounded_ids_or_times(self):
        original = "Found email Phoenix ID mail-123 at 09:30."
        result = AgentResult(response=original)
        with patch(
            "services.chat_agents.ai_service.configured_providers",
            ["openai"],
        ), patch(
            "services.chat_agents.ai_service.last_provider_used",
            "openai",
        ), patch(
            "services.chat_agents.ai_service.generate_response",
            return_value="Đã tạo lịch.",
        ):
            normalized = normalize_agent_result_language(
                result,
                "Hãy trả lời bằng tiếng Việt",
                user_id="test-user",
            )
        self.assertEqual(original, normalized.response)

    def test_translation_cannot_invert_a_write_outcome(self):
        self.assertFalse(
            _preserves_grounded_values(
                "Deleted event 'Phoenix'.",
                "Đã tạo lịch 'Phoenix'.",
            )
        )
        self.assertFalse(
            _preserves_grounded_values(
                "Found email Phoenix ID mail-123 at 09:30.",
                "Đã tạo lịch Phoenix ID mail-123 lúc 09:30.",
            )
        )
        self.assertFalse(
            _preserves_grounded_values(
                "Khong the xoa lich 'Payroll'.",
                "Đã xóa lịch 'Payroll'.",
            )
        )
        original = "Deleted event 'Phoenix'."
        result = AgentResult(
            response=original,
            action_applied={"tool": "schedule.delete"},
        )
        with patch(
            "services.chat_agents.ai_service.configured_providers",
            ["openai"],
        ), patch(
            "services.chat_agents.ai_service.generate_response",
            return_value="Đã tạo lịch 'Phoenix'.",
        ) as rewrite:
            normalized = normalize_agent_result_language(
                result,
                "Hãy trả lời bằng tiếng Việt",
                user_id="test-user",
            )
        rewrite.assert_not_called()
        self.assertEqual(original, normalized.response)

    def test_write_intent_failure_never_uses_a_generative_rewrite(self):
        original = "Gmail chưa được kết nối cho tài khoản này."
        result = AgentResult(response=original)
        false_success = (
            "Tiếng Việt:\nĐã đánh dấu email thành công.\n\n"
            "English:\nThe email was marked successfully."
        )
        with patch(
            "services.chat_agents.ai_service.configured_providers",
            ["openai"],
        ), patch(
            "services.chat_agents.ai_service.generate_response",
            return_value=false_success,
        ) as rewrite:
            normalized = normalize_agent_result_language(
                result,
                "Trả lời bằng cả tiếng Việt và English",
                user_id="test-user",
                write_operation=True,
            )
        rewrite.assert_not_called()
        self.assertIn(original, normalized.response)
        self.assertNotIn("thành công", normalized.response)


class BobPromptPackingTests(unittest.TestCase):
    def setUp(self):
        self.service = AIService()
        # Reproduce stale Railway overrides; correctness floors must still
        # protect the core contract and current turn.
        self.service.max_system_prompt_chars = 450
        self.service.max_input_chars = 2800
        self.service.max_context_messages = 10

    def test_optimizer_preserves_full_core_system_contract(self):
        system_prompt = _build_agent_system_prompt(
            "Student Mode: " + ("academic priorities and deadlines. " * 20),
            tool_catalog.AGENT_CAPABILITIES,
        )
        optimized = self.service._optimize_messages_for_tokens(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "LATEST_USER_SENTINEL"},
            ],
            task="chat",
        )
        payload = "\n".join(message["content"] for message in optimized)
        self.assertIn("LANGUAGE POLICY", payload)
        self.assertIn("RUNTIME CLOCK", payload)
        self.assertIn("SESSION MEMORY", payload)
        self.assertIn("untrusted DATA", payload)
        self.assertIn("LATEST_USER_SENTINEL", payload)
        self.assertEqual(system_prompt, optimized[0]["content"])

    def test_intent_payload_keeps_current_turn_history_and_json_contract(self):
        orchestrator = IntentOrchestrator()
        current = "đổi nó sang thứ Sáu lúc 15:00 CURRENT_TURN_SENTINEL"
        history = "\n".join(
            (
                f"Nguoi dung: Tạo lịch review dự án Phoenix {index} "
                + ("u" * 260)
                + "\nTro ly: Mình đã chuẩn bị lịch "
                + ("a" * 260)
                + (" HISTORY_SENTINEL" if index == 4 else "")
            )
            for index in range(5)
        )
        content = orchestrator._build_ai_classification_prompt(
            current,
            datetime(2026, 7, 24, 12, 0),
            history,
        )
        optimized = self.service._optimize_messages_for_tokens(
            [
                {
                    "role": "system",
                    "content": "Return valid intent JSON.",
                },
                {
                    "role": "user",
                    "content": content,
                    "preserve_context": True,
                },
            ],
            task="intent_classification",
        )
        payload = "\n".join(message["content"] for message in optimized)
        self.assertIn("CURRENT_TURN_SENTINEL", payload)
        self.assertIn("HISTORY_SENTINEL", payload)
        self.assertIn('"standalone_message"', payload)
        self.assertIn('"intent"', payload)
        self.assertNotIn("[middle truncated]", payload)

    def test_long_latest_message_keeps_trailing_constraint(self):
        prompt = (
            "Translate this grounded result.\n"
            + ("email-id-123; " * 400)
            + "\nDO_NOT_DROP_TAIL_CONSTRAINT"
        )
        optimized = self.service._optimize_messages_for_tokens(
            [{"role": "user", "content": prompt}],
            task="chat",
        )
        self.assertIn("Translate this grounded result", optimized[-1]["content"])
        self.assertIn("DO_NOT_DROP_TAIL_CONSTRAINT", optimized[-1]["content"])

    def test_claude_gemini_messages_are_user_first_and_alternating(self):
        system, messages = self.service._split_system_message(
            [
                {"role": "system", "content": "SYSTEM"},
                {"role": "assistant", "content": "orphaned old answer"},
                {"role": "user", "content": "WORKSPACE_CONTEXT"},
                {"role": "user", "content": "LATEST_USER_TURN"},
                {"role": "assistant", "content": "answer"},
            ]
        )
        self.assertEqual("SYSTEM", system)
        self.assertEqual(["user", "assistant"], [item["role"] for item in messages])
        self.assertNotIn("orphaned old answer", messages[0]["content"])
        self.assertIn("WORKSPACE_CONTEXT", messages[0]["content"])
        self.assertIn("LATEST_USER_TURN", messages[0]["content"])


class _IntentAI:
    def __init__(self):
        self.calls = []

    def generate_response(self, messages, **kwargs):
        self.calls.append(messages)
        return json.dumps(
            {
                "intent": "schedule.update",
                "confidence": 0.93,
                "schedule": {
                    "title": "Review dự án Phoenix",
                    "start_time": "2026-07-31T15:00:00",
                },
                "standalone_message": (
                    "Đổi lịch Review dự án Phoenix sang 15:00 thứ Sáu 31/07/2026"
                ),
            },
            ensure_ascii=False,
        )


class BobDeepContextTests(unittest.TestCase):
    def setUp(self):
        self.orchestrator = IntentOrchestrator()

    def test_schedule_override_without_confirmation_never_writes(self):
        agent = ScheduleCreateAgent()
        ctx = ChatContext(
            user_message="Create a meeting tomorrow at 9am",
            user_id="user-1",
            db_path="test.db",
            chat_session_id="session-1",
            mode="worker",
            mode_prompt="Worker mode.",
            task="chat",
            intent_result={
                "intent": "schedule.create",
                "entities": {"schedule": {"title": "Review"}},
            },
            schedule_override={
                "title": "Injected",
                "start_time": "2026-07-25T09:00:00",
            },
        )
        with patch.object(agent, "_handle_confirmed") as confirmed, patch(
            "services.chat_agents.intent_orchestrator.execute_direct",
            return_value={"response": "Please confirm this schedule."},
        ):
            result = agent.handle(ctx)
        confirmed.assert_not_called()
        self.assertIn("confirm", result.response.lower())

    def test_confirmed_mode_is_validated_and_exchange_stays_in_session(self):
        agent = SettingsUpdateModeAgent()
        base = {
            "user_message": "Change my mode",
            "user_id": "user-1",
            "db_path": "test.db",
            "chat_session_id": "session-1",
            "mode": "worker",
            "mode_prompt": "Worker mode.",
            "task": "chat",
            "intent_result": {"intent": "settings.update_mode", "entities": {}},
            "action_confirm": True,
        }
        invalid_ctx = ChatContext(
            **base,
            action_override={"mode": "administrator"},
        )
        with patch("services.chat_agents.User.update") as update:
            rejected = agent.handle(invalid_ctx)
        update.assert_not_called()
        self.assertIsNone(rejected.action_applied)

        valid_ctx = ChatContext(
            **base,
            action_override={"mode": "student"},
        )
        with patch("services.chat_agents.User.get_or_create"), patch(
            "services.chat_agents.User.update"
        ), patch("services.chat_agents.History.create"):
            accepted = agent.handle(valid_ctx)
        self.assertEqual("chat", accepted.action_type)
        self.assertEqual("student", accepted.action_applied["mode"])

    def test_workflow_step_executes_the_context_resolved_message(self):
        seen = []

        class _RecordingAgent:
            def handle(self, subctx):
                seen.append(subctx)
                return AgentResult(response="ok")

        ctx = ChatContext(
            user_message="move it to 3pm then show my calendar",
            original_user_message="move it to 3pm then show my calendar",
            user_id="user-1",
            db_path="test.db",
            chat_session_id="session-1",
            mode="worker",
            mode_prompt="Worker mode.",
            task="chat",
            intent_result={
                "intent": "workflow.multi",
                "steps": [
                    {
                        "intent": "schedule.update",
                        "message": "move it to 3pm",
                        "resolved_message": "move Project Phoenix review to 3pm",
                    },
                    {
                        "intent": "schedule.list",
                        "message": "show my calendar",
                    },
                ],
            },
        )
        with patch(
            "services.chat_agents.get_agent",
            return_value=_RecordingAgent(),
        ):
            MultiIntentWorkflowAgent().handle(ctx)
        self.assertEqual(
            "move Project Phoenix review to 3pm",
            seen[0].user_message,
        )
        self.assertEqual("move it to 3pm", seen[0].original_user_message)

    def test_contextual_followup_uses_history_and_is_not_cached_training(self):
        recent = [
            {
                "action_type": "chat",
                "user_message": "Tạo lịch review dự án Phoenix vào thứ Năm",
                "assistant_response": "Bạn muốn xác nhận lịch Review dự án Phoenix.",
            }
        ]
        ai = _IntentAI()
        with patch(
            "services.intent_orchestrator.History.get_recent",
            return_value=recent,
        ):
            result = self.orchestrator.detect_with_ai(
                "đổi nó sang thứ Sáu lúc 3 giờ chiều",
                ai,
                user_id="user-1",
                db_path="test.db",
                chat_session_id="11111111-1111-4111-8111-111111111111",
            )
        self.assertEqual("schedule.update", result["intent"])
        self.assertTrue(result["context_assisted"])
        self.assertIn("Phoenix", result["resolved_message"])
        sent_payload = json.dumps(ai.calls, ensure_ascii=False)
        self.assertIn("review dự án Phoenix", sent_payload)

    def test_contextual_phrase_without_history_does_not_guess(self):
        ai = _IntentAI()
        with patch(
            "services.intent_orchestrator.History.get_recent",
            return_value=[],
        ):
            result = self.orchestrator.detect_with_ai(
                "do it",
                ai,
                db_path="test.db",
                chat_session_id="22222222-2222-4222-8222-222222222222",
            )
        self.assertEqual("chat.freeform", result["intent"])
        self.assertEqual([], ai.calls)

    def test_freeform_keeps_history_together_with_workspace_context(self):
        recent = [
            {
                "action_type": "chat",
                "user_message": "Email của Lan là email mình đang nói tới.",
                "assistant_response": "Mình đã tìm thấy email của Lan.",
            }
        ]
        ctx = ChatContext(
            user_message="What about confidential Project Atlas?",
            original_user_message="Còn cái đó thì sao?",
            user_id="user-1",
            db_path="test.db",
            chat_session_id="33333333-3333-4333-8333-333333333333",
            mode="worker",
            mode_prompt="Worker mode.",
            task="chat",
            intent_result={"intent": "chat.freeform", "entities": {}},
        )
        with patch(
            "services.chat_agents._build_workspace_context",
            return_value=({"email"}, "WORKSPACE_SENTINEL"),
        ) as workspace_builder, patch(
            "services.chat_agents.History.get_recent",
            return_value=recent,
        ), patch(
            "services.chat_agents.SessionMemory.list_for_session",
            return_value=[],
        ), patch(
            "services.chat_agents.ai_service.configured_providers",
            ["ollama"],
        ), patch(
            "services.chat_agents.ai_service.last_provider_used",
            "ollama",
        ), patch(
            "services.chat_agents.ai_service.generate_response",
            return_value="Project Atlas appears in the supplied workspace context.",
        ) as generate:
            result = FreeformChatAgent().handle(ctx)

        generate.assert_called_once()
        packed_messages = generate.call_args.args[0]
        packed_text = "\n".join(message["content"] for message in packed_messages)
        self.assertIn("WORKSPACE_SENTINEL", packed_text)
        self.assertIn("Email của Lan", packed_text)
        self.assertFalse(
            workspace_builder.call_args.kwargs["force_web_research"]
        )
        self.assertFalse(
            workspace_builder.call_args.kwargs["allow_web_research"]
        )
        self.assertEqual("ollama", result.provider)
        self.assertFalse(result.demo_mode)
        self.assertTrue(result.ai_used)

    def test_english_and_code_switch_workflows_preserve_original_text(self):
        cases = (
            (
                "Show my calendar today and summarize my latest emails",
                ["schedule.list", "email.latest_summary"],
            ),
            (
                "Tìm email từ chị Nguyễn Ánh then create lịch follow-up tomorrow at 3pm",
                ["email.search", "schedule.create"],
            ),
        )
        for prompt, expected in cases:
            result = self.orchestrator.detect_workflow_with_ai(
                prompt,
                ai_service=None,
            )
            self.assertEqual("workflow.multi", result["intent"], prompt)
            self.assertEqual(
                expected,
                [step["intent"] for step in result["steps"]],
                prompt,
            )
            joined = " ".join(step["message"] for step in result["steps"])
            if "Nguyễn" in prompt:
                self.assertIn("Nguyễn Ánh", joined)

    def test_freeform_clause_is_not_silently_dropped_from_workflow(self):
        result = self.orchestrator.detect_workflow_with_ai(
            "Show my calendar today then tell me a joke then summarize my latest emails",
            ai_service=None,
        )
        self.assertEqual(
            ["schedule.list", "chat.freeform", "email.latest_summary"],
            [step["intent"] for step in result["steps"]],
        )

    def test_date_and_email_action_boundaries(self):
        date_cases = (
            ("Schedule a meeting on July 30 at 3pm", "2026-07-30T15:00:00"),
            ("Book a call next Friday at 10am", "2026-07-31T10:00:00"),
            ("Book a meeting next Monday at 9am", "2026-07-27T09:00:00"),
            ("Book a meeting next Monday at noon", "2026-07-27T12:00:00"),
            (
                "Schedule maintenance tomorrow at midnight",
                "2026-07-25T00:00:00",
            ),
            (
                "Schedule a review on January 5 at 9am",
                "2027-01-05T09:00:00",
            ),
            (
                "Schedule a review on February 29 at 9am",
                "2028-02-29T09:00:00",
            ),
            (
                "Đặt lịch họp thứ Năm tuần sau lúc 9 giờ sáng",
                "2026-07-30T09:00:00",
            ),
        )
        with patch(
            "services.intent_orchestrator.datetime",
            wraps=datetime,
        ) as mocked_datetime:
            mocked_datetime.now.return_value = datetime(2026, 7, 24, 12, 0)
            for prompt, expected_start in date_cases:
                result = self.orchestrator.detect(prompt)
                self.assertEqual("schedule.create", result["intent"], prompt)
                self.assertEqual(
                    expected_start,
                    result["entities"]["schedule"]["start_time"],
                    prompt,
                )
            mocked_datetime.now.assert_called_with(LOCAL_TZ)

        self.assertEqual(
            "email.mark_unread",
            self.orchestrator.detect(
                "Mark the latest 3 emails unread"
            )["intent"],
        )
        self.assertEqual(
            "email.latest_summary",
            self.orchestrator.detect(
                "Summarize the latest 3 emails"
            )["intent"],
        )
        for prompt in ("email mới nhất", "show latest email", "latest 3 emails"):
            self.assertEqual(
                "email.latest_summary",
                self.orchestrator.detect(prompt)["intent"],
                prompt,
            )
        self.assertEqual(
            "chat.freeform",
            self.orchestrator.detect(
                "Could you tell me who owns Gmail?"
            )["intent"],
        )
        negated = self.orchestrator.detect(
            "Don't create a Calendar event—put it on my checklist"
        )
        self.assertNotIn(
            negated["intent"],
            {"schedule.create", "schedule.list"},
        )
        self.assertFalse(negated["requires_confirmation"])
        for prompt in (
            "Bookmark this thread for later",
            "Mark this thread important",
            "Mark the report ready",
        ):
            self.assertNotIn(
                self.orchestrator.detect(prompt)["intent"],
                {"email.mark_read", "email.mark_unread"},
                prompt,
            )

    def test_negation_avoids_wrong_intent_across_expanded_rules(self):
        """_is_negated_action (services/intent_orchestrator.py) extends the
        negation check schedule.create/schedule.lookup already had to the
        other rule-based detectors, so an explicit refusal doesn't lock a
        wrong intent above detect_with_ai's confidence_threshold and skip
        AI review."""
        negated_cases = (
            ("dung xoa lich hop do", "schedule.delete"),
            ("chua muon doi che do sang freelancer", "settings.update_mode"),
            ("khong can xem lich su hoat dong nua", "history.list"),
            ("dung danh dau email nay da doc", "email.mark_read"),
            ("khong can them viec nay vao checklist", "checklist.create"),
            ("dung sap xep lich cho cac hoat dong nay", "schedule.suggest_plan"),
            ("don't mark this email as read", "email.mark_read"),
            ("khong can tom tat email moi nhat", "email.latest_summary"),
            ("dung cap nhat lich hop nay", "schedule.update"),
        )
        for prompt, avoided_intent in negated_cases:
            self.assertNotEqual(
                avoided_intent,
                self.orchestrator.detect(prompt)["intent"],
                prompt,
            )

        # The same phrasing without the negation marker must still route
        # normally -- the new check must not create false negatives on the
        # existing fast path.
        positive_cases = (
            ("xoa lich hop voi sep ngay mai", "schedule.delete"),
            ("doi che do sang freelancer", "settings.update_mode"),
            ("xem lich su hoat dong hom qua", "history.list"),
            ("danh dau email nay da doc", "email.mark_read"),
            ("them viec nop bao cao vao checklist, va di cho", "checklist.create"),
            ("sap xep lich cho tap gym va doc sach", "schedule.suggest_plan"),
            ("mark this email as read", "email.mark_read"),
            ("tom tat email moi nhat", "email.latest_summary"),
            ("doi lich hop sang 5 gio chieu mai", "schedule.update"),
        )
        for prompt, expected_intent in positive_cases:
            self.assertEqual(
                expected_intent,
                self.orchestrator.detect(prompt)["intent"],
                prompt,
            )

    def test_email_exclusions_survive_raw_and_entity_queries(self):
        raw_query, _ = _email_lookup_query(
            "Mark all emails read except invoice"
        )
        entity_query, _ = _query_override_from_entities(
            {
                "date_window": {
                    "start": "2026-07-24",
                    "end": "2026-07-24",
                }
            },
            message="Đánh dấu email hôm nay đã đọc, loại trừ invoice",
        )
        self.assertIn('-"invoice"', raw_query)
        self.assertIn('-"invoice"', entity_query)
        self.assertIn("after:2026/07/24", entity_query)

    def test_offline_classifier_contains_real_code_switch_cores(self):
        classifier = TrainingIntentClassifier()
        cases = (
            (
                "Please book lich demo san pham vao 3pm thu sau, please",
                "schedule.create",
            ),
            (
                "Giup minh tim unread emails cua giao vien, tren FlowMate",
                "email.search",
            ),
            (
                "Please add ba dau viec nay vao todo hom nay, cam on Bob",
                "checklist.create",
            ),
        )
        for prompt, expected in cases:
            result = classifier.classify(prompt)
            self.assertEqual(expected, result["intent"], prompt)
            self.assertGreaterEqual(result["confidence"], 0.65, prompt)

    def test_rag_mode_filter_keeps_shared_and_current_mode_rules(self):
        documents = [
            {
                "id": 1,
                "title": "Worker planning",
                "content": "planning schedule deadline",
                "tags": "worker,planning,semantic-pair,vi-en",
                "source": "test",
                "user_id": None,
            },
            {
                "id": 2,
                "title": "Student planning",
                "content": "planning schedule deadline",
                "tags": "student,planning,semantic-pair,vi-en",
                "source": "test",
                "user_id": None,
            },
            {
                "id": 3,
                "title": "Shared safety",
                "content": "planning schedule deadline confirmation",
                "tags": "shared,safety,semantic-pair,vi-en",
                "source": "test",
                "user_id": None,
            },
            {
                "id": 4,
                "title": "Personal preference",
                "content": "planning schedule deadline personal preference",
                "tags": "student,preference,auto",
                "source": "auto",
                "user_id": "user-1",
            },
        ]
        with patch(
            "services.knowledge_service.KnowledgeDocument.get_all",
            return_value=documents,
        ):
            service = KnowledgeService()
            results = service.search(
                "planning schedule deadline",
                top_k=10,
                min_score=0,
                user_id="user-1",
                mode="worker",
            )
        titles = {result["title"] for result in results}
        self.assertIn("Worker planning", titles)
        self.assertIn("Shared safety", titles)
        self.assertIn("Personal preference", titles)
        self.assertNotIn("Student planning", titles)


if __name__ == "__main__":
    unittest.main()
