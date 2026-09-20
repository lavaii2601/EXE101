import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOBILE_ROOT = PROJECT_ROOT / 'mobile'


class MobileWorkerModeParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (MOBILE_ROOT / 'App.js').read_text(encoding='utf-8')
        cls.worker_hub = (
            MOBILE_ROOT / 'src/screens/WorkerModeScreen.js'
        ).read_text(encoding='utf-8')
        cls.work_hub = (
            MOBILE_ROOT / 'src/screens/WorkHubScreen.js'
        ).read_text(encoding='utf-8')
        cls.knowledge = (
            MOBILE_ROOT / 'src/screens/WorkspaceKnowledgeScreen.js'
        ).read_text(encoding='utf-8')
        cls.settings = (
            MOBILE_ROOT / 'src/screens/SettingsScreen.js'
        ).read_text(encoding='utf-8')

    def test_worker_modes_expose_a_first_class_work_tab(self):
        self.assertIn("key: 'work'", self.app)
        self.assertIn('workerOnly: true', self.app)
        self.assertIn("userMode === 'worker' || userMode === 'business'", self.app)
        self.assertIn('<WorkerModeScreen syncEvent={syncEvent} />', self.app)

    def test_worker_hub_connects_all_workspace_tools(self):
        self.assertIn("apiGet('/work-hub/dashboard')", self.worker_hub)
        for screen in (
            'WorkHubScreen',
            'StatusReportsScreen',
            'WorkspaceKnowledgeScreen',
            'WorkspaceMembersScreen',
            'SharingCenterScreen',
        ):
            self.assertIn(f'<{screen} ', self.worker_hub)
        for sync_target in ('work_hub', 'status_reports', 'workspace_members'):
            self.assertIn(f"'{sync_target}'", self.worker_hub)
        self.assertIn('dashboard.task_counts?.blocked', self.worker_hub)
        self.assertIn('onClose={closeTool}', self.worker_hub)

    def test_workspace_knowledge_supports_shared_crud_and_sync(self):
        self.assertIn("apiGet('/workspace-knowledge')", self.knowledge)
        self.assertIn("apiPost('/workspace-knowledge'", self.knowledge)
        self.assertIn('apiDelete(`/workspace-knowledge/${document.id}`)', self.knowledge)
        self.assertIn("'workspace_knowledge'", self.knowledge)
        self.assertIn('workspace.canManage', self.knowledge)
        self.assertIn('<WorkspaceKnowledgeScreen ', self.settings)

    def test_mobile_project_creation_matches_web_date_fields(self):
        self.assertIn('start_date: toDateOnly(projectStartDate)', self.work_hub)
        self.assertIn('due_date: toDateOnly(projectDueDate)', self.work_hub)


if __name__ == '__main__':
    unittest.main()
