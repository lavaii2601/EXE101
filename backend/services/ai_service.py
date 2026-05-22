import os
import sys
import logging
import json
import re
import requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from services.openrouter_service import OpenRouterService
from models.cache import Cache
from utils.user_context import get_user_db_path, get_current_user_id
import hashlib

# Configure module logger
logger = logging.getLogger(__name__)

# Demo responses khi hết quota
DEMO_RESPONSES = {
    "tóm tắt": "Đây là tóm tắt email:\n- Điểm chính 1: Nội dung quan trọng\n- Điểm chính 2: Thông tin cần chú ý\n- Hành động: Cần phản hồi trong 24h",
    "lịch": "Tôi đề xuất lên lịch hẹn vào ngày mai lúc 14:00 để thảo luận chi tiết.",
    "default": "Xin chào! Tôi là TeacherBot - trợ lý AI cho giáo viên. Tôi có thể giúp bạn với:\n- Soạn tài liệu giáo dục\n- Phân tích email\n- Lên lịch hẹn\n- Và nhiều hơn nữa!\n\n(Hiện đang ở mode Demo - hết quota OpenAI)"
}

# Quota/rate limit error keywords
QUOTA_ERROR_KEYWORDS = [
    'quota', 'rate_limit', 'insufficient_quota', 'quota_exceeded',
    'rate limit', 'too many requests', 'billing', 'overloaded',
    'capacity', 'throttled', 'exceeded your current quota'
]

