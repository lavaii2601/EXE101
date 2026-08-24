import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
MODE_DIR = REPO_ROOT / "docs" / "bob-training" / "modes"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from train_bob import _load_documents  # noqa: E402
from services.knowledge_service import KnowledgeService  # noqa: E402


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
        self.assertEqual(1139, len(documents))
        self.assertEqual(500, len(additions))
        self.assertEqual(1139, len({doc["title"] for doc in documents}))

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

    def test_agent_and_academic_lessons_are_present(self):
        documents = [doc for _, payload in self.payloads for doc in payload["documents"]]
        lessons = [doc for doc in documents if "agent-academic-v1" in doc.get("tags", "")]
        self.assertEqual(20, len(lessons))
        content = " ".join(doc["content_en"] for doc in lessons)
        self.assertIn("requested deliverable", content)
        self.assertIn("Never invent authors", content)
        self.assertIn("correlation from causation", content)

    def test_every_mode_receives_new_contexts(self):
        for path, payload in self.payloads:
            additions = [doc for doc in payload["documents"] if "new-500" in doc.get("tags", "")]
            self.assertGreater(len(additions), 0, path.name)

    def test_every_document_has_one_to_one_english_semantics(self):
        documents = [doc for _, payload in self.payloads for doc in payload["documents"]]
        self.assertEqual(1139, len(documents))
        for document in documents:
            self.assertTrue(str(document.get("content_en") or "").strip(), document["title"])
            tags = set(str(document.get("tags") or "").split(","))
            self.assertIn("semantic-pair", tags, document["title"])
            self.assertIn("vi-en", tags, document["title"])

    def test_shared_corpus_contains_real_code_switch_and_followup_lessons(self):
        documents = {
            doc["title"]: doc
            for path, payload in self.payloads
            if path.stem == "shared"
            for doc in payload["documents"]
        }
        language = documents["Case 099 - Ngon ngu tra loi"]
        followup = documents["Case 100 - Cau hoi mo ho"]
        mixed_email = documents["Email 117 - Email language mixed"]

        self.assertIn("in English", language["content"])
        self.assertIn("both languages", language["content_en"])
        self.assertIn("Move it to Friday at 3 PM", followup["content_en"])
        self.assertIn("Don't create a Calendar event", followup["content_en"])
        self.assertIn("except invoice", mixed_email["content"])
        self.assertIn("code-switch", mixed_email["tags"])

    def test_generated_english_contexts_do_not_use_invalid_articles(self):
        documents = [doc for _, payload in self.payloads for doc in payload["documents"]]
        generated = [
            doc for doc in documents
            if "new-500" in str(doc.get("tags") or "").split(",")
        ]
        invalid_phrases = (
            "a ambiguous situation",
            "a urgent situation",
            "an bilingual situation",
            "an missing data situation",
            "an multi-step situation",
            "an last-minute change situation",
            "an long-term follow-up situation",
        )
        for document in generated:
            for phrase in invalid_phrases:
                self.assertNotIn(phrase, document["content_en"], document["title"])

    def test_importer_indexes_english_semantics_in_same_document(self):
        documents = _load_documents(
            [MODE_DIR / "teacher.json"],
            default_tags="bob,training,mode,teacher",
            chunk_chars=0,
        )
        teacher_payload = next(payload for path, payload in self.payloads if path.stem == "teacher")
        self.assertEqual(len(teacher_payload["documents"]), len(documents))
        for document in documents:
            self.assertIn("English semantic equivalent:", document["content"])

    def test_english_queries_retrieve_matching_vietnamese_rules(self):
        imported = _load_documents(
            [MODE_DIR],
            default_tags="bob,training,semantic-pair,vi-en",
            chunk_chars=0,
        )
        db_documents = [
            {
                "id": index,
                "title": document["title"],
                "content": document["content"],
                "tags": document["tags"],
                "source": "test",
                "user_id": None,
            }
            for index, document in enumerate(imported, start=1)
        ]
        cases = (
            ("an ambiguous schedule request in Teacher Mode", {"teacher", "schedule"}),
            ("an urgent client invoice email in Freelancer Mode", {"freelancer", "email"}),
            ("keep private workspace data local and offline", {"privacy", "agent-academic-v1"}),
            ("sort gym at 7:30 AM before class at 9:00 AM in my checklist", {"checklist", "time"}),
            ("who founded Facebook?", {"knowledge-negative-correction"}),
        )

        with patch(
            "services.knowledge_service.KnowledgeDocument.get_all",
            return_value=db_documents,
        ):
            service = KnowledgeService()
            for query, expected_tags in cases:
                results = service.search(query, top_k=5, min_score=0.03)
                result_tags = {
                    tag
                    for result in results
                    for tag in str(result.get("tags") or "").split(",")
                }
                self.assertTrue(
                    expected_tags <= result_tags,
                    f"{query!r} retrieved {result_tags}",
                )


if __name__ == "__main__":
    unittest.main()
