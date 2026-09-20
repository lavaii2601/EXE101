import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import Config  # noqa: E402
from models.knowledge import KnowledgeDocument  # noqa: E402
from models import workspace_subscription as subscription_module  # noqa: E402
from services.knowledge_service import KnowledgeService  # noqa: E402
from routes import workspace_knowledge as workspace_knowledge_route  # noqa: E402

WORKSPACE_A = "30000000-0000-4000-8000-00000000000a"
WORKSPACE_B = "30000000-0000-4000-8000-00000000000b"


class KnowledgeWorkspaceIsolationTests(unittest.TestCase):
    """Real SQLite DB (isolated temp file) -- cross-workspace isolation is
    the one thing this stage must never fake away with a mock, so these
    exercise the actual KnowledgeDocument/KnowledgeService filtering."""

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmp_dir.name, "test_knowledge.db")
        self._patcher = patch.object(Config, "DATABASE_PATH", self._db_path)
        self._patcher.start()
        KnowledgeDocument._initialized = False
        self.service = KnowledgeService()

    def tearDown(self):
        self._patcher.stop()
        KnowledgeDocument._initialized = False
        self._tmp_dir.cleanup()

    def test_business_doc_invisible_to_other_workspace(self):
        self.service.add_document(
            "Company policy", "Remote work allowed on Fridays",
            workspace_id=WORKSPACE_A, created_by_user_id="owner-a",
        )
        results_a = self.service.search(
            "remote work friday", user_id="alice", workspace_id=WORKSPACE_A, min_score=0.0,
        )
        results_b = self.service.search(
            "remote work friday", user_id="bob", workspace_id=WORKSPACE_B, min_score=0.0,
        )
        self.assertTrue(any(r["title"] == "Company policy" for r in results_a))
        self.assertFalse(any(r["title"] == "Company policy" for r in results_b))

    def test_global_and_personal_docs_still_visible_alongside_business(self):
        self.service.add_document("Global FAQ", "FlowMate feature onboarding guide")
        self.service.add_document(
            "Alice private note", "Alice personal reminder about deadline",
            source="auto", user_id="alice",
        )
        self.service.add_document(
            "Company policy", "Business onboarding guide for new hires",
            workspace_id=WORKSPACE_A, created_by_user_id="owner-a",
        )
        results = self.service.search(
            "onboarding guide reminder deadline", user_id="alice",
            workspace_id=WORKSPACE_A, top_k=10, min_score=0.0,
        )
        titles = {r["title"] for r in results}
        self.assertIn("Global FAQ", titles)
        self.assertIn("Alice private note", titles)
        self.assertIn("Company policy", titles)

    def test_personal_doc_never_visible_to_a_different_user_in_the_same_workspace(self):
        self.service.add_document(
            "Alice private note", "a very specific secret reminder",
            source="auto", user_id="alice",
        )
        results = self.service.search(
            "specific secret reminder", user_id="bob", workspace_id=WORKSPACE_A, min_score=0.0,
        )
        self.assertFalse(any(r["title"] == "Alice private note" for r in results))

    def test_scope_field_labels_each_tier_correctly(self):
        self.service.add_document("Global doc", "shared onboarding info for everyone")
        self.service.add_document(
            "Biz doc", "shared onboarding info for workspace members",
            workspace_id=WORKSPACE_A, created_by_user_id="owner-a",
        )
        results = self.service.search(
            "shared onboarding info", user_id="alice", workspace_id=WORKSPACE_A, min_score=0.0,
        )
        scopes = {r["title"]: r["scope"] for r in results}
        self.assertEqual("global", scopes.get("Global doc"))
        self.assertEqual("business", scopes.get("Biz doc"))

    def test_answer_search_can_exclude_labelled_intent_training_documents(self):
        self.service.add_document(
            "Bob intent 750 - email.latest_summary - phan 15",
            "khung long mau gi intent email.latest_summary",
            tags="bob,training,intent,email.latest_summary,750-cases",
            source="bob-intent-500-v1",
        )
        self.service.add_document(
            "Dinosaur colours",
            "Bang chung hoa thach giup nghien cuu mau cua khung long",
            source="manual",
        )

        results = self.service.search(
            "khung long mau gi",
            top_k=10,
            min_score=0.0,
            user_id="alice",
            excluded_sources={"bob-intent-500-v1"},
        )
        titles = {result["title"] for result in results}
        self.assertIn("Dinosaur colours", titles)
        self.assertNotIn("Bob intent 750 - email.latest_summary - phan 15", titles)

    def test_list_for_workspace_returns_only_that_workspaces_docs(self):
        self.service.add_document("A doc", "content", workspace_id=WORKSPACE_A, created_by_user_id="owner-a")
        self.service.add_document("B doc", "content", workspace_id=WORKSPACE_B, created_by_user_id="owner-b")
        self.service.add_document("Global doc", "content")
        docs_a = self.service.list_for_workspace(WORKSPACE_A)
        self.assertEqual({"A doc"}, {d["title"] for d in docs_a})

    def test_get_workspace_document_rejects_cross_workspace_id_guessing(self):
        doc = self.service.add_document("A doc", "content", workspace_id=WORKSPACE_A, created_by_user_id="owner-a")
        self.assertIsNone(self.service.get_workspace_document(WORKSPACE_B, doc["id"]))
        self.assertIsNotNone(self.service.get_workspace_document(WORKSPACE_A, doc["id"]))

    def test_auto_learned_memory_never_gets_a_workspace_id(self):
        # learn_from_exchange / mentor / web-research callers never pass
        # workspace_id -- confirms KnowledgeDocument.create's default keeps
        # them personal-only even inside a Business workspace chat.
        doc = self.service.add_document(
            "Auto memory", "Bob inferred this during a chat", source="auto", user_id="alice",
        )
        self.assertIsNone(doc.get("workspace_id"))


class WorkspaceKnowledgeRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(TESTING=True, SECRET_KEY="test")
        cls.app.register_blueprint(workspace_knowledge_route.workspace_knowledge_bp)

    def _resolve_as(self, role, workspace_type="business"):
        workspace = {"id": WORKSPACE_A, "type": workspace_type}
        membership = {"role": role, "status": "active"}
        return (
            patch.object(workspace_knowledge_route, "get_current_user_id", return_value="alice"),
            patch.object(
                workspace_knowledge_route.workspace_model, "resolve_context",
                return_value=(workspace, membership),
            ),
        )

    def test_worker_can_list(self):
        p1, p2 = self._resolve_as("worker")
        with p1, p2, patch.object(workspace_knowledge_route.knowledge_service, "list_for_workspace", return_value=[]):
            response = self.app.test_client().get("/api/workspace-knowledge")
        self.assertEqual(200, response.status_code)

    def test_worker_cannot_create(self):
        p1, p2 = self._resolve_as("worker")
        with p1, p2:
            response = self.app.test_client().post(
                "/api/workspace-knowledge", json={"title": "t", "content": "c"},
            )
        self.assertEqual(403, response.status_code)
        self.assertEqual("insufficient_role", response.get_json()["error"])

    def test_owner_can_create(self):
        p1, p2 = self._resolve_as("owner")
        with (
            p1, p2,
            patch.object(
                workspace_knowledge_route.knowledge_service, "add_document",
                return_value={"id": 1, "title": "t", "content": "c"},
            ),
            patch.object(workspace_knowledge_route.workspace_model, "record_audit_event") as audit,
        ):
            response = self.app.test_client().post(
                "/api/workspace-knowledge", json={"title": "t", "content": "c"},
            )
        self.assertEqual(201, response.status_code)
        audit.assert_called_once_with(
            WORKSPACE_A, "alice", "knowledge_document_created",
            target_type="knowledge_document", target_id="1",
            metadata={"title": "t"},
        )

    def test_owner_can_update(self):
        p1, p2 = self._resolve_as("owner")
        with (
            p1, p2,
            patch.object(
                workspace_knowledge_route.knowledge_service, "get_workspace_document",
                return_value={"id": 1, "title": "old", "content": "c"},
            ),
            patch.object(
                workspace_knowledge_route.knowledge_service, "update_document",
                return_value={"id": 1, "title": "new", "content": "c"},
            ),
            patch.object(workspace_knowledge_route.workspace_model, "record_audit_event") as audit,
        ):
            response = self.app.test_client().patch(
                "/api/workspace-knowledge/1", json={"title": "new"},
            )
        self.assertEqual(200, response.status_code)
        audit.assert_called_once_with(
            WORKSPACE_A, "alice", "knowledge_document_updated",
            target_type="knowledge_document", target_id="1",
            metadata={"fields": ["title"]},
        )

    def test_owner_can_delete(self):
        p1, p2 = self._resolve_as("owner")
        with (
            p1, p2,
            patch.object(
                workspace_knowledge_route.knowledge_service, "get_workspace_document",
                return_value={"id": 1, "title": "old", "content": "c"},
            ),
            patch.object(workspace_knowledge_route.knowledge_service, "delete_document"),
            patch.object(workspace_knowledge_route.workspace_model, "record_audit_event") as audit,
        ):
            response = self.app.test_client().delete("/api/workspace-knowledge/1")
        self.assertEqual(200, response.status_code)
        audit.assert_called_once_with(
            WORKSPACE_A, "alice", "knowledge_document_deleted",
            target_type="knowledge_document", target_id="1",
            metadata={"title": "old"},
        )

    def test_admin_create_requires_title_and_content(self):
        p1, p2 = self._resolve_as("admin")
        with p1, p2:
            response = self.app.test_client().post(
                "/api/workspace-knowledge", json={"title": "", "content": "c"},
            )
        self.assertEqual(400, response.status_code)
        self.assertEqual("knowledge_title_required", response.get_json()["error"])

    def test_read_only_workspace_blocks_create(self):
        p1, p2 = self._resolve_as("owner")
        with p1, p2, patch.object(
            workspace_knowledge_route.workspace_subscription, "assert_writable",
            side_effect=subscription_module.WorkspaceSubscriptionError("workspace_read_only"),
        ):
            response = self.app.test_client().post(
                "/api/workspace-knowledge", json={"title": "t", "content": "c"},
            )
        self.assertEqual(403, response.status_code)
        self.assertEqual("workspace_read_only", response.get_json()["error"])

    def test_update_rejects_doc_from_a_different_workspace(self):
        p1, p2 = self._resolve_as("owner")
        with p1, p2, patch.object(
            workspace_knowledge_route.knowledge_service, "get_workspace_document", return_value=None,
        ):
            response = self.app.test_client().patch(
                "/api/workspace-knowledge/999", json={"title": "new"},
            )
        self.assertEqual(404, response.status_code)
        self.assertEqual("knowledge_not_found", response.get_json()["error"])

    def test_worker_cannot_delete(self):
        p1, p2 = self._resolve_as("worker")
        with p1, p2:
            response = self.app.test_client().delete("/api/workspace-knowledge/1")
        self.assertEqual(403, response.status_code)


if __name__ == "__main__":
    unittest.main()