class AIService:
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
            'analyze': Config.AI_ANALYZE_MAX_TOKENS
        }
        self.provider_order = [
            p.strip().lower() for p in Config.AI_PROVIDER_ORDER.split(',') if p.strip()
        ]
        self.primary_provider = Config.AI_PRIMARY_PROVIDER
        self.task_provider_overrides = {
            'chat': self._parse_provider_list(Config.AI_TASK_PROVIDERS_CHAT),
            'summary': self._parse_provider_list(Config.AI_TASK_PROVIDERS_SUMMARY),
            'reply': self._parse_provider_list(Config.AI_TASK_PROVIDERS_REPLY),
            'analyze': self._parse_provider_list(Config.AI_TASK_PROVIDERS_ANALYZE)
        }
        self.last_provider_used = None
        self.provider_usage = {
            'openrouter': 0,
            'openai': 0,
            'mistral': 0,
            'claude': 0,
            'gemini': 0,
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

        if not self.configured_providers:
            logger.warning("⚠️  Không có AI provider khả dụng - sử dụng Demo Mode")
            print("⚠️  Không có AI provider khả dụng - sử dụng Demo Mode")
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
    
    def generate_response(self, messages, max_tokens=None, task='chat', user_id=None):
        """Generate AI response using round-robin rotation with intelligent fallback"""
        if max_tokens is None:
            max_tokens = self.task_max_tokens.get(task, self.default_max_tokens)

        normalized_messages = self._normalize_messages(messages)
        optimized_messages = self._optimize_messages_for_tokens(normalized_messages)

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
                cache_key = f"ai::{user_id}::{h.hexdigest()}"
                cached = Cache.get(cache_key, db_path=cache_db)
                if cached:
                    self.last_provider_used = cached.get('provider', self.last_provider_used)
                    return cached.get('response')
        except Exception:
            cache_db = None

        if not self.configured_providers:
            self.last_provider_used = 'demo'
            self.provider_usage['demo'] += 1
            demo = self._get_demo_response(optimized_messages)
            try:
                if cache_db:
                    Cache.set(cache_key, {'response': demo, 'provider': 'demo'}, db_path=cache_db)
            except Exception:
                pass
            return demo

        providers = self._build_provider_chain(task=task)
        last_error = None
        all_quota_errors = True

        for provider in providers:
            # Skip unhealthy providers
            if not self._is_provider_healthy(provider):
                health = self.provider_health.get(provider, {})
                remaining = health.get('cooldown_minutes', 0)
                print(f"⏭️  Bỏ qua {provider.upper()} (đang cooldown ~{remaining}min)")
                continue
            
            try:
                response = self._call_provider(provider, optimized_messages, max_tokens)
                if response and response.strip():
                    # Successful - mark as used
                    self.last_provider_used = provider
                    if provider in self.provider_usage:
                        self.provider_usage[provider] += 1
                    print(f"✅ {provider.upper()} responded successfully")
                    try:
                        if cache_db:
                            Cache.set(cache_key, {'response': response, 'provider': provider}, db_path=cache_db)
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

        # All providers failed or in cooldown
        healthy_count = len([p for p in self.configured_providers if self._is_provider_healthy(p)])
        
        if healthy_count == 0:
            print(f"❌ TẤT CẢ AI PROVIDERS KHÔNG KHẢ DỤNG - chuyển Demo Mode")
            print(f"   Last error: {last_error}")
        else:
            print(f"⚠️  Không thể generate response. {healthy_count} providers vẫn healthy nhưng chưa thử")
        
        self.last_provider_used = 'demo'
        self.provider_usage['demo'] += 1
        return self._get_demo_response(optimized_messages)

    def _parse_provider_list(self, value):
        if not value:
            return []
        return [p.strip().lower() for p in value.split(',') if p.strip()]

    def _detect_configured_providers(self):
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

        return configured

    def _build_provider_chain(self, task='chat'):
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
                'content': str(content)
            })

        return normalized

    def _truncate_text(self, text, max_chars):
        if not text:
            return ''
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n...[truncated]"

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

    def _optimize_messages_for_tokens(self, messages):
        if not messages:
            return []

        system_messages = [m for m in messages if m.get('role') == 'system']
        non_system = [m for m in messages if m.get('role') != 'system']

        optimized = []

        if system_messages:
            system_content = "\n".join([m.get('content', '') for m in system_messages])
            optimized.append({
                'role': 'system',
                'content': self._truncate_text(system_content, self.max_system_prompt_chars)
            })

        # If there are too many recent messages, prioritize the most recent and assistant replies
        recent_non_system = non_system[-self.max_context_messages:] if self.max_context_messages > 0 else non_system

        # Further reduce context for very long conversations
        if len(recent_non_system) > max(6, self.max_context_messages // 2):
            # keep the last N messages and collapse earlier ones into a brief summary
            keep = max(6, self.max_context_messages // 2)
            head = recent_non_system[:-keep]
            tail = recent_non_system[-keep:]
            # summarize head into one line to keep tokens low
            head_summary = ' '.join([self._truncate_text(h.get('content', ''), 120) for h in head])
            if head_summary:
                optimized.append({'role': 'system', 'content': self._truncate_text('Conversation summary: ' + head_summary, 300)})
            recent_non_system = tail

        # Tighter per-message truncation to reduce token usage
        per_message_limit = max(120, min(400, self.max_input_chars // max(1, len(recent_non_system))))

        for msg in recent_non_system:
            content = msg.get('content', '')
            # Keep assistant responses shorter
            if msg.get('role') == 'assistant':
                content = self._truncate_text(content, per_message_limit // 2)
            optimized.append({
                'role': msg.get('role', 'user'),
                'content': self._truncate_text(content, per_message_limit)
            })

        return optimized

    def _call_provider(self, provider, messages, max_tokens):
        if provider == 'openrouter':
            return self._call_openrouter(messages, max_tokens)
        if provider == 'openai':
            return self._call_openai(messages, max_tokens)
        if provider == 'mistral':
            return self._call_mistral(messages, max_tokens)
        if provider == 'claude':
            return self._call_claude(messages, max_tokens)
        if provider == 'gemini':
            return self._call_gemini(messages, max_tokens)

        raise ValueError(f"Unsupported provider: {provider}")

    def _call_openrouter(self, messages, max_tokens):
        """Delegate to OpenRouterService adapter if available."""
        if self.openrouter_service:
            return self.openrouter_service.generate_chat(messages, max_tokens=max_tokens, temperature=0.5)

        # Fallback to previous inline implementation if adapter isn't available
        if not Config.OPENROUTER_API_KEY:
            raise ValueError("OpenRouter chưa được cấu hình")
        raise RuntimeError("OpenRouterService not initialized")

    def _call_openai(self, messages, max_tokens):
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
                    "model": Config.OPENAI_MODEL,
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
            return data['choices'][0]['message']['content']
            
        except requests.exceptions.RequestException as e:
            # Attach response for status code checking
            raise e

    def _call_mistral(self, messages, max_tokens):
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
                    "model": Config.MISTRAL_MODEL,
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
            return data['choices'][0]['message']['content']
            
        except requests.exceptions.RequestException as e:
            raise e

    def _call_claude(self, messages, max_tokens):
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
                    "model": Config.CLAUDE_MODEL,
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
            return "\n".join([t for t in texts if t])
            
        except requests.exceptions.RequestException as e:
            raise e

    def _call_gemini(self, messages, max_tokens):
        if not Config.GEMINI_API_KEY:
            raise ValueError("Gemini chưa được cấu hình")

        system_prompt, provider_messages = self._split_system_message(messages)

        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{Config.GEMINI_MODEL}:generateContent?key={Config.GEMINI_API_KEY}"
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
            return "\n".join(texts)
            
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
        chain = self._build_provider_chain() if self.configured_providers else []
        missing_providers = [
            provider for provider in ['openai', 'mistral', 'claude', 'gemini']
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
            "demo_mode": len(self.configured_providers) == 0 or all(not self._is_provider_healthy(p) for p in self.configured_providers)
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
    
    def summarize_email(self, email_content, user_id=None):
        """Summarize email content"""
        messages = [
            {
                "role": "system",
                "content": "Bạn là trợ lý giáo viên. Tóm tắt ngắn gọn email thành ý chính và 1-2 hành động."
            },
            {
                "role": "user",
                "content": f"Tóm tắt email sau:\n\n{self._truncate_text(email_content, self.max_input_chars)}"
            }
        ]
        return self.generate_response(messages, task='summary', user_id=user_id)
    
    def generate_reply(self, context, user_choice, user_id=None):
        """Generate automatic reply based on user choice"""
        messages = [
            {
                "role": "system",
                "content": "Bạn là trợ lý giáo viên. Viết email trả lời ngắn gọn, lịch sự, rõ ràng."
            },
            {
                "role": "user",
                "content": (
                    f"Bối cảnh: {self._truncate_text(context, self.max_input_chars)}\n\n"
                    f"Lựa chọn: {user_choice}\n\n"
                    "Viết email trả lời phù hợp."
                )
            }
        ]
        return self.generate_response(messages, task='reply', user_id=user_id)
    
    def analyze_text(self, text):
        """Analyze text for sentiment and intent"""
        messages = [
            {
                "role": "system",
                "content": "Phân tích ngắn: cảm xúc, ý định chính, hành động đề xuất."
            },
            {
                "role": "user",
                "content": f"Phân tích:\n\n{self._truncate_text(text, self.max_input_chars)}"
            }
        ]
        return self.generate_response(messages, task='analyze')

    def summarize_email_report(self, emails, report_date=None, user_id=None):
        """Summarize multiple emails in a single AI call for reporting."""
        if not emails:
            return []

        compact_items = []
        for idx, email in enumerate(emails, start=1):
            compact_text = self._truncate_text(
                f"Subject: {email.get('subject', '')}\n"
                f"Snippet: {email.get('snippet', '')}\n"
                f"Body: {email.get('body', '')}",
                420
            )
            compact_items.append(
                f"[{idx}] Sender: {email.get('sender', 'Unknown')}\n{compact_text}"
            )

        prompt = (
            "Tóm tắt từng email sau thành 1 câu ngắn. Nếu email là lịch họp/cuộc họp/lịch hẹn thì đặt is_meeting=true, "
            "thêm meeting_note ngắn và tạo suggested_start_time nếu có thể. "
            "Trả về JSON array, mỗi phần tử gồm: index (số), summary (chuỗi), is_meeting (bool), meeting_note (chuỗi), "
            "schedule_title (chuỗi), suggested_start_time (ISO string hoặc null), suggested_end_time (ISO string hoặc null), "
            "suggested_description (chuỗi). Không thêm giải thích ngoài JSON.\n\n"
            + "\n\n".join(compact_items)
        )

        max_tokens = min(700, max(220, len(emails) * 70))
        messages = [
            {
                "role": "system",
                "content": "Bạn là trợ lý giáo viên. Tóm tắt cực ngắn, rõ ý, đúng nội dung email."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        try:
            # Request compact JSON from AI to minimize parsing/roundtrips
            raw = self.generate_response(messages, max_tokens=max_tokens, task='summary', user_id=user_id)
            cleaned = raw.strip()
            if '```json' in cleaned:
                cleaned = cleaned.split('```json', 1)[1].split('```', 1)[0].strip()
            elif '```' in cleaned:
                cleaned = cleaned.split('```', 1)[1].split('```', 1)[0].strip()

            parsed = json.loads(cleaned)
            if not isinstance(parsed, list):
                raise ValueError("Invalid JSON structure")

            index_to_item = {}
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                idx = item.get('index')
                summary = str(item.get('summary', '')).strip()
                if isinstance(idx, int):
                    inferred = self._infer_meeting_signals(emails[idx - 1], report_date=report_date) if 1 <= idx <= len(emails) else {}
                    index_to_item[idx] = {
                        'summary': summary,
                        'is_meeting': bool(item.get('is_meeting', inferred.get('is_meeting', False))),
                        'meeting_note': str(item.get('meeting_note', inferred.get('meeting_note', ''))).strip(),
                        'schedule_title': str(item.get('schedule_title', inferred.get('schedule_title', ''))).strip(),
                        'suggested_start_time': item.get('suggested_start_time') or inferred.get('suggested_start_time'),
                        'suggested_end_time': item.get('suggested_end_time') or inferred.get('suggested_end_time'),
                        'suggested_description': str(item.get('suggested_description', inferred.get('suggested_description', ''))).strip(),
                    }

            rows = []
            for idx, email in enumerate(emails, start=1):
                fallback_summary = self._truncate_text(email.get('snippet', '') or email.get('body', ''), 180)
                inferred = self._infer_meeting_signals(email, report_date=report_date)
                item = index_to_item.get(idx, {})
                rows.append({
                    'sender': email.get('sender', 'Unknown'),
                    'summary': item.get('summary') or fallback_summary,
                    'subject': email.get('subject', ''),
                    'date': email.get('date', ''),
                    'is_meeting': bool(item.get('is_meeting', inferred.get('is_meeting', False))),
                    'meeting_note': item.get('meeting_note') or inferred.get('meeting_note', ''),
                    'schedule_title': item.get('schedule_title') or inferred.get('schedule_title', ''),
                    'suggested_start_time': item.get('suggested_start_time') or inferred.get('suggested_start_time'),
                    'suggested_end_time': item.get('suggested_end_time') or inferred.get('suggested_end_time'),
                    'suggested_description': item.get('suggested_description') or inferred.get('suggested_description', '')
                })
            # Cache the parsed rows for user for faster re-use
            try:
                if user_id:
                    db_path = get_user_db_path(user_id)
                    Cache.set(f"email_report::{user_id}::{report_date}", rows, db_path=db_path, ttl=600)
            except Exception:
                pass
            return rows
        except Exception:
            # Retry once with an explicit strict-JSON instruction to the AI
            try:
                strict_prompt = (
                    "Bạn phải trả về CHÍNH XÁC một JSON array duy nhất.\n"
                    "Mỗi phần tử là 1 object có các trường: index, summary, is_meeting, meeting_note, schedule_title, suggested_start_time, suggested_end_time, suggested_description.\n"
                    "Trả về KHÔNG có giải thích, không có mã đánh dấu khác. CHỈ JSON.\n\n"
                    + cleaned
                )
                retry_msgs = [
                    {"role": "system", "content": "Bạn là trợ lý giáo viên. Trả về đúng JSON như yêu cầu."},
                    {"role": "user", "content": strict_prompt}
                ]
                raw2 = self.generate_response(retry_msgs, max_tokens=min(800, max_tokens), task='summary', user_id=user_id)
                cleaned2 = raw2.strip()
                if '```json' in cleaned2:
                    cleaned2 = cleaned2.split('```json', 1)[1].split('```', 1)[0].strip()
                elif '```' in cleaned2:
                    cleaned2 = cleaned2.split('```', 1)[1].split('```', 1)[0].strip()
                parsed2 = json.loads(cleaned2)
                if isinstance(parsed2, list):
                    parsed = parsed2
                else:
                    raise
            except Exception:
                rows = []
            for email in emails:
                fallback_summary = self._truncate_text(email.get('snippet', '') or email.get('body', ''), 180)
                inferred = self._infer_meeting_signals(email, report_date=report_date)
                rows.append({
                    'sender': email.get('sender', 'Unknown'),
                    'summary': fallback_summary,
                    'subject': email.get('subject', ''),
                    'date': email.get('date', ''),
                    'is_meeting': inferred.get('is_meeting', False),
                    'meeting_note': inferred.get('meeting_note', ''),
                    'schedule_title': inferred.get('schedule_title', ''),
                    'suggested_start_time': inferred.get('suggested_start_time'),
                    'suggested_end_time': inferred.get('suggested_end_time'),
                    'suggested_description': inferred.get('suggested_description', '')
                })
            return rows
