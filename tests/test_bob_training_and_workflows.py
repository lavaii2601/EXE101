import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from services.bob_training_cases import (  # noqa: E402
    CASES_PER_INTENT,
    build_rag_training_documents,
    generate_training_cases,
    iter_labelled_cases,
)
from config import Config  # noqa: E402
from services.ai_service import AIService  # noqa: E402
from services.intent_orchestrator import IntentOrchestrator  # noqa: E402
from services.chat_agents import (  # noqa: E402
    ChatContext,
    FreeformChatAgent,
    LOCAL_TZ,
    _build_agent_system_prompt,
    _direct_current_time_response,
    _web_research_fallback_response,
)
from services.tool_catalog import TOOL_NAMES  # noqa: E402
from services.training_intent_classifier import TrainingIntentClassifier  # noqa: E402
try:
    from services.web_research_service import WebResearchService  # noqa: E402
except ModuleNotFoundError:  # Minimal unit-test environments may omit requests.
    WebResearchService = None


class BobTrainingCorpusTests(unittest.TestCase):
    def test_exactly_cases_per_intent_unique_cases_exist_for_every_tool(self):
        for intent in TOOL_NAMES:
            cases = generate_training_cases(intent)
            self.assertEqual(CASES_PER_INTENT, len(cases), intent)
            self.assertEqual(CASES_PER_INTENT, len(set(cases)), intent)

    def test_total_case_and_compact_document_counts(self):
        self.assertEqual(len(TOOL_NAMES) * CASES_PER_INTENT, len(list(iter_labelled_cases())))
        batches_per_intent = CASES_PER_INTENT // 50
        self.assertEqual(len(TOOL_NAMES) * batches_per_intent, len(build_rag_training_documents(batch_size=50)))

    def test_classifier_routes_unseen_paraphrases(self):
        classifier = TrainingIntentClassifier()
        samples = {
            "nhac toi dung day luc 6 gio sang mai": "schedule.create",
            "toi da lam duoc nhung gi": "history.list",
            "de may viec nay vao todo": "checklist.create",
            "chuyen toi thanh freelancer": "settings.update_mode",
        }
        for phrase, expected in samples.items():
            result = classifier.classify(phrase)
            self.assertEqual(expected, result["intent"], phrase)
            self.assertGreaterEqual(result["confidence"], 0.65, phrase)


class BobWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.orchestrator = IntentOrchestrator()

    def test_explicit_sequence_becomes_multi_step_workflow(self):
        result = self.orchestrator.detect_workflow_with_ai(
            "xem lich hom nay roi tom tat email moi nhat",
            ai_service=None,
        )
        self.assertEqual("workflow.multi", result["intent"])
        self.assertEqual(
            ["schedule.list", "email.latest_summary"],
            [step["intent"] for step in result["steps"]],
        )

    def test_training_fallback_routes_schedule_without_schedule_keyword(self):
        result = self.orchestrator.detect_workflow_with_ai(
            "nhac toi dung day luc 6 gio sang mai",
            ai_service=None,
        )
        self.assertEqual("schedule.create", result["intent"])
        self.assertTrue(result.get("training_assisted"))
        self.assertTrue((result.get("entities") or {}).get("schedule", {}).get("start_time"))

    def test_raised_read_limits(self):
        self.assertEqual(37, self.orchestrator._latest_email_count("tom tat 37 email moi nhat"))
        self.assertEqual(75, self.orchestrator._limit_from_text("xem 75 hoat dong", maximum=100))

    def test_facebook_knowledge_question_is_not_mistaken_for_book_action(self):
        questions = (
            "Người sáng lập Facebook là ai?",
            "Ai là chủ của Facebook?",
            "Ai là chủ của Amazon?",
            "Chủ của Booking.com là ai?",
            "Who owns Eventbrite?",
            "Ai sáng lập Gmail?",
        )
        for question in questions:
            self.assertTrue(self.orchestrator.is_general_knowledge_question(question), question)
            self.assertFalse(self.orchestrator.has_actionable_hint(question), question)
            result = self.orchestrator.detect_workflow_with_ai(question, ai_service=None)
            self.assertEqual("chat.freeform", result["intent"], question)
            self.assertTrue(result.get("knowledge_question"), question)
            self.assertFalse(result.get("requires_confirmation"), question)
            self.assertNotIn("schedule", result.get("entities") or {}, question)

    def test_ai_cannot_turn_company_owner_question_into_schedule_popup(self):
        result = self.orchestrator._coerce_ai_result(
            {
                "intent": "schedule.create",
                "confidence": 0.99,
                "schedule": {"title": "Facebook", "start_time": "2026-07-21T09:00:00"},
            },
            "Ai là chủ Facebook?",
        )
        self.assertEqual("chat.freeform", result["intent"])
        self.assertFalse(result["requires_confirmation"])
        self.assertNotIn("schedule", result["entities"])

    def test_book_still_routes_a_real_calendar_request(self):
        result = self.orchestrator.detect("Book a meeting tomorrow at 3pm")
        self.assertEqual("schedule.create", result["intent"])

    def test_checklist_preserves_clock_colons_activity_names_and_time_order(self):
        message = (
            "hôm nay tôi có làm bài tập lúc 11:00 sáng, gym lúc 7:30 sáng, "
            "nấu ăn lúc 9:00 sáng. hãy thêm vào checklist theo thứ tự giờ"
        )
        result = self.orchestrator.detect(message)
        self.assertEqual("checklist.create", result["intent"])
        self.assertEqual(
            ["07:30 - gym", "09:00 - nấu ăn", "11:00 - làm bài tập"],
            [item["title"] for item in result["entities"]["items"]],
        )

    def test_natural_current_date_question_uses_runtime_clock(self):
        before = datetime.now(LOCAL_TZ).strftime("%d/%m/%Y")
        response = _direct_current_time_response("Hôm nay là ngày mấy?")
        after = datetime.now(LOCAL_TZ).strftime("%d/%m/%Y")
        self.assertIsNotNone(response)
        self.assertTrue(before in response or after in response, response)
        self.assertIn("UTC+7", response)

        result = FreeformChatAgent().handle(ChatContext(
            user_message="Hôm nay là ngày mấy?",
            user_id="test-user",
            db_path="test.db",
            chat_session_id="00000000-0000-4000-8000-000000000001",
            mode="worker",
            mode_prompt="worker",
            task="chat",
            intent_result={"intent": "chat.freeform", "entities": {}},
        ))
        self.assertFalse(result.ai_used)
        self.assertEqual(["time"], result.workspace_sources)
        self.assertIsNone(result.schedule_suggestion)
        self.assertIsNone(result.schedule_created)

    def test_freeform_system_prompt_contains_authoritative_runtime_date(self):
        before = datetime.now(LOCAL_TZ).strftime("%d/%m/%Y")
        prompt = _build_agent_system_prompt("worker", [])
        after = datetime.now(LOCAL_TZ).strftime("%d/%m/%Y")
        self.assertTrue(before in prompt or after in prompt, prompt)
        self.assertIn("Asia/Ho_Chi_Minh", prompt)


