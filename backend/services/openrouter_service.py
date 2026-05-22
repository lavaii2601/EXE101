import requests
from config import Config


class OpenRouterService:
    """Adapter for OpenRouter API with model fallback and basic error handling."""

    def __init__(self, timeout=20):
        self.api_key = getattr(Config, 'OPENROUTER_API_KEY', None)
        self.primary_model = getattr(Config, 'OPENROUTER_PRIMARY_MODEL', None)
        fallback = getattr(Config, 'OPENROUTER_MODEL_FALLBACK', '') or ''
        self.fallback_models = [m.strip() for m in fallback.split(',') if m.strip()]
        self.timeout = timeout

    def _models_to_try(self):
        models = []
        if self.primary_model:
            models.append(self.primary_model)
        for m in self.fallback_models:
            if m not in models:
                models.append(m)
        return models

    def generate_chat(self, messages, max_tokens=220, temperature=0.5):
        if not self.api_key:
            raise ValueError('OpenRouter API key not configured')

        last_error = None

        for model in self._models_to_try():
            try:
                payload = {
                    'model': model,
                    'messages': messages,
                    'max_tokens': max_tokens,
                    'temperature': temperature
                }
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                }

                resp = requests.post(
                    'https://openrouter.ai/api/v1/chat/completions',
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )

                if resp.status_code in (429, 401, 402, 403):
                    # quota or auth error - try next model
                    try:
                        err = resp.json()
                        msg = err.get('error', {}).get('message', str(resp.status_code))
                    except Exception:
                        msg = f'HTTP {resp.status_code}'
                    last_error = f"{model}: {msg}"
                    continue

                resp.raise_for_status()
                data = resp.json()
                # Expect standard OpenRouter chat shape
                choice = data.get('choices', [{}])[0]
                message = choice.get('message') or {}
                content = message.get('content')
                if isinstance(content, dict):
                    # sometimes content may be {'type':'output_text','text': '...'}
                    text = content.get('text') or content.get('content') or ''
                else:
                    text = content or ''

                if text:
                    return text

            except requests.RequestException as e:
                last_error = str(e)
                continue

        raise RuntimeError(f'OpenRouter failed for all models. Last error: {last_error}')
