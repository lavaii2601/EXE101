import os
import sys
import logging
import json
import re
import requests
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from services.openrouter_service import OpenRouterService
from services import extractive_summary
from services.ai_json_utils import parse_json_object
from models import ai_cost_log
from models.cache import Cache
from models import subscription as subscription_model
from utils.user_context import get_user_db_path
import hashlib
from urllib.parse import urlparse

# Configure module logger
logger = logging.getLogger(__name__)

# Demo responses khi hết quota
DEMO_RESPONSES = {
    "tóm tắt": "Đây là tóm tắt email:\n- Điểm chính 1: Nội dung quan trọng\n- Điểm chính 2: Thông tin cần chú ý\n- Hành động: Cần phản hồi trong 24h",
    "lịch": "Tôi đề xuất lên lịch hẹn vào ngày mai lúc 14:00 để thảo luận chi tiết.",
    "default": "Xin chào! Tôi là Lunex - trợ lý AI thông minh. Tôi có thể giúp bạn với:\n- Phân tích email\n- Lên lịch hẹn\n- Quản lý công việc\n- Và nhiều hơn nữa!\n\n(Hiện đang ở mode Demo - hết quota API)"
}

# Appended to prompts whose output is shown as plain text (email body, schedule
# fields) so the model doesn't emit raw HTML/Markdown markup like <b> or **text**.
PLAIN_TEXT_INSTRUCTION = (
    " Chỉ viết văn bản thuần (plain text). KHÔNG dùng thẻ HTML (như <b>, </b>, <i>, <br>, <p>) "
    "và KHÔNG dùng ký hiệu Markdown (**, __, #, ``` , -). Nếu cần nhấn mạnh, dùng chữ thường "
    "và xuống dòng rõ ràng."
)

_HTML_TAG_RE = re.compile(r'</?[a-zA-Z][a-zA-Z0-9]*\s*/?>')
_MD_BOLD_RE = re.compile(r'\*\*(.+?)\*\*|__(.+?)__')


def strip_markup(text):
    """Remove stray HTML tags and Markdown bold markers from AI output
    so plain-text fields (email body, schedule fields) don't show raw
    formatting like <b> or **text**."""
    if not text:
        return text
    cleaned = _HTML_TAG_RE.sub('', text)
    cleaned = _MD_BOLD_RE.sub(lambda m: m.group(1) or m.group(2), cleaned)
    return cleaned

# Quota/rate limit error keywords
QUOTA_ERROR_KEYWORDS = [
    'quota', 'rate_limit', 'insufficient_quota', 'quota_exceeded',
    'rate limit', 'too many requests', 'billing', 'overloaded',
    'capacity', 'throttled', 'exceeded your current quota'
]