@unittest.skipIf(WebResearchService is None, "web research dependencies are not installed")
class BobWebResearchIntentTests(unittest.TestCase):
    def setUp(self):
        self.service = WebResearchService()

    def test_natural_search_requests_do_not_require_word_internet(self):
        prompts = (
            "Tim giup toi nguoi sang lap Facebook la ai",
            "Tra cuu thong tin moi nhat ve OpenAI",
            "Xac minh thong tin nay co dung khong",
            "Find out who founded Facebook",
        )
        for prompt in prompts:
            self.assertTrue(self.service.should_research(prompt), prompt)

    def test_plain_fact_question_researches_when_local_knowledge_has_gap(self):
        self.assertTrue(self.service.should_research(
            "Nguoi sang lap Facebook la ai?",
            knowledge_gap=True,
        ))

    def test_freeform_questions_force_web_search_without_keyword(self):
        questions = (
            "Ai là chủ của Amazon?",
            "Email marketing hoạt động như thế nào?",
            "Giải thích điện toán lượng tử cho người mới",
            "So sánh PostgreSQL và MySQL",
        )
        for question in questions:
            self.assertTrue(
                self.service.should_research(question, force_research=True),
                question,
            )

    def test_forced_search_still_excludes_smalltalk_and_private_tasks(self):
        self.assertFalse(self.service.should_research("Xin chào Bob", force_research=True))
        self.assertFalse(self.service.should_research("Hôm nay mình thấy vui", force_research=True))
        self.assertFalse(self.service.should_research(
            "Tóm tắt email của tôi",
            workspace_sources={"email"},
            force_research=True,
        ))

    def test_demo_mode_preserves_grounded_internet_results(self):
        context = """INTERNET RESEARCH
Query: donald trump
Retrieved at: 2026-07-25T10:00:00Z
Use these external sources only for public web facts.
1. Donald Trump - latest information
   URL: https://example.com/donald-trump
   Snippet: Recent public information about Donald Trump.
2. Donald Trump profile
   URL: https://example.org/profile
   Snippet: Background and related public updates.
"""
        ctx = ChatContext(
            user_message="tìm kiếm trên internet thông tin về Donald Trump",
            user_id="test-user",
            db_path="test.db",
            chat_session_id="00000000-0000-4000-8000-000000000002",
            mode="worker",
            mode_prompt="worker",
            task="chat",
            intent_result={"intent": "chat.freeform", "entities": {}},
        )

        with (
            patch(
                "services.chat_agents._build_workspace_context",
                return_value=({"internet"}, context),
            ),
            patch("services.chat_agents.ai_service.generate_response") as generate,
            patch(
                "services.chat_agents.SessionMemory.list_for_session",
                return_value=[],
            ),
        ):
            result = FreeformChatAgent().handle(ctx)

        generate.assert_not_called()
        self.assertEqual("internet", result.provider)
        self.assertFalse(result.demo_mode)
        self.assertFalse(result.ai_used)
        self.assertIn("https://example.com/donald-trump", result.response)
        self.assertIn("Recent public information", result.response)
        self.assertNotIn("AI provider", result.response)

    def test_web_fallback_requires_citable_results(self):
        self.assertIsNone(
            _web_research_fallback_response(
                "INTERNET RESEARCH\nQuery: donald trump",
                target_language="vi",
            )
        )

    def test_local_only_blocks_external_provider_even_when_called_directly(self):
        service = AIService()
        self.assertTrue(Config.BOB_LOCAL_ONLY)
        self.assertEqual([], service.configured_providers)
        with self.assertRaisesRegex(RuntimeError, "BOB_LOCAL_ONLY"):
            service._call_provider("openrouter", [], 10)

    def test_general_questions_that_mention_tools_do_not_trigger_actions(self):
        orchestrator = IntentOrchestrator()
        for prompt in ("email marketing là gì", "schedule algorithm là gì"):
            with self.subTest(prompt=prompt):
                result = orchestrator.detect_with_ai(prompt, ai_service=None)
                self.assertEqual("chat.freeform", result["intent"])


if __name__ == "__main__":
    unittest.main()
