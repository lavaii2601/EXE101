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


class AIServiceMeetingConfirmationTests(unittest.TestCase):
    """AIService.confirm_meeting_extraction must stay on the regex
    candidate for any disabled/unconfigured/invalid-response path, and
    only ever accept a result with a concrete, parseable start_time."""

    def setUp(self):
        self.service = ai_service_module.AIService()
        self.email = {'subject': 'Họp dự án', 'sender': 'a@example.com', 'body': 'noi dung'}
        self.regex_candidate = {'title': 'Họp dự án', 'start_time': None}

    def test_returns_none_when_feature_disabled(self):
        with patch.object(ai_service_module.Config, 'AI_MEETING_CONFIRM_ENABLED', False):
            result = self.service.confirm_meeting_extraction(self.email, self.regex_candidate)
        self.assertIsNone(result)

    def test_returns_none_when_local_only(self):
        with patch.object(ai_service_module.Config, 'AI_MEETING_CONFIRM_ENABLED', True), \
             patch.object(ai_service_module.Config, 'BOB_LOCAL_ONLY', True):
            result = self.service.confirm_meeting_extraction(self.email, self.regex_candidate)
        self.assertIsNone(result)

    def test_returns_none_when_ai_json_is_malformed(self):
        with patch.object(ai_service_module.Config, 'AI_MEETING_CONFIRM_ENABLED', True), \
             patch.object(ai_service_module.Config, 'BOB_LOCAL_ONLY', False), \
             patch.object(self.service, 'configured_providers', ['openai']), \
             patch.object(self.service, 'generate_response', return_value='not json'):
            self.service.last_provider_used = 'openai'
            result = self.service.confirm_meeting_extraction(self.email, self.regex_candidate)
        self.assertIsNone(result)

    def test_returns_none_when_start_time_missing_from_ai_response(self):
        with patch.object(ai_service_module.Config, 'AI_MEETING_CONFIRM_ENABLED', True), \
             patch.object(ai_service_module.Config, 'BOB_LOCAL_ONLY', False), \
             patch.object(self.service, 'configured_providers', ['openai']), \
             patch.object(self.service, 'generate_response',
                           return_value='{"is_meeting": true, "start_time": null}'):
            self.service.last_provider_used = 'openai'
            result = self.service.confirm_meeting_extraction(self.email, self.regex_candidate)
        self.assertIsNone(result)

    def test_accepts_a_valid_response_and_clamps_confidence(self):
        raw = (
            '{"is_meeting": true, "title": "Họp dự án", '
            '"start_time": "2026-07-20T10:00:00", "end_time": null, '
            '"location": "", "attendees": "", "confidence": 1.4}'
        )
        with patch.object(ai_service_module.Config, 'AI_MEETING_CONFIRM_ENABLED', True), \
             patch.object(ai_service_module.Config, 'BOB_LOCAL_ONLY', False), \
             patch.object(self.service, 'configured_providers', ['openai']), \
             patch.object(self.service, 'generate_response', return_value=raw):
            self.service.last_provider_used = 'openai'
            result = self.service.confirm_meeting_extraction(self.email, self.regex_candidate)
        self.assertIsNotNone(result)
        self.assertEqual('2026-07-20T10:00:00', result['start_time'])
        self.assertEqual(0.97, result['confidence'])

    def test_rejects_the_demo_fallback_sentinel(self):
        """generate_response never raises for provider exhaustion -- it
        silently degrades to 'demo'/'bob-local' instead. That must not be
        mistaken for a genuine AI-confirmed result."""
        raw = '{"is_meeting": true, "start_time": "2026-07-20T10:00:00"}'
        with patch.object(ai_service_module.Config, 'AI_MEETING_CONFIRM_ENABLED', True), \
             patch.object(ai_service_module.Config, 'BOB_LOCAL_ONLY', False), \
             patch.object(self.service, 'configured_providers', ['openai']), \
             patch.object(self.service, 'generate_response', return_value=raw):
            self.service.last_provider_used = 'demo'
            result = self.service.confirm_meeting_extraction(self.email, self.regex_candidate)
        self.assertIsNone(result)


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


