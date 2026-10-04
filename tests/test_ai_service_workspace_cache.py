import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import ai_service as ai_service_module  # noqa: E402

MESSAGES = [{"role": "user", "content": "same prompt text"}]


def _fake_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = '{}'
    return resp


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


class AIServiceProviderUsageParsingTests(unittest.TestCase):
    """Each provider adapter must return (text, usage_dict) parsed from
    that provider's own response shape -- these were previously discarded
    entirely, so ai_cost_log never had real token counts to record."""

    def setUp(self):
        self.service = ai_service_module.AIService()

    def test_openai_parses_usage_from_openai_compatible_shape(self):
        resp = _fake_response(200, {
            'choices': [{'message': {'content': 'hi'}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
        })
        with patch.object(ai_service_module.requests, 'post', return_value=resp), \
             patch.object(ai_service_module.Config, 'OPENAI_API_KEY', 'k'):
            text, usage = self.service._call_openai([], 10)
        self.assertEqual('hi', text)
        self.assertEqual({'input_tokens': 10, 'output_tokens': 5}, usage)

    def test_mistral_parses_usage_from_openai_compatible_shape(self):
        resp = _fake_response(200, {
            'choices': [{'message': {'content': 'hi'}}],
            'usage': {'prompt_tokens': 7, 'completion_tokens': 3},
        })
        with patch.object(ai_service_module.requests, 'post', return_value=resp), \
             patch.object(ai_service_module.Config, 'MISTRAL_API_KEY', 'k'):
            text, usage = self.service._call_mistral([], 10)
        self.assertEqual('hi', text)
        self.assertEqual({'input_tokens': 7, 'output_tokens': 3}, usage)

    def test_claude_parses_usage_from_anthropic_shape(self):
        resp = _fake_response(200, {
            'content': [{'type': 'text', 'text': 'hi'}],
            'usage': {'input_tokens': 20, 'output_tokens': 8},
        })
        with patch.object(ai_service_module.requests, 'post', return_value=resp), \
             patch.object(ai_service_module.Config, 'CLAUDE_API_KEY', 'k'):
            text, usage = self.service._call_claude([{'role': 'user', 'content': 'hi'}], 10)
        self.assertEqual('hi', text)
        self.assertEqual({'input_tokens': 20, 'output_tokens': 8}, usage)

    def test_gemini_parses_usage_from_usage_metadata(self):
        resp = _fake_response(200, {
            'candidates': [{'content': {'parts': [{'text': 'hi'}]}}],
            'usageMetadata': {'promptTokenCount': 12, 'candidatesTokenCount': 4},
        })
        with patch.object(ai_service_module.requests, 'post', return_value=resp), \
             patch.object(ai_service_module.Config, 'GEMINI_API_KEY', 'k'):
            text, usage = self.service._call_gemini([{'role': 'user', 'content': 'hi'}], 10)
        self.assertEqual('hi', text)
        self.assertEqual({'input_tokens': 12, 'output_tokens': 4}, usage)

    def test_ollama_parses_usage_from_top_level_eval_counts(self):
        resp = _fake_response(200, {
            'message': {'content': 'hi'},
            'prompt_eval_count': 9,
            'eval_count': 2,
        })
        with patch.object(ai_service_module.requests, 'post', return_value=resp), \
             patch.object(ai_service_module.Config, 'OLLAMA_ENABLED', True), \
             patch.object(ai_service_module.Config, 'BOB_LOCAL_ONLY', False):
            text, usage = self.service._call_ollama([], 10)
        self.assertEqual('hi', text)
        self.assertEqual({'input_tokens': 9, 'output_tokens': 2}, usage)

    def test_missing_usage_block_degrades_to_none_counts_without_raising(self):
        resp = _fake_response(200, {'choices': [{'message': {'content': 'hi'}}]})
        with patch.object(ai_service_module.requests, 'post', return_value=resp), \
             patch.object(ai_service_module.Config, 'OPENAI_API_KEY', 'k'):
            text, usage = self.service._call_openai([], 10)
        self.assertEqual('hi', text)
        self.assertIsNone(usage['input_tokens'])
        self.assertIsNone(usage['output_tokens'])


class AIServiceCostLogRecordingTests(unittest.TestCase):
    """generate_response must record a cost-log row on every exit path
    (cache hit, demo/no-provider, per-provider success, per-provider
    failure) and must never let a logging failure break the AI call it's
    observing."""

    def test_cache_hit_records_a_row_with_cache_hit_true(self):
        service = ai_service_module.AIService()
        with (
            patch.object(ai_service_module.Config, 'BOB_LOCAL_ONLY', False),
            patch.object(ai_service_module, 'get_user_db_path', return_value='dummy.db'),
            patch.object(ai_service_module.Cache, 'get', return_value={'response': 'cached', 'provider': 'demo'}),
            patch.object(ai_service_module.ai_cost_log, 'record_call') as record,
        ):
            result = service.generate_response(MESSAGES, task='chat', user_id='alice', workspace_id='ws')
        self.assertEqual('cached', result)
        record.assert_called_once()
        self.assertTrue(record.call_args.kwargs['cache_hit'])

    def test_no_configured_providers_records_a_free_demo_row(self):
        service = ai_service_module.AIService()
        with (
            patch.object(ai_service_module.Config, 'BOB_LOCAL_ONLY', False),
            patch.object(service, 'configured_providers', []),
            patch.object(ai_service_module.ai_cost_log, 'record_call') as record,
        ):
            service.generate_response(MESSAGES, task='chat')
        record.assert_called_once()
        self.assertEqual('demo', record.call_args.kwargs['provider'])
        self.assertTrue(record.call_args.kwargs['success'])

    def test_successful_provider_call_records_tokens_and_cost(self):
        service = ai_service_module.AIService()
        with (
            patch.object(ai_service_module.Config, 'BOB_LOCAL_ONLY', False),
            patch.object(service, 'configured_providers', ['openai']),
            patch.object(service, '_build_provider_chain', return_value=['openai']),
            patch.object(service, '_is_provider_healthy', return_value=True),
            patch.object(service, '_call_provider', return_value=('hi', {'input_tokens': 100, 'output_tokens': 50})),
            patch.object(ai_service_module.ai_cost_log, 'record_call') as record,
            # ai_service.py's own print()s emit emoji -- unrelated to this
            # test's assertions, and the Windows test runner's cp1252
            # stdout can't encode them. Silence print only, not the logic.
            patch('builtins.print'),
        ):
            result = service.generate_response(MESSAGES, task='chat')
        self.assertEqual('hi', result)
        record.assert_called_once()
        kwargs = record.call_args.kwargs
        self.assertTrue(kwargs['success'])
        self.assertEqual(100, kwargs['input_tokens'])
        self.assertEqual(50, kwargs['output_tokens'])
        self.assertEqual('openai', kwargs['provider'])

    def test_failed_provider_call_records_failure_without_raising(self):
        service = ai_service_module.AIService()
        with (
            patch.object(ai_service_module.Config, 'BOB_LOCAL_ONLY', False),
            patch.object(service, 'configured_providers', ['openai']),
            patch.object(service, '_build_provider_chain', return_value=['openai']),
            patch.object(service, '_is_provider_healthy', return_value=True),
            patch.object(service, '_call_provider', side_effect=RuntimeError('boom')),
            patch.object(ai_service_module.ai_cost_log, 'record_call') as record,
            patch('builtins.print'),
        ):
            # Falls through to the demo/bob-local fallback -- must not raise.
            service.generate_response(MESSAGES, task='chat')
        # One failure row for the provider attempt, one for the final fallback.
        self.assertEqual(2, record.call_count)
        failure_calls = [c for c in record.call_args_list if c.kwargs.get('success') is False]
        self.assertEqual(1, len(failure_calls))
        self.assertEqual('error', failure_calls[0].kwargs['error_type'])


class AICostLogNoOpTests(unittest.TestCase):
    """models.ai_cost_log must be a true no-op (no DB connection attempted,
    never raises) whenever Postgres isn't configured or tracking is off --
    this is an admin-observability feature, never load-bearing."""

    def test_record_call_is_noop_without_postgres(self):
        from models import ai_cost_log, postgres_db as pg
        with patch.object(pg, 'enabled', return_value=False), \
             patch.object(pg, 'connection') as connection:
            ai_cost_log.record_call(provider='openai', success=True)
        connection.assert_not_called()

    def test_record_call_is_noop_when_tracking_disabled(self):
        from models import ai_cost_log
        from config import Config
        with patch.object(Config, 'AI_COST_TRACKING_ENABLED', False), \
             patch('models.postgres_db.enabled', return_value=True) as enabled:
            ai_cost_log.record_call(provider='openai', success=True)
        enabled.assert_not_called()

    def test_record_call_never_raises_on_connection_failure(self):
        from models import ai_cost_log, postgres_db as pg
        with patch.object(pg, 'enabled', return_value=True), \
             patch.object(pg, 'connection', side_effect=RuntimeError('db down')):
            ai_cost_log.record_call(provider='openai', success=True)  # must not raise


if __name__ == '__main__':
    unittest.main()