class AIService:
    # Premium users get responses routed through these providers first (when
    # configured and healthy) before falling back to the normal round-robin
    # chain -- a soft quality preference, not a hard requirement, so full
    # failover resilience for Free users is unaffected.
    PREMIUM_PREFERRED_PROVIDERS = ['claude', 'openai', 'openrouter', 'gemini', 'mistral', 'ollama']
    PREMIUM_MAX_TOKENS_MULTIPLIER = 1.4

    def __init__(self):
        self.timeout = Config.AI_REQUEST_TIMEOUT
        self.max_context_messages = Config.AI_MAX_CONTEXT_MESSAGES
        self.max_input_chars = Config.AI_MAX_INPUT_CHARS
        self.max_system_prompt_chars = Config.AI_MAX_SYSTEM_PROMPT_CHARS
        self.default_max_tokens = Config.AI_DEFAULT_MAX_TOKENS
        self.task_max_tokens = {
            'chat': Config.AI_DEFAULT_MAX_TOKENS,
            'summary': Config.AI_SUMMARY_MAX_TOKENS,
            'reply': Config.AI_REPLY_MAX_TOKENS,
            'analyze': Config.AI_ANALYZE_MAX_TOKENS,
            'intent_classification': 320,
            'overview_brief': Config.AI_OVERVIEW_BRIEF_MAX_TOKENS,
            'meeting_confirm': Config.AI_MEETING_CONFIRM_MAX_TOKENS,
        }
        self.provider_order = [
            p.strip().lower() for p in Config.AI_PROVIDER_ORDER.split(',') if p.strip()
        ]
        self.primary_provider = Config.AI_PRIMARY_PROVIDER
        self.task_provider_overrides = {
            'chat': self._parse_provider_list(Config.AI_TASK_PROVIDERS_CHAT),
            'summary': self._parse_provider_list(Config.AI_TASK_PROVIDERS_SUMMARY),
            'reply': self._parse_provider_list(Config.AI_TASK_PROVIDERS_REPLY),
            'analyze': self._parse_provider_list(Config.AI_TASK_PROVIDERS_ANALYZE),
            'intent_classification': self._parse_provider_list(Config.AI_TASK_PROVIDERS_INTENT_CLASSIFICATION),
            'overview_brief': self._parse_provider_list(Config.AI_TASK_PROVIDERS_OVERVIEW_BRIEF),
            'meeting_confirm': self._parse_provider_list(Config.AI_TASK_PROVIDERS_MEETING_CONFIRM),
        }
        # Which model SIZE each task uses ('cheap' vs 'strong') -- see
        # _model_for() below for how a tier resolves to an actual model
        # name per provider. Unknown tasks default to 'strong' (today's
        # single-model behavior, unchanged).
        self.task_tiers = {
            'chat': self._normalize_tier(Config.AI_TASK_TIER_CHAT, 'strong'),
            'intent_classification': self._normalize_tier(Config.AI_TASK_TIER_INTENT_CLASSIFICATION, 'cheap'),
            'summary': self._normalize_tier(Config.AI_TASK_TIER_SUMMARY, 'cheap'),
            'reply': self._normalize_tier(Config.AI_TASK_TIER_REPLY, 'cheap'),
            'analyze': self._normalize_tier(Config.AI_TASK_TIER_ANALYZE, 'cheap'),
            'overview_brief': self._normalize_tier(Config.AI_TASK_TIER_OVERVIEW_BRIEF, 'cheap'),
            'meeting_confirm': self._normalize_tier(Config.AI_TASK_TIER_MEETING_CONFIRM, 'cheap'),
        }
        # Per-provider model name for each tier. Every 'cheap' entry
        # defaults to that provider's own strong model (Config.X_MODEL_CHEAP
        # falls back to Config.X_MODEL when unset), so tiering is a no-op
        # on model choice until an operator explicitly configures a cheap
        # model for a provider.
        self.provider_models = {
            'openai': {'strong': Config.OPENAI_MODEL, 'cheap': Config.OPENAI_MODEL_CHEAP},
            'mistral': {'strong': Config.MISTRAL_MODEL, 'cheap': Config.MISTRAL_MODEL_CHEAP},
            'claude': {'strong': Config.CLAUDE_MODEL, 'cheap': Config.CLAUDE_MODEL_CHEAP},
            'gemini': {'strong': Config.GEMINI_MODEL, 'cheap': Config.GEMINI_MODEL_CHEAP},
            'ollama': {'strong': Config.OLLAMA_MODEL, 'cheap': Config.OLLAMA_MODEL_CHEAP},
            'openrouter': {
                'strong': Config.OPENROUTER_PRIMARY_MODEL,
                'cheap': Config.OPENROUTER_PRIMARY_MODEL_CHEAP,
            },
        }
        self.last_provider_used = None
        self.provider_usage = {
            'bob-local': 0,
            'openrouter': 0,
            'openai': 0,
            'mistral': 0,
            'claude': 0,
            'gemini': 0,
            'ollama': 0,
            'demo': 0
        }
        
        # Round-robin rotation and health tracking
        self.provider_rotation_index = 0
        self.provider_health = {}  # {provider: {'failed_at': timestamp, 'errors': count}}
        self.provider_cooldown_minutes = 5  # Wait 5 minutes before retrying failed provider
        self.quota_error_cooldown_minutes = 30  # Wait 30 minutes for quota errors

        self.configured_providers = self._detect_configured_providers()

        # instantiate OpenRouterService when configured
        self.openrouter_service = None
        if 'openrouter' in self.configured_providers:
            try:
                self.openrouter_service = OpenRouterService(timeout=self.timeout)
            except Exception:
                self.openrouter_service = None

        if Config.BOB_LOCAL_ONLY:
            if 'ollama' in self.configured_providers:
                logger.info("Bob local-only engine enabled with self-hosted Ollama")
            else:
                logger.info("Bob local-only deterministic engine enabled; Ollama is not configured")
        elif not self.configured_providers:
            logger.warning("⚠️  Không có AI provider khả dụng - sử dụng Demo Mode")
    def _is_quota_error(self, error_message, status_code=None):
        """Detect if error is related to quota/rate limits"""
        if status_code in [429, 402, 403]:  # Too many requests, payment required, forbidden
            return True
        
        error_lower = str(error_message).lower()
        return any(keyword in error_lower for keyword in QUOTA_ERROR_KEYWORDS)
    
    def _mark_provider_failed(self, provider, error_message, is_quota_error=False):
        """Mark a provider as temporarily failed with cooldown"""
        cooldown = self.quota_error_cooldown_minutes if is_quota_error else self.provider_cooldown_minutes
        self.provider_health[provider] = {
            'failed_at': datetime.now(),
            'error': str(error_message)[:200],
            'is_quota_error': is_quota_error,
            'cooldown_minutes': cooldown
        }
        error_type = "QUOTA" if is_quota_error else "ERROR"
        print(f"🔴 {provider.upper()} {error_type}: {error_message[:100]} (cooldown: {cooldown}min)")
    
    def _is_provider_healthy(self, provider):
        """Check if provider is healthy (not in cooldown period)"""
        if provider not in self.provider_health:
            return True
        
        health = self.provider_health[provider]
        failed_at = health.get('failed_at')
        cooldown = health.get('cooldown_minutes', self.provider_cooldown_minutes)
        
        if not failed_at:
            return True
        
        # Check if cooldown period has passed
        time_passed = datetime.now() - failed_at
        if time_passed > timedelta(minutes=cooldown):
            # Reset health status
            del self.provider_health[provider]
            print(f"✅ {provider.upper()} cooldown ended - back to healthy")
            return True
        
        # Still in cooldown
        remaining = cooldown - (time_passed.total_seconds() / 60)
        return False
    
    def _get_next_round_robin_provider(self):
        """Get next provider in round-robin rotation"""
        if not self.configured_providers:
            return None
        
        healthy_providers = [p for p in self.configured_providers if self._is_provider_healthy(p)]
        
        if not healthy_providers:
            return None  # All providers in cooldown
        
        # Rotate through healthy providers
        provider = healthy_providers[self.provider_rotation_index % len(healthy_providers)]
        self.provider_rotation_index += 1
        
        return provider
    
    def generate_response(self, messages, max_tokens=None, task='chat', user_id=None, workspace_id=None):
        """Generate AI response using round-robin rotation with intelligent fallback"""
        if Config.BOB_LOCAL_ONLY and not self.configured_providers:
            self.last_provider_used = 'bob-local'
            self.provider_usage['bob-local'] += 1
            ai_cost_log.record_call(
                user_id=user_id, workspace_id=workspace_id, task=task,
                tier=self._tier_for_task(task), provider='bob-local', success=True,
            )
            return self._get_local_response(messages)

        if max_tokens is None:
            max_tokens = self.task_max_tokens.get(task, self.default_max_tokens)
        tier = self._tier_for_task(task)

        is_premium = bool(user_id) and subscription_model.is_premium(user_id)
        if is_premium:
            max_tokens = int(max_tokens * self.PREMIUM_MAX_TOKENS_MULTIPLIER)

        normalized_messages = self._normalize_messages(messages)
        optimized_messages = self._optimize_messages_for_tokens(
            normalized_messages,
            task=task,
        )

        # Try to use DB-backed cache when user_id provided
        cache_db = None
        try:
            if user_id:
                cache_db = get_user_db_path(user_id)
                # build cache key from task + messages content hash
                h = hashlib.sha256()
                h.update(task.encode('utf-8'))
                joined = '\n'.join([m.get('role','') + ':' + (m.get('content') or '') for m in optimized_messages])
                h.update(joined.encode('utf-8'))
                # workspace_id in the key: the same prompt text asked from
                # Personal vs. a Business workspace must never share a cached
                # answer -- the injected workspace_context differs even when
                # the raw message text happens to match.
                cache_key = f"ai::{user_id}::{workspace_id}::{h.hexdigest()}"
                cached = Cache.get(cache_key, db_path=cache_db)
                if cached:
                    cached_provider = cached.get('provider', self.last_provider_used)
                    self.last_provider_used = cached_provider
                    ai_cost_log.record_call(
                        user_id=user_id, workspace_id=workspace_id, task=task, tier=tier,
                        provider=cached_provider or 'cache', success=True, cache_hit=True,
                    )
                    return cached.get('response')
        except Exception:
            cache_db = None

        if not self.configured_providers:
            self.last_provider_used = 'demo'
            self.provider_usage['demo'] += 1
            ai_cost_log.record_call(
                user_id=user_id, workspace_id=workspace_id, task=task, tier=tier,
                provider='demo', success=True,
            )
            demo = self._get_demo_response(optimized_messages)
            try:
                if cache_db:
                    Cache.set(cache_key, {'response': demo, 'provider': 'demo'}, ttl=3600, db_path=cache_db)
            except Exception:
                pass
            return demo

        providers = self._build_provider_chain(task=task, prefer_quality=is_premium)
        last_error = None
        all_quota_errors = True

        for provider in providers:
            # Skip unhealthy providers
            if not self._is_provider_healthy(provider):
                health = self.provider_health.get(provider, {})
                remaining = health.get('cooldown_minutes', 0)
                print(f"⏭️  Bỏ qua {provider.upper()} (đang cooldown ~{remaining}min)")
                continue
            
            t0 = time.monotonic()
            try:
                response, usage = self._call_provider(provider, optimized_messages, max_tokens, tier=tier)
                if response and response.strip():
                    # Successful - mark as used
                    self.last_provider_used = provider
                    if provider in self.provider_usage:
                        self.provider_usage[provider] += 1
                    print(f"✅ {provider.upper()} responded successfully")
                    model = self._model_for(provider, tier)
                    ai_cost_log.record_call(
                        user_id=user_id, workspace_id=workspace_id, task=task, tier=tier,
                        provider=provider, model=model, success=True,
                        input_tokens=(usage or {}).get('input_tokens'),
                        output_tokens=(usage or {}).get('output_tokens'),
                        estimated_cost_usd=self._estimate_cost_usd(provider, model, usage),
                        latency_ms=int((time.monotonic() - t0) * 1000),
                    )
                    try:
                        if cache_db:
                            Cache.set(cache_key, {'response': response, 'provider': provider}, ttl=3600, db_path=cache_db)
                    except Exception:
                        pass
                    return response
            except Exception as e:
                error_msg = str(e)
                last_error = f"{provider}: {error_msg}"

                # Check if it's a quota/rate limit error
                status_code = getattr(e, 'response', None)
                if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                    status_code = e.response.status_code
                else:
                    status_code = None

                is_quota = self._is_quota_error(error_msg, status_code)

                if is_quota:
                    print(f"🚫 {provider.upper()} HẾT QUOTA - chuyển sang provider khác")
                    self._mark_provider_failed(provider, error_msg, is_quota_error=True)
                else:
                    all_quota_errors = False
                    print(f"⚠️  {provider.upper()} lỗi - thử provider tiếp theo: {error_msg[:100]}")
                    self._mark_provider_failed(provider, error_msg, is_quota_error=False)
                ai_cost_log.record_call(
                    user_id=user_id, workspace_id=workspace_id, task=task, tier=tier,
                    provider=provider, model=self._model_for(provider, tier), success=False,
                    error_type='quota' if is_quota else 'error',
                    latency_ms=int((time.monotonic() - t0) * 1000),
                )

        # All providers failed or in cooldown
        healthy_count = len([p for p in self.configured_providers if self._is_provider_healthy(p)])
        
        if healthy_count == 0:
            print(f"❌ TẤT CẢ AI PROVIDERS KHÔNG KHẢ DỤNG - chuyển Demo Mode")
            print(f"   Last error: {last_error}")
        else:
            print(f"⚠️  Không thể generate response. {healthy_count} providers vẫn healthy nhưng chưa thử")
        
        if Config.BOB_LOCAL_ONLY:
            self.last_provider_used = 'bob-local'
            self.provider_usage['bob-local'] += 1
            ai_cost_log.record_call(
                user_id=user_id, workspace_id=workspace_id, task=task, tier=tier,
                provider='bob-local', success=True,
            )
            return self._get_local_response(optimized_messages)
        self.last_provider_used = 'demo'
        self.provider_usage['demo'] += 1
        ai_cost_log.record_call(
            user_id=user_id, workspace_id=workspace_id, task=task, tier=tier,
            provider='demo', success=True,
        )
        return self._get_demo_response(optimized_messages)

    def generate_with_provider(self, provider, messages, max_tokens=None, task='analyze',
                                user_id=None, workspace_id=None):
        """Generate one response from a specific configured provider.

        Used by background mentor learning so Bob can ask a particular
        "senior" model for process feedback without changing the normal
        round-robin/fallback behavior that serves the user's visible answer.
        """
        provider = (provider or '').strip().lower()
        if not provider:
            raise ValueError("Provider is required")
        if Config.BOB_LOCAL_ONLY and provider != 'ollama':
            raise RuntimeError("External model providers are disabled by BOB_LOCAL_ONLY")
        if provider not in self.configured_providers:
            raise ValueError(f"{provider} chưa được cấu hình")
        if not self._is_provider_healthy(provider):
            raise RuntimeError(f"{provider} đang cooldown")

        if max_tokens is None:
            max_tokens = self.task_max_tokens.get(task, self.default_max_tokens)
        tier = self._tier_for_task(task)

        normalized_messages = self._normalize_messages(messages)
        optimized_messages = self._optimize_messages_for_tokens(
            normalized_messages,
            task=task,
        )

        t0 = time.monotonic()
        try:
            response, usage = self._call_provider(provider, optimized_messages, max_tokens, tier=tier)
            if response and response.strip():
                self.last_provider_used = provider
                if provider in self.provider_usage:
                    self.provider_usage[provider] += 1
                model = self._model_for(provider, tier)
                ai_cost_log.record_call(
                    user_id=user_id, workspace_id=workspace_id, task=task, tier=tier,
                    provider=provider, model=model, success=True,
                    input_tokens=(usage or {}).get('input_tokens'),
                    output_tokens=(usage or {}).get('output_tokens'),
                    estimated_cost_usd=self._estimate_cost_usd(provider, model, usage),
                    latency_ms=int((time.monotonic() - t0) * 1000),
                )
                return response
        except Exception as e:
            status_code = None
            if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                status_code = e.response.status_code
            is_quota = self._is_quota_error(str(e), status_code)
            self._mark_provider_failed(provider, str(e), is_quota_error=is_quota)
            ai_cost_log.record_call(
                user_id=user_id, workspace_id=workspace_id, task=task, tier=tier,
                provider=provider, model=self._model_for(provider, tier), success=False,
                error_type='quota' if is_quota else 'error',
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            raise

        raise RuntimeError(f"{provider} không trả về nội dung")

    def _parse_provider_list(self, value):
        if not value:
            return []
        return [p.strip().lower() for p in value.split(',') if p.strip()]

    @staticmethod
    def _normalize_tier(value, default):
        value = str(value or '').strip().lower()
        return value if value in ('cheap', 'strong') else default

    def _tier_for_task(self, task):
        return self.task_tiers.get(task, 'strong')

    def _model_for(self, provider, tier):
        """Resolve the model name a provider should use for a tier.

        Falls back to that provider's strong model if the requested tier
        isn't configured (e.g. a brand-new provider added to
        provider_models without a 'cheap' entry) -- never returns an empty
        string for a provider that has any model configured at all.
        """
        models = self.provider_models.get(provider) or {}
        return models.get(tier) or models.get('strong') or ''

    # USD per 1,000 tokens, seeded for the models this app configures by
    # default. An operator-configured custom model (e.g. a new
    # *_MODEL_CHEAP override) that isn't in this table simply gets
    # estimated_cost_usd=NULL in the cost log rather than a guessed number
    # -- a documented limitation, not a bug.
    _PRICING_USD_PER_1K = {
        ('openai', 'gpt-4o'): {'input': 0.0025, 'output': 0.01},
        ('mistral', 'mistral-large-latest'): {'input': 0.002, 'output': 0.006},
        ('claude', 'claude-sonnet-5'): {'input': 0.003, 'output': 0.015},
        ('gemini', 'gemini-2.5-pro'): {'input': 0.00125, 'output': 0.005},
    }

    def _estimate_cost_usd(self, provider, model, usage):
        prices = self._PRICING_USD_PER_1K.get((provider, model))
        if not prices or not usage:
            return None
        input_tokens = usage.get('input_tokens')
        output_tokens = usage.get('output_tokens')
        if input_tokens is None and output_tokens is None:
            return None
        cost = (input_tokens or 0) / 1000.0 * prices.get('input', 0.0) \
            + (output_tokens or 0) / 1000.0 * prices.get('output', 0.0)
        return round(cost, 6)

    def _detect_configured_providers(self):
        if Config.BOB_LOCAL_ONLY:
            return ['ollama'] if Config.OLLAMA_ENABLED else []
        configured = []

        # OpenRouter is the primary choice if enabled
        if Config.OPENROUTER_ENABLED and Config.OPENROUTER_API_KEY:
            configured.append('openrouter')
        
        if Config.OPENAI_API_KEY:
            configured.append('openai')
        if Config.MISTRAL_API_KEY:
            configured.append('mistral')
        if Config.CLAUDE_API_KEY:
            configured.append('claude')
        if Config.GEMINI_API_KEY:
            configured.append('gemini')
        if Config.OLLAMA_ENABLED:
            configured.append('ollama')

        return configured

    def _build_provider_chain(self, task='chat', prefer_quality=False):
        """Build provider chain using round-robin + health filtering"""
        # Start with round-robin selection
        ordered = []
        
        # Get healthy providers only
        healthy_providers = [p for p in self.configured_providers if self._is_provider_healthy(p)]
        
        if not healthy_providers:
            # All providers in cooldown - try all configured anyway
            print("⚠️  Tất cả providers trong cooldown - thử lại toàn bộ")
            return self.configured_providers.copy()
        
        # Use round-robin to select starting provider
        next_provider = self._get_next_round_robin_provider()
        if next_provider and next_provider in healthy_providers:
            ordered.append(next_provider)
            print(f"🔄 Round-robin selected: {next_provider.upper()}")
        
        # Add remaining healthy providers
        for provider in healthy_providers:
            if provider not in ordered:
                ordered.append(provider)
        
        # Task-specific overrides (if configured)
        task_overrides = self.task_provider_overrides.get(task, [])
        for provider in task_overrides:
            if provider in healthy_providers and provider not in ordered:
                ordered.insert(0, provider)  # Prioritize task-specific providers

        # Premium quality preference: bubble the stronger providers to the
        # front without dropping anything from the fallback chain.
        if prefer_quality:
            for provider in reversed(self.PREMIUM_PREFERRED_PROVIDERS):
                if provider in ordered:
                    ordered.remove(provider)
                    ordered.insert(0, provider)

        return ordered

    def _normalize_messages(self, messages):
        normalized = []
        for msg in messages or []:
            role = msg.get('role', 'user')
            if role not in ['system', 'user', 'assistant']:
                role = 'user'

            content = msg.get('content', '')
            if content is None:
                content = ''

            normalized.append({
                'role': role,
                'content': str(content),
                'preserve_context': bool(msg.get('preserve_context'))
            })

        return normalized

    def _truncate_text(self, text, max_chars):
        if not text:
            return ''
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n...[truncated]"

    def _truncate_text_ends(self, text, max_chars):
        """Truncate while retaining both instructions and trailing constraints.

        User corrections and language requirements commonly appear at the end
        of a long prompt.  Head-only truncation silently changed their intent.
        """
        text = str(text or '')
        if not text or len(text) <= max_chars:
            return text
        marker = "\n...[middle truncated]...\n"
        if max_chars <= len(marker) + 40:
            return self._truncate_text(text, max_chars)
        available = max_chars - len(marker)
        head_chars = int(available * 0.62)
        tail_chars = available - head_chars
        return text[:head_chars] + marker + text[-tail_chars:]

    def _parse_report_date(self, report_date):
        if not report_date:
            return None

        value = str(report_date).strip()
        for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%Y/%m/%d'):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None

    def _infer_meeting_signals(self, email, report_date=None):
        text = ' '.join([
            str(email.get('subject', '') or ''),
            str(email.get('snippet', '') or ''),
            str(email.get('body', '') or '')
        ]).lower()

        meeting_keywords = [
            'meeting', 'họp', 'lịch hẹn', 'cuộc họp', 'appointment', 'schedule',
            'call', 'zoom', 'teams', 'google meet', 'gặp', 'thảo luận'
        ]
        is_meeting = any(keyword in text for keyword in meeting_keywords)

        report_day = self._parse_report_date(report_date)
        time_match = re.search(r'(?<!\d)(\d{1,2})[:h](\d{2})(?!\d)', text)
        hour_only_match = re.search(r'(?<!\d)(\d{1,2})\s*(giờ|h)(?!\d)', text)

        suggested_start_time = None
        if report_day:
            hour = 9
            minute = 0
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
            elif hour_only_match:
                hour = int(hour_only_match.group(1))

            if 0 <= hour <= 23 and 0 <= minute <= 59:
                suggested_start_time = datetime.combine(
                    report_day,
                    datetime.strptime(f'{hour:02d}:{minute:02d}', '%H:%M').time()
                ).isoformat()

        schedule_title = str(email.get('subject', '') or '').strip() or 'Lịch hẹn từ email'

        return {
            'is_meeting': is_meeting,
            'meeting_note': 'Email này có nội dung liên quan đến cuộc họp/lịch hẹn.' if is_meeting else '',
            'schedule_title': schedule_title[:120],
            'suggested_start_time': suggested_start_time,
            'suggested_end_time': None,
            'suggested_description': self._truncate_text(
                f"Nguồn email: {email.get('sender', 'Unknown')}\nSubject: {email.get('subject', '')}\nSnippet: {email.get('snippet', '')}",
                500
            )
        }

    def _optimize_messages_for_tokens(self, messages, task='chat'):
        if not messages:
            return []

        system_messages = [m for m in messages if m.get('role') == 'system']
        non_system = [m for m in messages if m.get('role') != 'system']

        optimized = []

        if system_messages:
            system_content = "\n".join([m.get('content', '') for m in system_messages])
            # The core system contract is a correctness and safety boundary,
            # not disposable conversation context.  Keep a floor large enough
            # for Bob's grounding, confirmation, language, and memory rules
            # even if an old deployment still carries the former 450-char env
            # value.
            system_budget = max(12000, int(self.max_system_prompt_chars or 0))
            optimized.append({
                'role': 'system',
                'content': self._truncate_text_ends(system_content, system_budget)
            })

        # Keep the newest bounded window.  The latest user turn is always in
        # this slice and is never subjected to the old blanket 400-char cap.
        context_limit = max(1, int(self.max_context_messages or 1))
        recent_non_system = non_system[-context_limit:]
        input_budget = max(4000, int(self.max_input_chars or 0))
        if task == 'intent_classification':
            # The classifier carries its JSON schema and a bounded history in
            # one structured message.  It must see that entire contract.
            input_budget = max(input_budget, 16000)

        contents = []
        for msg in recent_non_system:
            content = str(msg.get('content', '') or '')
            if msg.get('role') == 'assistant' and not msg.get('preserve_context'):
                content = self._truncate_text_ends(content, 1600)
            contents.append(content)

        overflow = max(0, sum(len(content) for content in contents) - input_budget)
        if overflow:
            latest_user_index = next(
                (
                    index
                    for index in range(len(recent_non_system) - 1, -1, -1)
                    if recent_non_system[index].get('role') == 'user'
                ),
                len(recent_non_system) - 1,
            )
            # Reduce oldest context first.  Preserve a useful excerpt of each
            # turn and leave the newest user prompt untouched for as long as
            # possible.
            for index, msg in enumerate(recent_non_system):
                if overflow <= 0 or index == latest_user_index:
                    continue
                floor = 800 if msg.get('preserve_context') else (
                    180 if msg.get('role') == 'assistant' else 320
                )
                reducible = max(0, len(contents[index]) - floor)
                reduction = min(overflow, reducible)
                if reduction:
                    contents[index] = self._truncate_text_ends(
                        contents[index],
                        len(contents[index]) - reduction,
                    )
                    overflow -= reduction

            if overflow > 0 and recent_non_system:
                current = contents[latest_user_index]
                target = max(800, len(current) - overflow)
                contents[latest_user_index] = self._truncate_text_ends(
                    current,
                    target,
                )

        for msg, content in zip(recent_non_system, contents):
            optimized.append({
                'role': msg.get('role', 'user'),
                'content': content,
            })

        return optimized

    def _call_provider(self, provider, messages, max_tokens, tier='strong'):
        if Config.BOB_LOCAL_ONLY and provider != 'ollama':
            raise RuntimeError("External model providers are disabled by BOB_LOCAL_ONLY")
        model = self._model_for(provider, tier)
        if provider == 'openrouter':
            return self._call_openrouter(messages, max_tokens, model=model)
        if provider == 'openai':
            return self._call_openai(messages, max_tokens, model=model)
        if provider == 'mistral':
            return self._call_mistral(messages, max_tokens, model=model)
        if provider == 'claude':
            return self._call_claude(messages, max_tokens, model=model)
        if provider == 'gemini':
            return self._call_gemini(messages, max_tokens, model=model)
        if provider == 'ollama':
            return self._call_ollama(messages, max_tokens, model=model)

        raise ValueError(f"Unsupported provider: {provider}")

    def _call_openrouter(self, messages, max_tokens, model=None):
        """Delegate to OpenRouterService adapter if available."""
        if self.openrouter_service:
            return self.openrouter_service.generate_chat(
                messages, max_tokens=max_tokens, temperature=0.5, model_override=model,
            )

        # Fallback to previous inline implementation if adapter isn't available
        if not Config.OPENROUTER_API_KEY:
            raise ValueError("OpenRouter chưa được cấu hình")
        raise RuntimeError("OpenRouterService not initialized")

    def _call_openai(self, messages, max_tokens, model=None):
        if not Config.OPENAI_API_KEY:
            raise ValueError("OpenAI chưa được cấu hình")

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model or Config.OPENAI_MODEL,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.5
                },
                timeout=self.timeout
            )
            
            # Check for quota/rate limit errors
            if response.status_code in [429, 401, 403, 402]:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get('error', {}).get('message', f"HTTP {response.status_code}")
                raise requests.exceptions.HTTPError(f"OpenAI quota/rate error: {error_msg}", response=response)
            
            response.raise_for_status()
            data = response.json()
            usage = data.get('usage') or {}
            return data['choices'][0]['message']['content'], {
                'input_tokens': usage.get('prompt_tokens'),
                'output_tokens': usage.get('completion_tokens'),
            }

        except requests.exceptions.RequestException as e:
            # Attach response for status code checking
            raise e

    def _call_mistral(self, messages, max_tokens, model=None):
        if not Config.MISTRAL_API_KEY:
            raise ValueError("Mistral chưa được cấu hình")

        try:
            response = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {Config.MISTRAL_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model or Config.MISTRAL_MODEL,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.4
                },
                timeout=self.timeout
            )
            
            # Check for quota/rate limit errors
            if response.status_code in [429, 401, 403, 402]:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get('message', f"HTTP {response.status_code}")
                raise requests.exceptions.HTTPError(f"Mistral quota/rate error: {error_msg}", response=response)
            
            response.raise_for_status()
            data = response.json()
            usage = data.get('usage') or {}
            return data['choices'][0]['message']['content'], {
                'input_tokens': usage.get('prompt_tokens'),
                'output_tokens': usage.get('completion_tokens'),
            }

        except requests.exceptions.RequestException as e:
            raise e

    def _call_claude(self, messages, max_tokens, model=None):
        if not Config.CLAUDE_API_KEY:
            raise ValueError("Claude chưa được cấu hình")

        system_prompt, provider_messages = self._split_system_message(messages)

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": Config.CLAUDE_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": model or Config.CLAUDE_MODEL,
                    "system": system_prompt,
                    "messages": provider_messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.5
                },
                timeout=self.timeout
            )
            
            # Check for quota/rate limit errors
            if response.status_code in [429, 401, 403, 402]:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get('error', {}).get('message', f"HTTP {response.status_code}")
                raise requests.exceptions.HTTPError(f"Claude quota/rate error: {error_msg}", response=response)
            
            response.raise_for_status()
            data = response.json()
            content_parts = data.get('content', [])
            texts = [part.get('text', '') for part in content_parts if part.get('type') == 'text']
            usage = data.get('usage') or {}
            return "\n".join([t for t in texts if t]), {
                'input_tokens': usage.get('input_tokens'),
                'output_tokens': usage.get('output_tokens'),
            }

        except requests.exceptions.RequestException as e:
            raise e

    def _call_gemini(self, messages, max_tokens, model=None):
        if not Config.GEMINI_API_KEY:
            raise ValueError("Gemini chưa được cấu hình")

        system_prompt, provider_messages = self._split_system_message(messages)

        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model or Config.GEMINI_MODEL}:generateContent?key={Config.GEMINI_API_KEY}"
        )

        payload = {
            "contents": self._convert_to_gemini_messages(provider_messages),
            "generationConfig": {
                "temperature": 0.5,
                "maxOutputTokens": max_tokens
            }
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        try:
            response = requests.post(
                endpoint,
                headers={"content-type": "application/json"},
                json=payload,
                timeout=self.timeout
            )
            
            # Check for quota/rate limit errors
            if response.status_code in [429, 401, 403, 402]:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get('error', {}).get('message', f"HTTP {response.status_code}")
                raise requests.exceptions.HTTPError(f"Gemini quota/rate error: {error_msg}", response=response)
            
            response.raise_for_status()
            data = response.json()
            candidates = data.get('candidates', [])
            
            if not candidates:
                raise ValueError("Gemini không trả về candidates")

            parts = candidates[0].get('content', {}).get('parts', [])
            texts = [part.get('text', '') for part in parts if part.get('text')]
            meta = data.get('usageMetadata') or {}
            return "\n".join(texts), {
                'input_tokens': meta.get('promptTokenCount'),
                'output_tokens': meta.get('candidatesTokenCount'),
            }

        except requests.exceptions.RequestException as e:
            raise e

    def _call_ollama(self, messages, max_tokens, model=None):
        if not Config.OLLAMA_ENABLED:
            raise ValueError("Ollama chưa được cấu hình")

        base_url = str(Config.OLLAMA_BASE_URL or '').strip().rstrip('/')
        hostname = (urlparse(base_url).hostname or '').lower()
        if Config.BOB_LOCAL_ONLY and hostname not in {'localhost', '127.0.0.1', '::1'}:
            raise RuntimeError("BOB_LOCAL_ONLY chỉ cho phép Ollama chạy trên máy cục bộ")

        try:
            response = requests.post(
                f"{base_url}/api/chat",
                headers={"Content-Type": "application/json"},
                json={
                    "model": model or Config.OLLAMA_MODEL,
                    "messages": messages,
                    "stream": False,
                    # Qwen3 and other reasoning models otherwise spend the
                    # response budget on hidden thinking and may return a
                    # truncated user-visible answer. Bob plans internally but
                    # only returns the final response.
                    "think": False,
                    "options": {
                        "temperature": 0.5,
                        "num_predict": max_tokens
                    }
                },
                timeout=self.timeout,
                allow_redirects=False,
            )

            if response.status_code in [429, 401, 403, 402]:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get('error', f"HTTP {response.status_code}")
                raise requests.exceptions.HTTPError(f"Ollama quota/rate error: {error_msg}", response=response)

            response.raise_for_status()
            data = response.json()
            return data['message']['content'], {
                'input_tokens': data.get('prompt_eval_count'),
                'output_tokens': data.get('eval_count'),
            }

        except requests.exceptions.RequestException as e:
            raise e

    def _split_system_message(self, messages):
        system_parts = []
        converted = []

        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if role == 'system':
                system_parts.append(content)
            elif role in ['user', 'assistant']:
                # Context-window slicing can orphan an old assistant turn.
                # Claude/Gemini expect a user-first, alternating dialogue, so
                # discard only that unusable prefix and merge adjacent roles
                # (workspace context + memory + current turn are often three
                # consecutive user messages).
                if role == 'assistant' and not converted:
                    continue
                if converted and converted[-1]['role'] == role:
                    converted[-1]['content'] += "\n\n" + content
                else:
                    converted.append({
                        "role": role,
                        "content": content
                    })

        return "\n\n".join(system_parts), converted

    def _convert_to_gemini_messages(self, messages):
        converted = []
        for msg in messages:
            role = 'model' if msg.get('role') == 'assistant' else 'user'
            converted.append({
                "role": role,
                "parts": [{"text": msg.get('content', '')}]
            })
        return converted

    def get_provider_status(self):
        """Return provider configuration for UI/debug"""
        if Config.BOB_LOCAL_ONLY:
            local_chain = self.configured_providers or ["bob-local"]
            health = {
                provider: {
                    "healthy": self._is_provider_healthy(provider),
                    "usage_count": self.provider_usage.get(provider, 0),
                }
                for provider in local_chain
            }
            return {
                "engine": "ollama-local" if 'ollama' in local_chain else "bob-local",
                "local_only": True,
                "primary_provider": local_chain[0],
                "provider_order": local_chain,
                "configured_providers": self.configured_providers,
                "missing_providers": [],
                "active_chain": local_chain,
                "task_provider_overrides": {},
                "task_chains": {
                    task: local_chain
                    for task in ("chat", "summary", "reply", "analyze")
                },
                "provider_health": health,
                "provider_usage": self.provider_usage,
                "last_provider_used": self.last_provider_used,
                "rotation_index": 0,
                "demo_mode": False,
                "task_tiers": self.task_tiers,
                "provider_models": self.provider_models,
            }
        chain = self._build_provider_chain() if self.configured_providers else []
        missing_providers = [
            provider for provider in ['openai', 'mistral', 'claude', 'gemini', 'ollama']
            if provider not in self.configured_providers
        ]
        
        # Get health status for all providers
        health_status = {}
        for provider in self.configured_providers:
            is_healthy = self._is_provider_healthy(provider)
            health_info = {
                'healthy': is_healthy,
                'usage_count': self.provider_usage.get(provider, 0)
            }
            
            if not is_healthy and provider in self.provider_health:
                failed_info = self.provider_health[provider]
                failed_at = failed_info.get('failed_at')
                cooldown = failed_info.get('cooldown_minutes', 5)
                
                if failed_at:
                    time_passed = datetime.now() - failed_at
                    remaining = cooldown - (time_passed.total_seconds() / 60)
                    health_info['cooldown_remaining_minutes'] = max(0, remaining)
                    health_info['error'] = failed_info.get('error', 'Unknown error')
                    health_info['is_quota_error'] = failed_info.get('is_quota_error', False)
            
            health_status[provider] = health_info
        
        return {
            "primary_provider": self.primary_provider,
            "provider_order": self.provider_order,
            "configured_providers": self.configured_providers,
            "missing_providers": missing_providers,
            "active_chain": chain,
            "task_provider_overrides": self.task_provider_overrides,
            "task_chains": {
                "chat": self._build_provider_chain('chat') if self.configured_providers else [],
                "summary": self._build_provider_chain('summary') if self.configured_providers else [],
                "reply": self._build_provider_chain('reply') if self.configured_providers else [],
                "analyze": self._build_provider_chain('analyze') if self.configured_providers else []
            },
            "provider_health": health_status,
            "provider_usage": self.provider_usage,
            "last_provider_used": self.last_provider_used,
            "rotation_index": self.provider_rotation_index,
            "demo_mode": len(self.configured_providers) == 0 or all(not self._is_provider_healthy(p) for p in self.configured_providers),
            "task_tiers": self.task_tiers,
            "provider_models": self.provider_models,
        }
    
    def _get_demo_response(self, messages):
        """Trả về demo response"""
        user_msg = messages[-1]["content"].lower() if messages else ""
        
        if "tóm tắt" in user_msg or "summary" in user_msg:
            return DEMO_RESPONSES["tóm tắt"]
        elif "lịch" in user_msg or "schedule" in user_msg:
            return DEMO_RESPONSES["lịch"]
        else:
            return DEMO_RESPONSES["default"]

    def _get_local_response(self, messages):
        """Safe last-resort response for legacy call sites in local-only mode."""
        user_message = ''
        for message in reversed(messages or []):
            if message.get('role') == 'user':
                user_message = str(message.get('content') or '').strip()
                break
        normalized = user_message.casefold()
        if any(term in normalized for term in ('xin chào', 'chào bob', 'hello', 'hi bob')):
            return (
                "Chào bạn, mình là Bob. Mình có thể xử lý email, lịch, checklist, "
                "kiến thức đã học và tìm thông tin công khai trên Internet."
            )
        return (
            "Mình chưa có đủ dữ liệu hoặc quy tắc cục bộ để trả lời chắc chắn. "
            "Bạn hãy nói rõ tác vụ cần làm, yêu cầu tìm Internet, hoặc dạy Bob "
            "một quy tắc cụ thể để mình ghi nhớ."
        )
    
    def summarize_email(self, email_content, user_id=None):
        """Summarize email content with focus on key points and action items.

        Local extractive summarization (services/extractive_summary.py) --
        no LLM/API call, no token cost. See summarize_email_polished for why.
        """
        return extractive_summary.summarize_short('', email_content)

    def summarize_email_polished(self, email_data, user_id=None):
        """Create a structured, accurate and action-oriented email summary.

        Local extractive summarization (services/extractive_summary.py):
        ranks sentences already in the email by word-frequency importance
        and reassembles the same 4-section report from verbatim source
        text -- no LLM/API call, no token cost. Because nothing is
        generated, only selected, it can never state a fact that isn't
        literally in the source (the trade-off: it can't paraphrase/
        synthesize a new sentence the way an LLM summary could).
        """
        email_data = email_data or {}
        subject = str(email_data.get('subject', '') or '').strip()
        sender = str(email_data.get('sender', '') or '').strip()
        cc = str(email_data.get('cc', '') or '').strip()
        to = str(email_data.get('to', '') or '').strip()
        body = str(email_data.get('body', '') or email_data.get('snippet', '') or '').strip()
        attachments = email_data.get('attachments') or []
        return extractive_summary.summarize_structured(
            subject,
            body,
            sender=sender,
            to=to,
            cc=cc,
            attachments=attachments,
        )

    def generate_reply(self, context, user_choice, user_id=None):
        """Create a bounded, deterministic email reply without a model."""
        choice = re.sub(r'\s+', ' ', str(user_choice or '')).strip()
        if not choice:
            choice = "Tôi đã nhận được thông tin và sẽ phản hồi sớm."
        if re.search(r'\b(thanks?|cảm ơn|cam on)\b', choice, re.IGNORECASE):
            body = choice
        else:
            body = f"Cảm ơn bạn đã liên hệ.\n\n{choice}"
        return strip_markup(f"Xin chào,\n\n{body}\n\nTrân trọng.")
    
    def analyze_text(self, text):
        """Analyze text with transparent keyword rules."""
        value = str(text or '')
        lowered = value.casefold()
        negative = ('khẩn', 'gấp', 'lỗi', 'không hài lòng', 'urgent', 'error', 'failed')
        positive = ('cảm ơn', 'tốt', 'tuyệt', 'thanks', 'great', 'excellent')
        sentiment = 'tiêu cực/khẩn cấp' if any(x in lowered for x in negative) else (
            'tích cực' if any(x in lowered for x in positive) else 'trung tính'
        )
        actions = []
        if re.search(r'\b(phản hồi|trả lời|reply|respond)\b', lowered):
            actions.append('phản hồi')
        if re.search(r'\b(họp|lịch|meeting|schedule|deadline)\b', lowered):
            actions.append('kiểm tra lịch/deadline')
        return (
            f"Cảm xúc: {sentiment}.\n"
            f"Hành động gợi ý: {', '.join(actions) if actions else 'chưa phát hiện hành động rõ ràng'}."
        )
    
    def classify_email(self, email_data, user_id=None):
        """Classify email into categories: education, business, ads, notification, personal, etc.
        
        Args:
            email_data: dict with keys 'subject', 'sender', 'body', 'snippet'
            
        Returns:
            dict with 'tag' (str), 'confidence' (float 0-1), 'reason' (str)
        """
        subject = email_data.get('subject', '')
        sender = email_data.get('sender', '')
        body = email_data.get('body', '') or email_data.get('snippet', '')
        
        email_text = f"{subject} {sender} {body}".casefold()
        rules = (
            ('ads', ('sale', 'discount', 'promotion', 'ưu đãi', 'khuyến mãi', 'unsubscribe')),
            ('notification', ('otp', 'verification', 'xác nhận', 'alert', 'notification')),
            ('education', ('course', 'lesson', 'university', 'school', 'khóa học', 'bài học')),
            ('business', ('invoice', 'meeting', 'project', 'hợp đồng', 'hóa đơn', 'công việc')),
            ('social', ('facebook', 'linkedin', 'instagram', 'community', 'group')),
            ('personal', ('family', 'friend', 'gia đình', 'bạn bè')),
        )
        for tag, keywords in rules:
            matches = [word for word in keywords if word in email_text]
            if matches:
                return {
                    'tag': tag,
                    'confidence': min(0.95, 0.65 + 0.1 * len(matches)),
                    'reason': f"Matched local rules: {', '.join(matches[:3])}",
                }
        return {'tag': 'other', 'confidence': 0.4, 'reason': 'No local category rule matched'}
    
    def summarize_email_short(self, email_data, user_id=None):
        """Create a short summary (1-2 sentences) of email content
        
        Args:
            email_data: dict with keys 'subject', 'sender', 'body', 'snippet'
            
        Returns:
            str: Brief summary
        """
        subject = email_data.get('subject', '')
        body = email_data.get('body', '') or email_data.get('snippet', '')
        
        return extractive_summary.summarize_short(subject, body)

    def summarize_email_report(self, emails, report_date=None, user_id=None):
        """Summarize multiple emails with intelligent filtering.

        Local extractive summarization (services/extractive_summary.py) for
        the per-email one-line summary -- no LLM/API call, no token cost,
        deterministic. Meeting detection stays rule-based via
        _infer_meeting_signals, unchanged.
        """
        if not emails:
            return []

        # Filter out purely promotional/redundant emails before processing
        filtered_emails = []
        for email in emails:
            subject = (email.get('subject', '') or '').lower()
            body = (email.get('body', '') or '').lower()

            # Skip obvious promotions, newsletters, automated notifications
            skip_keywords = [
                'unsubscribe', 'promotional', 'khuyến mãi', 'đơn hàng', 'shipping',
                'marketing', 'newsletter', 'subscription', 'confirm your', 'verify your'
            ]

            if any(kw in subject or kw in body[:200] for kw in skip_keywords):
                # Check if it's important despite being promotional
                important_keywords = ['urgent', 'cần sự chú ý', 'gấp', 'important', 'action required']
                if not any(kw in subject for kw in important_keywords):
                    continue

            filtered_emails.append(email)

        # Use original list if all filtered, prevent empty result
        if not filtered_emails:
            filtered_emails = emails[:15]  # Process top 15 if all filtered

        rows = []
        for email in filtered_emails:
            inferred = self._infer_meeting_signals(email, report_date=report_date)
            summary = extractive_summary.summarize_one_line(
                email.get('subject', ''),
                email.get('snippet', ''),
                email.get('body', ''),
            )
            rows.append({
                'id': email.get('id', ''),
                'sender': email.get('sender', 'Unknown'),
                'summary': summary,
                'subject': email.get('subject', ''),
                'date': email.get('date', ''),
                'is_unread': bool(email.get('is_unread', False)),
                'is_meeting': bool(inferred.get('is_meeting', False)),
                'meeting_note': inferred.get('meeting_note', ''),
                'schedule_title': inferred.get('schedule_title', ''),
                'suggested_start_time': inferred.get('suggested_start_time'),
                'suggested_end_time': inferred.get('suggested_end_time'),
                'suggested_description': inferred.get('suggested_description', '')
            })

        # Cache the rows for user for faster re-use
        try:
            if user_id:
                db_path = get_user_db_path(user_id)
                Cache.set(f"email_report:v2:{user_id}::{report_date}", rows, db_path=db_path, ttl=600)
        except Exception:
            pass
        return rows

    def _build_overview_brief_context(self, schedules, email_rows, report_date):
        lines = [f"Ngay: {report_date}"] if report_date else []
        for item in (schedules or [])[:10]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- Lich: {item.get('title','')} luc {item.get('start_time','')} "
                f"({item.get('status','')})"
            )
        for row in (email_rows or [])[:10]:
            if not isinstance(row, dict):
                continue
            tag = " [co the la cuoc hop]" if row.get('is_meeting') else ""
            lines.append(f"- Email tu {row.get('sender','')}: {row.get('summary','')}{tag}")
        return "\n".join(lines)

    def generate_daily_overview_brief(self, schedules, email_rows, report_date=None, user_id=None):
        """Synthesize a short written brief from already-compact structured
        data (live schedules + the extractive per-email one-liners
        summarize_email_report already produces) -- never raw emails.

        Returns None (never raises) when disabled, unconfigured, there's no
        input data, or the result looks unusable -- callers must keep
        rendering their existing bullet-list rendering in that case, never
        regress or crash.
        """
        if not Config.AI_OVERVIEW_BRIEF_ENABLED:
            return None
        if Config.BOB_LOCAL_ONLY or not self.configured_providers:
            return None
        if not schedules and not email_rows:
            return None

        context = self._build_overview_brief_context(schedules, email_rows, report_date)
        messages = [
            {"role": "system", "content": (
                "Ban la Bob, viet MOT doan brief ngan (3-5 cau, van xuoi, khong "
                "markdown, khong gach dau dong) tong hop ngay lam viec cua nguoi "
                "dung dua TREN DUNG du kien duoc cung cap. KHONG bia them ten, "
                "gio, hay su kien khong co trong du lieu. Neu du lieu rong, noi "
                "ngan gon ngay nay chua co gi noi bat."
            )},
            {"role": "user", "content": context},
        ]
        try:
            raw = self.generate_response(
                messages,
                max_tokens=self.task_max_tokens.get('overview_brief', 260),
                task='overview_brief',
                user_id=user_id,
            )
        except Exception:
            logger.warning("Overview brief synthesis failed", exc_info=True)
            return None
        # generate_response never raises for provider exhaustion -- it
        # silently degrades to the demo/bob-local sentinel instead. Reject
        # that case explicitly so callers never mistake a canned non-answer
        # for a real synthesized brief.
        if self.last_provider_used not in self.configured_providers:
            return None
        text = strip_markup(str(raw or '').strip())
        return text if len(text) >= 20 else None

    @staticmethod
    def _coerce_iso_datetime(value):
        text = str(value or '').strip()
        if not text or text.lower() == 'null':
            return None
        try:
            datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            return None
        return text

    def confirm_meeting_extraction(self, email, regex_candidate, user_id=None):
        """Cheap-tier confirm+improve a borderline regex meeting candidate.

        "Borderline" means the regex pass flagged the email as a likely
        meeting but couldn't resolve a concrete start_time. Never
        auto-creates anything -- returns improved fields for the SAME
        pending suggestion row, or None to leave regex_candidate as-is.
        Disabled, unconfigured, or any invalid/unparseable AI response all
        fall back to None (keep the regex-only result), same philosophy as
        generate_daily_overview_brief.
        """
        if not Config.AI_MEETING_CONFIRM_ENABLED:
            return None
        if Config.BOB_LOCAL_ONLY or not self.configured_providers:
            return None

        subject = str(email.get('subject') or '')[:200]
        sender = str(email.get('sender') or '')[:200]
        body_excerpt = str(email.get('body') or email.get('snippet') or '')[:1500]
        messages = [
            {"role": "system", "content": (
                "Ban la bo xac nhan trich xuat lich hop tu email. Doc email va "
                "ket qua regex so bo, TRA VE DUY NHAT JSON dang: "
                '{"is_meeting": bool, "title": "", '
                '"start_time": "YYYY-MM-DDTHH:MM:SS hoac null", '
                '"end_time": "... hoac null", "location": "", "attendees": "", '
                '"confidence": 0.0-1.0}. Neu khong chac ve mot thoi gian cu the, '
                "dat start_time=null va is_meeting=false. KHONG bia dat thong tin "
                "khong co trong email. Khong giai thich, khong dung markdown."
            )},
            {"role": "user", "content": (
                f"EMAIL:\nTu: {sender}\nChu de: {subject}\nNoi dung: {body_excerpt}\n\n"
                f"KET QUA REGEX SO BO: {json.dumps(regex_candidate or {}, ensure_ascii=False)}"
            )},
        ]
        try:
            raw = self.generate_response(
                messages,
                max_tokens=self.task_max_tokens.get('meeting_confirm', 220),
                task='meeting_confirm',
                user_id=user_id,
            )
        except Exception:
            logger.warning("Meeting AI confirmation failed", exc_info=True)
            return None
        if self.last_provider_used not in self.configured_providers:
            return None

        data = parse_json_object(raw)
        if not isinstance(data, dict) or not data.get('is_meeting'):
            return None
        start_time = self._coerce_iso_datetime(data.get('start_time'))
        if not start_time:
            # Mirrors intent_orchestrator.py's rule for schedule.create:
            # reject the whole AI result if it can't name a concrete time.
            return None
        try:
            confidence = max(0.5, min(0.97, float(data.get('confidence') or 0.6)))
        except (TypeError, ValueError):
            confidence = 0.6

        regex_candidate = regex_candidate or {}
        return {
            'title': str(data.get('title') or regex_candidate.get('title') or '')[:200],
            'start_time': start_time,
            'end_time': self._coerce_iso_datetime(data.get('end_time')) or regex_candidate.get('end_time'),
            'location': (str(data.get('location') or '')[:120]) or regex_candidate.get('location', ''),
            'attendees': (str(data.get('attendees') or '')[:300]) or regex_candidate.get('attendees', ''),
            'confidence': confidence,
        }