class AIServiceChatProviderPriorityTests(unittest.TestCase):
    """Bob's Chat tab (task='chat') tries OpenAI first when it's healthy and
    configured, falling back to the rest of the normal chain otherwise --
    Claude is out of credits and Gemini was only recently fixed, so OpenAI
    is the one provider that's actually been reliable. See config.py's
    AI_TASK_PROVIDERS_CHAT and _build_provider_chain's task_overrides
    handling, which this exercises directly rather than re-deriving."""

    def test_openai_is_tried_first_even_when_round_robin_would_pick_another(self):
        service = ai_service_module.AIService()
        service.configured_providers = ['claude', 'openai', 'gemini']
        service.provider_rotation_index = 0  # round-robin alone would pick 'claude'
        chain = service._build_provider_chain(task='chat')
        self.assertEqual('openai', chain[0])
        self.assertEqual({'claude', 'openai', 'gemini'}, set(chain))

    def test_openai_in_cooldown_still_falls_back_to_the_rest_of_the_chain(self):
        from datetime import datetime
        service = ai_service_module.AIService()
        service.configured_providers = ['claude', 'openai', 'gemini']
        service.provider_health = {'openai': {'failed_at': datetime.now()}}
        chain = service._build_provider_chain(task='chat')
        self.assertNotIn('openai', chain)
        self.assertTrue(chain)
        self.assertTrue(set(chain) <= {'claude', 'gemini'})

    def test_other_tasks_are_unaffected_by_the_chat_override(self):
        service = ai_service_module.AIService()
        service.configured_providers = ['claude', 'openai', 'gemini']
        service.provider_rotation_index = 0
        chain = service._build_provider_chain(task='summary')
        self.assertEqual('claude', chain[0])


class EmailSummaryAITests(unittest.TestCase):
    """summarize_email_polished (the Email tab's 'Tóm tắt' feature) tries a
    real AI-generated summary first, but must fall back to the fully local
    extractive summarizer whenever the AI call fails, is unconfigured, or
    returns something unusable (the demo-mode sentinel, or text that
    ignores the TÓM TẮT/CẦN LÀM/THỜI HẠN format the summary-card UI
    parses) -- this feature must keep working even when every AI provider
    is down, exactly like every other 'AI first, deterministic fallback'
    path in this codebase."""

    def setUp(self):
        self.service = ai_service_module.AIService()
        self.email = {
            'subject': 'Duyệt ngân sách Q4',
            'sender': 'ceo@example.com',
            'to': 'me@example.com',
            'body': (
                'Ngân sách Q4 đã tăng lên 250 triệu đồng. '
                'Vui lòng xác nhận trước 17:00 ngày 25/09/2026.'
            ),
            'attachments': [],
        }

    def test_uses_ai_summary_when_provider_configured_and_well_formed(self):
        ai_text = "TÓM TẮT\nNgân sách Q4 tăng lên 250 triệu đồng.\n\nTHỜI HẠN\n- 17:00 ngày 25/09/2026"
        with patch.object(self.service, 'configured_providers', ['openai']), \
             patch.object(self.service, 'generate_response', return_value=ai_text) as generate:
            self.service.last_provider_used = 'openai'
            result = self.service.summarize_email_polished(self.email)
        generate.assert_called_once()
        self.assertIn('Ngân sách Q4 tăng lên 250 triệu đồng.', result)
        self.assertNotIn('ĐIỂM CHÍNH', result)  # AI prompt omits this section for conciseness

    def test_ai_summary_keeps_deterministic_links_section(self):
        email = dict(self.email)
        email['body'] = email['body'] + ' Xem chi tiết tại https://example.com/budget-report'
        ai_text = "TÓM TẮT\nNgân sách Q4 tăng lên 250 triệu đồng."
        with patch.object(self.service, 'configured_providers', ['openai']), \
             patch.object(self.service, 'generate_response', return_value=ai_text):
            self.service.last_provider_used = 'openai'
            result = self.service.summarize_email_polished(email)
        self.assertIn('TÀI LIỆU', result)
        self.assertIn('example.com/budget-report', result)

    def test_model_hallucinated_documents_section_is_discarded_not_duplicated(self):
        """The prompt tells the model never to add its own TÀI LIỆU section,
        but that's an instruction, not a guarantee. If it disobeys anyway,
        its fabricated version must be dropped entirely -- never merged
        alongside the real one -- or a fabricated link could reach the UI."""
        email = dict(self.email)
        email['body'] = email['body'] + ' Xem chi tiết tại https://example.com/budget-report'
        ai_text = (
            "TÓM TẮT\nNgân sách Q4 tăng lên 250 triệu đồng.\n\n"
            "TÀI LIỆU\n- Liên kết: https://fake-phishing-site.example/claim"
        )
        with patch.object(self.service, 'configured_providers', ['openai']), \
             patch.object(self.service, 'generate_response', return_value=ai_text):
            self.service.last_provider_used = 'openai'
            result = self.service.summarize_email_polished(email)
        self.assertNotIn('fake-phishing-site', result)
        self.assertIn('example.com/budget-report', result)
        self.assertEqual(1, result.count('TÀI LIỆU'))

    def test_model_hallucinated_documents_section_dropped_with_no_real_replacement(self):
        """Same as above, but when there are no real attachments/links to
        append -- the fake section must simply disappear, not survive
        because "there was nothing to replace it with"."""
        ai_text = (
            "TÓM TẮT\nNgân sách Q4 tăng lên 250 triệu đồng.\n\n"
            "TÀI LIỆU\n- Liên kết: https://fake-phishing-site.example/claim"
        )
        with patch.object(self.service, 'configured_providers', ['openai']), \
             patch.object(self.service, 'generate_response', return_value=ai_text):
            self.service.last_provider_used = 'openai'
            result = self.service.summarize_email_polished(self.email)
        self.assertNotIn('fake-phishing-site', result)
        self.assertEqual(0, result.count('TÀI LIỆU'))

    def test_falls_back_to_extractive_when_no_provider_configured(self):
        with patch.object(self.service, 'configured_providers', []), \
             patch.object(self.service, 'generate_response') as generate:
            result = self.service.summarize_email_polished(self.email)
        generate.assert_not_called()
        self.assertIn('250 triệu đồng', result)  # verbatim extractive evidence

    def test_falls_back_to_extractive_when_ai_call_raises(self):
        with patch.object(self.service, 'configured_providers', ['openai']), \
             patch.object(self.service, 'generate_response', side_effect=RuntimeError('boom')):
            result = self.service.summarize_email_polished(self.email)
        self.assertIn('250 triệu đồng', result)

    def test_rejects_demo_fallback_sentinel_even_if_well_formed(self):
        """generate_response never raises for provider exhaustion -- it
        silently degrades to the demo-mode canned response instead. That
        text could coincidentally contain 'TÓM TẮT' and must still not be
        trusted as a real AI answer."""
        ai_text = "TÓM TẮT\nMột câu trả lời demo không liên quan."
        with patch.object(self.service, 'configured_providers', ['openai']), \
             patch.object(self.service, 'generate_response', return_value=ai_text):
            self.service.last_provider_used = 'demo'
            result = self.service.summarize_email_polished(self.email)
        self.assertIn('250 triệu đồng', result)
        self.assertNotIn('Một câu trả lời demo không liên quan', result)

    def test_rejects_ai_output_missing_required_header(self):
        with patch.object(self.service, 'configured_providers', ['openai']), \
             patch.object(self.service, 'generate_response', return_value='Ngân sách đã tăng.'):
            self.service.last_provider_used = 'openai'
            result = self.service.summarize_email_polished(self.email)
        self.assertIn('250 triệu đồng', result)


