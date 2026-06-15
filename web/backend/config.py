import os

try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except Exception:
    pass


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", 5000))
    DEBUG = _bool(os.getenv("DEBUG"), default=True)

    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(REPO_ROOT, "data")
    DATABASE_PATH = os.path.join(DATA_DIR, "assistant.db")
    GMAIL_CREDENTIALS_FILE = os.path.join(DATA_DIR, "credentials.json")
    GMAIL_TOKEN_FILE = os.path.join(DATA_DIR, "users", "gmail_token.pickle")

    GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
    GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
    GMAIL_CREDENTIALS_JSON = os.getenv("GMAIL_CREDENTIALS_JSON", "")
    GMAIL_REDIRECT_URI = os.getenv("GMAIL_REDIRECT_URI", "")

    GMAIL_CLIENT_ID_KEYS = ["GMAIL_CLIENT_ID", "GMAIL_CLIENT_ID_ALT"]
    GMAIL_CLIENT_SECRET_KEYS = ["GMAIL_CLIENT_SECRET"]
    GMAIL_CREDENTIALS_JSON_KEYS = ["GMAIL_CREDENTIALS_JSON"]

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_ENABLED = _bool(os.getenv("OPENROUTER_ENABLED"), default=bool(OPENROUTER_API_KEY))
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
    MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-1")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-opus")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

    AI_PRIMARY_PROVIDER = os.getenv("AI_PRIMARY_PROVIDER", "openrouter")
    AI_PROVIDER_ORDER = os.getenv("AI_PROVIDER_ORDER", "openrouter,openai,mistral,claude,gemini")
    AI_REQUEST_TIMEOUT = int(os.getenv("AI_REQUEST_TIMEOUT", 20))
    AI_MAX_CONTEXT_MESSAGES = int(os.getenv("AI_MAX_CONTEXT_MESSAGES", 6))
    AI_MAX_INPUT_CHARS = int(os.getenv("AI_MAX_INPUT_CHARS", 2800))
    AI_MAX_SYSTEM_PROMPT_CHARS = int(os.getenv("AI_MAX_SYSTEM_PROMPT_CHARS", 450))
    AI_DEFAULT_MAX_TOKENS = int(os.getenv("AI_DEFAULT_MAX_TOKENS", 220))
    AI_SUMMARY_MAX_TOKENS = int(os.getenv("AI_SUMMARY_MAX_TOKENS", 180))
    AI_REPLY_MAX_TOKENS = int(os.getenv("AI_REPLY_MAX_TOKENS", 220))
    AI_ANALYZE_MAX_TOKENS = int(os.getenv("AI_ANALYZE_MAX_TOKENS", 180))

    AI_TASK_PROVIDERS_CHAT = os.getenv("AI_TASK_PROVIDERS_CHAT", "")
    AI_TASK_PROVIDERS_SUMMARY = os.getenv("AI_TASK_PROVIDERS_SUMMARY", "")
    AI_TASK_PROVIDERS_REPLY = os.getenv("AI_TASK_PROVIDERS_REPLY", "")
    AI_TASK_PROVIDERS_ANALYZE = os.getenv("AI_TASK_PROVIDERS_ANALYZE", "")

    SESSION_COOKIE_SECURE = _bool(os.getenv("SESSION_COOKIE_SECURE"), default=False)
    MOBILE_TOKEN_MAX_AGE = int(os.getenv("MOBILE_TOKEN_MAX_AGE", 24 * 3600))
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", 180))
    AI_RATE_LIMIT_PER_MINUTE = int(os.getenv("AI_RATE_LIMIT_PER_MINUTE", 30))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 1024 * 1024))
    ALLOWED_ORIGINS = [
        item.strip()
        for item in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:5000,http://127.0.0.1:5000",
        ).split(",")
        if item.strip()
    ]

    if not SECRET_KEY:
        if DEBUG:
            SECRET_KEY = "development-only-change-me"
        else:
            raise RuntimeError("SECRET_KEY must be configured when DEBUG is disabled")

    @classmethod
    def as_dict(cls):
        return {key: value for key, value in cls.__dict__.items() if key.isupper()}


GMAIL_CLIENT_ID_KEYS = Config.GMAIL_CLIENT_ID_KEYS
GMAIL_CLIENT_SECRET_KEYS = Config.GMAIL_CLIENT_SECRET_KEYS
GMAIL_CREDENTIALS_JSON_KEYS = Config.GMAIL_CREDENTIALS_JSON_KEYS
