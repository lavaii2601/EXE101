import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from services.bob_training_cases import (  # noqa: E402
    CASES_PER_INTENT,
    build_rag_training_documents,
    generate_training_cases,
    iter_labelled_cases,
)
from services.intent_orchestrator import IntentOrchestrator  # noqa: E402
from services.tool_catalog import TOOL_NAMES  # noqa: E402
from services.training_intent_classifier import TrainingIntentClassifier  # noqa: E402


class BobTrainingCorpusTests(unittest.TestCase):
    def test_exactly_500_unique_cases_exist_for_every_tool(self):
        for intent in TOOL_NAMES:
            cases = generate_training_cases(intent)
            self.assertEqual(CASES_PER_INTENT, len(cases), intent)
            self.assertEqual(CASES_PER_INTENT, len(set(cases)), intent)

    def test_total_case_and_compact_document_counts(self):
        self.assertEqual(len(TOOL_NAMES) * CASES_PER_INTENT, len(list(iter_labelled_cases())))
        self.assertEqual(len(TOOL_NAMES) * 10, len(build_rag_training_documents(batch_size=50)))

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


if __name__ == "__main__":
    unittest.main()