class AIServiceFallbackBudgetTests(unittest.TestCase):
    """generate_response's provider loop previously had no overall time cap
    -- a chain of several degraded providers, each blocking up to
    AI_REQUEST_TIMEOUT before failing over, could tie up a request-handling
    thread (this app's actual concurrency ceiling) for minutes."""

    def setUp(self):
        self.service = ai_service_module.AIService()

    def test_stops_trying_more_providers_once_total_budget_is_exhausted(self):
        # Real (tiny) sleep, not a mocked clock: more robust against
        # incidental extra time.monotonic() calls elsewhere in the loop
        # than asserting on call order/count against a mocked clock would be.
        import time as time_module

        attempted = []

        def fake_call_provider(provider, *args, **kwargs):
            attempted.append(provider)
            time_module.sleep(0.08)
            raise RuntimeError(f"{provider} is down")

        with (
            patch.object(ai_service_module.Config, 'AI_FALLBACK_TOTAL_BUDGET_SECONDS', 0.05),
            patch.object(self.service, 'configured_providers', ['openai', 'claude', 'gemini']),
            patch.object(self.service, '_build_provider_chain', return_value=['openai', 'claude', 'gemini']),
            patch.object(self.service, '_is_provider_healthy', return_value=True),
            patch.object(ai_service_module.admin_ops, 'current_budget_state', return_value={'allowed': True}),
            patch.object(self.service, '_call_provider', side_effect=fake_call_provider),
        ):
            self.service.generate_response([{"role": "user", "content": "hi"}], task='chat')

        # Only the first provider should have been attempted -- its own
        # 0.08s already exceeds the 0.05s total budget, so the loop must
        # stop before trying a second one.
        self.assertEqual(['openai'], attempted)

    def test_first_provider_is_still_tried_even_with_a_near_zero_budget(self):
        """The budget caps the FALLBACK chain, not the first attempt -- a
        tiny/misconfigured budget must never prevent trying any provider
        at all, only stop further failover after it's exhausted."""
        with (
            patch.object(ai_service_module.Config, 'AI_FALLBACK_TOTAL_BUDGET_SECONDS', 45),
            patch.object(self.service, 'configured_providers', ['openai']),
            patch.object(self.service, '_build_provider_chain', return_value=['openai']),
            patch.object(self.service, '_is_provider_healthy', return_value=True),
            patch.object(ai_service_module.admin_ops, 'current_budget_state', return_value={'allowed': True}),
            patch.object(self.service, '_call_provider', return_value=('hello', {})),
        ):
            result = self.service.generate_response([{"role": "user", "content": "hi"}], task='chat')
        self.assertEqual('hello', result)


if __name__ == '__main__':
    unittest.main()
