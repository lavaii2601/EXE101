import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODE_DIR = REPO_ROOT / "docs" / "bob-training" / "modes"
EXPECTED_MODES = {
    "shared", "student", "worker", "freelancer", "creator", "business", "mentor", "teacher",
}


class BobModeCorpusTests(unittest.TestCase):
    def setUp(self):
        self.payloads = []
        for path in sorted(MODE_DIR.glob("*.json")):
            self.payloads.append((path, json.loads(path.read_text(encoding="utf-8"))))

    def test_exact_mode_file_set_and_schema(self):
        self.assertEqual(EXPECTED_MODES, {path.stem for path, _ in self.payloads})
        for path, payload in self.payloads:
            self.assertEqual(2, payload.get("schema_version"), path.name)
            self.assertEqual(path.stem, payload.get("mode"), path.name)
            self.assertIsInstance(payload.get("documents"), list, path.name)

    def test_preserves_old_documents_and_adds_exactly_500_contexts(self):
        documents = [doc for _, payload in self.payloads for doc in payload["documents"]]
        additions = [doc for doc in documents if "new-500" in doc.get("tags", "").split(",")]
        self.assertEqual(1119, len(documents))
        self.assertEqual(500, len(additions))
        self.assertEqual(1119, len({doc["title"] for doc in documents}))

    def test_checklist_time_corrections_are_present(self):
        documents = [doc for _, payload in self.payloads for doc in payload["documents"]]
        corrections = [doc for doc in documents if "checklist-time-correction" in doc.get("tags", "")]
        self.assertEqual(10, len(corrections))

    def test_knowledge_negative_corrections_are_present(self):
        documents = [doc for _, payload in self.payloads for doc in payload["documents"]]
        corrections = [doc for doc in documents if "knowledge-negative-correction" in doc.get("tags", "")]
        self.assertEqual(30, len(corrections))

    def test_web_fallback_corrections_are_present(self):
        documents = [doc for _, payload in self.payloads for doc in payload["documents"]]
        corrections = [doc for doc in documents if "web-fallback-correction" in doc.get("tags", "")]
        self.assertEqual(10, len(corrections))

    def test_every_mode_receives_new_contexts(self):
        for path, payload in self.payloads:
            additions = [doc for doc in payload["documents"] if "new-500" in doc.get("tags", "")]
            self.assertGreater(len(additions), 0, path.name)


if __name__ == "__main__":
    unittest.main()
