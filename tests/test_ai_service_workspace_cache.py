import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import ai_service as ai_service_module  # noqa: E402

MESSAGES = [{"role": "user", "content": "same prompt text"}]


class AIServiceWorkspaceCacheTests(unittest.TestCase):
    """generate_response's response cache must never let a Business workspace
    reuse an answer generated for the Personal workspace (or another
    Business workspace) even when the raw prompt text is identical -- the
    injected workspace_context differs per tenant even when the user's own
    words happen to match. See services/ai_service.py's cache_key comment."""

    def _cache_key_used(self, workspace_id):
        seen = {}

        def fake_get(key, db_path=None):
            seen['key'] = key
            return {'response': 'cached answer', 'provider': 'demo'}

        service = ai_service_module.AIService()
        with (
            patch.object(ai_service_module.Config, 'BOB_LOCAL_ONLY', False),
            patch.object(ai_service_module, 'get_user_db_path', return_value='dummy.db'),
            patch.object(ai_service_module.Cache, 'get', side_effect=fake_get),
        ):
            result = service.generate_response(
                MESSAGES, task='chat', user_id='alice', workspace_id=workspace_id,
            )
        self.assertEqual('cached answer', result)
        return seen['key']

    def test_cache_key_differs_between_workspaces_for_identical_prompt(self):
        personal_key = self._cache_key_used('ws-personal')
        business_key = self._cache_key_used('ws-business')
        self.assertNotEqual(personal_key, business_key)

    def test_cache_key_is_stable_for_the_same_workspace(self):
        first = self._cache_key_used('ws-business')
        second = self._cache_key_used('ws-business')
        self.assertEqual(first, second)

    def test_cache_key_includes_user_id_and_workspace_id(self):
        key = self._cache_key_used('ws-business')
        self.assertTrue(key.startswith('ai::alice::ws-business::'))


if __name__ == '__main__':
    unittest.main()
