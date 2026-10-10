import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from services.bob_basic_eval_cases import (  # noqa: E402
    BASIC_INTENT_EVAL_CASES,
    iter_basic_intent_eval_cases,
)
from services.bob_training_cases import generate_training_cases  # noqa: E402
from services.intent_orchestrator import IntentOrchestrator  # noqa: E402
from services.tool_catalog import TOOL_NAMES  # noqa: E402


class BobBasicIntentAccuracyTests(unittest.TestCase):
    def test_eval_set_is_held_out_from_generated_training_phrases(self):
        training = {
            phrase.casefold()
            for intent in TOOL_NAMES
            for phrase in generate_training_cases(intent)
        }
        overlap = [
            case["text"]
            for case in iter_basic_intent_eval_cases()
            if case["text"].casefold() in training
        ]
        self.assertEqual([], overlap)

    def test_basic_web_app_intent_accuracy_is_at_least_90_percent(self):
        orchestrator = IntentOrchestrator()
        correct = Counter()
        totals = Counter()
        mistakes = defaultdict(list)

        for case in iter_basic_intent_eval_cases():
            expected = case["intent"]
            actual = orchestrator.detect_with_ai(case["text"], ai_service=None)["intent"]
            totals[expected] += 1
            if actual == expected:
                correct[expected] += 1
            else:
                mistakes[expected].append((case["text"], actual))

        total = sum(totals.values())
        score = sum(correct.values()) / total
        detail = "; ".join(
            f"{intent}={correct[intent]}/{totals[intent]} mistakes={mistakes[intent]}"
            for intent in sorted(totals)
        )
        self.assertGreaterEqual(score, 0.90, f"accuracy={score:.2%}; {detail}")

        # Overall accuracy must not hide a completely broken feature class.
        for intent, count in totals.items():
            self.assertGreaterEqual(
                correct[intent] / count,
                0.70,
                f"{intent}: {correct[intent]}/{count}, mistakes={mistakes[intent]}",
            )

    def test_eval_covers_every_basic_catalog_tool_and_freeform(self):
        expected = set(TOOL_NAMES) | {"chat.freeform"}
        self.assertEqual(expected, set(BASIC_INTENT_EVAL_CASES))


if __name__ == "__main__":
    unittest.main()
