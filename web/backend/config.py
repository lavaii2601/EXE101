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
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    GMAIL_CREDENTIALS_FILE = os.path.join(DATA_DIR, "credentials.json")
    GMAIL_TOKEN_FILE = os.path.join(DATA_DIR, "users", "gmail_token.pickle")

    GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
    GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
    GMAIL_CREDENTIALS_JSON = os.getenv("GMAIL_CREDENTIALS_JSON", "")
    GMAIL_REDIRECT_URI = os.getenv("GMAIL_REDIRECT_URI", "")
    MOBILE_OAUTH_REDIRECT_URL = os.getenv("MOBILE_OAUTH_REDIRECT_URL", "flowmateai://oauth-callback")

    GMAIL_CLIENT_ID_KEYS = ["GMAIL_CLIENT_ID", "GMAIL_CLIENT_ID_ALT"]
    GMAIL_CLIENT_SECRET_KEYS = ["GMAIL_CLIENT_SECRET"]
    GMAIL_CREDENTIALS_JSON_KEYS = ["GMAIL_CREDENTIALS_JSON"]

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_ENABLED = _bool(os.getenv("OPENROUTER_ENABLED"), default=bool(OPENROUTER_API_KEY))
    # Bob's production engine is deterministic/local by default. External
    # model adapters remain in the repository only for backwards-compatible
    # experiments; core chat, tools, RAG, summaries, and learning must never
    # require them.
    BOB_LOCAL_ONLY = True
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    OLLAMA_ENABLED = _bool(os.getenv("OLLAMA_ENABLED"), default=False)
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
    MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-1")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-opus")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

    AI_PRIMARY_PROVIDER = os.getenv("AI_PRIMARY_PROVIDER", "openrouter")
    AI_PROVIDER_ORDER = os.getenv("AI_PROVIDER_ORDER", "openrouter,openai,mistral,claude,gemini")
    AI_REQUEST_TIMEOUT = int(os.getenv("AI_REQUEST_TIMEOUT", 20))
    AI_MAX_CONTEXT_MESSAGES = int(os.getenv("AI_MAX_CONTEXT_MESSAGES", 10))
    # These are character budgets (not output-token budgets).  The previous
    # 450/2800 defaults cut Bob's safety/language contract and, for intent
    # classification, even removed the latest user message before it reached
    # the provider.
    AI_MAX_INPUT_CHARS = int(os.getenv("AI_MAX_INPUT_CHARS", 12000))
    AI_MAX_SYSTEM_PROMPT_CHARS = int(os.getenv("AI_MAX_SYSTEM_PROMPT_CHARS", 8000))
    AI_DEFAULT_MAX_TOKENS = int(os.getenv("AI_DEFAULT_MAX_TOKENS", 220))
    AI_SUMMARY_MAX_TOKENS = int(os.getenv("AI_SUMMARY_MAX_TOKENS", 180))
    AI_REPLY_MAX_TOKENS = int(os.getenv("AI_REPLY_MAX_TOKENS", 220))
    AI_ANALYZE_MAX_TOKENS = int(os.getenv("AI_ANALYZE_MAX_TOKENS", 180))

    AI_TASK_PROVIDERS_CHAT = os.getenv("AI_TASK_PROVIDERS_CHAT", "")
    AI_TASK_PROVIDERS_SUMMARY = os.getenv("AI_TASK_PROVIDERS_SUMMARY", "")
    AI_TASK_PROVIDERS_REPLY = os.getenv("AI_TASK_PROVIDERS_REPLY", "")
    AI_TASK_PROVIDERS_ANALYZE = os.getenv("AI_TASK_PROVIDERS_ANALYZE", "")

    WEB_RESEARCH_ENABLED = _bool(os.getenv("WEB_RESEARCH_ENABLED"), default=True)
    WEB_RESEARCH_AUTO_LEARN_ENABLED = _bool(os.getenv("WEB_RESEARCH_AUTO_LEARN_ENABLED"), default=False)
    WEB_RESEARCH_MAX_RESULTS = int(os.getenv("WEB_RESEARCH_MAX_RESULTS", 3))
    WEB_RESEARCH_FETCH_PAGES = int(os.getenv("WEB_RESEARCH_FETCH_PAGES", 2))
    WEB_RESEARCH_TIMEOUT = int(os.getenv("WEB_RESEARCH_TIMEOUT", 8))
    WEB_RESEARCH_MAX_BYTES = int(os.getenv("WEB_RESEARCH_MAX_BYTES", 180000))
    WEB_RESEARCH_MAX_CHARS = int(os.getenv("WEB_RESEARCH_MAX_CHARS", 1800))
    WEB_RESEARCH_LEARNING_MAX_PER_DAY = int(os.getenv("WEB_RESEARCH_LEARNING_MAX_PER_DAY", 6))

    AI_MENTOR_LEARNING_ENABLED = _bool(os.getenv("AI_MENTOR_LEARNING_ENABLED"), default=False)
    AI_MENTOR_ALLOW_PRIVATE_CONTEXT = _bool(os.getenv("AI_MENTOR_ALLOW_PRIVATE_CONTEXT"), default=False)
    AI_MENTOR_PROVIDERS = os.getenv("AI_MENTOR_PROVIDERS", "openai,gemini,claude,openrouter,mistral,ollama")
    AI_MENTOR_MAX_PROVIDERS = int(os.getenv("AI_MENTOR_MAX_PROVIDERS", 2))
    AI_MENTOR_MAX_TOKENS = int(os.getenv("AI_MENTOR_MAX_TOKENS", 260))
    AI_MENTOR_MIN_MESSAGE_CHARS = int(os.getenv("AI_MENTOR_MIN_MESSAGE_CHARS", 18))
    AI_MENTOR_LEARNING_MAX_PER_DAY = int(os.getenv("AI_MENTOR_LEARNING_MAX_PER_DAY", 6))

    SESSION_COOKIE_SECURE = _bool(os.getenv("SESSION_COOKIE_SECURE"), default=False)
    MOBILE_TOKEN_MAX_AGE = int(os.getenv("MOBILE_TOKEN_MAX_AGE", 30 * 24 * 3600))
    MOBILE_USER_HEADER_ENABLED = _bool(os.getenv("MOBILE_USER_HEADER_ENABLED"), default=DEBUG)
    ADMIN_EMAILS = {
        item.strip().lower()
        for item in os.getenv("ADMIN_EMAILS", "").split(",")
        if item.strip()
    }
    ADMIN_TOTP_SECRET = os.getenv("ADMIN_TOTP_SECRET", "")
    ADMIN_TOTP_SESSION_SECONDS = int(os.getenv("ADMIN_TOTP_SESSION_SECONDS", 8 * 3600))
    ADMIN_TOTP_MAX_ATTEMPTS = int(os.getenv("ADMIN_TOTP_MAX_ATTEMPTS", 5))
    ADMIN_TOTP_ATTEMPT_WINDOW_SECONDS = int(
        os.getenv("ADMIN_TOTP_ATTEMPT_WINDOW_SECONDS", 300)
    )
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

    # Fail closed in production: both of these silently downgrade auth when
    # left at their DEBUG-friendly defaults. MOBILE_USER_HEADER_ENABLED
    # trusts a client-supplied X-User-Id header as identity with no
    # verification at all (utils/security.py::header_user_id) -- a full
    # auth bypass if left on. SESSION_COOKIE_SECURE=False lets the session
    # cookie travel over plain HTTP. Refuse to boot rather than run either
    # unsafely once DEBUG is off.
    if not DEBUG:
        if MOBILE_USER_HEADER_ENABLED:
            raise RuntimeError("MOBILE_USER_HEADER_ENABLED must be false when DEBUG is disabled")
        if not SESSION_COOKIE_SECURE:
            raise RuntimeError("SESSION_COOKIE_SECURE must be true when DEBUG is disabled")

    @classmethod
    def as_dict(cls):
        return {key: value for key, value in cls.__dict__.items() if key.isupper()}


GMAIL_CLIENT_ID_KEYS = Config.GMAIL_CLIENT_ID_KEYS
GMAIL_CLIENT_SECRET_KEYS = Config.GMAIL_CLIENT_SECRET_KEYS
GMAIL_CREDENTIALS_JSON_KEYS = Config.GMAIL_CREDENTIALS_JSON_KEYS
