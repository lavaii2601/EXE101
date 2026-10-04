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
    GMAIL_TOKEN_FILE = os.path.join(DATA_DIR, "users", "gmail_token.json")

    GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
    GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
    GMAIL_CREDENTIALS_JSON = os.getenv("GMAIL_CREDENTIALS_JSON", "")
    GMAIL_REDIRECT_URI = os.getenv("GMAIL_REDIRECT_URI", "")
    MOBILE_OAUTH_REDIRECT_URL = os.getenv("MOBILE_OAUTH_REDIRECT_URL", "flowmateai://oauth-callback")

    # SEPay Payment Gateway. The signing secret is backend-only and must
    # never be exposed in a web/mobile response. Sandbox is the safe default;
    # set SEPAY_ENV=production explicitly when the production merchant is
    # ready to receive real payments.
    SEPAY_ENV = os.getenv("SEPAY_ENV", "sandbox").strip().lower()
    SEPAY_MERCHANT_ID = os.getenv("SEPAY_MERCHANT_ID", "").strip()
    SEPAY_SECRET_KEY = os.getenv("SEPAY_SECRET_KEY", "").strip()
    SEPAY_IPN_SECRET_KEY = (
        os.getenv("SEPAY_IPN_SECRET_KEY", "").strip()
        or os.getenv("SEPAY_IPN_SECRET", "").strip()
        or SEPAY_SECRET_KEY
    )
    SEPAY_CHECKOUT_URL = os.getenv("SEPAY_CHECKOUT_URL", "").strip() or (
        "https://pay.sepay.vn/v1/checkout/init"
        if SEPAY_ENV == "production"
        else "https://pay-sandbox.sepay.vn/v1/checkout/init"
    )

    GMAIL_CLIENT_ID_KEYS = ["GMAIL_CLIENT_ID", "GMAIL_CLIENT_ID_ALT"]
    GMAIL_CLIENT_SECRET_KEYS = ["GMAIL_CLIENT_SECRET"]
    GMAIL_CREDENTIALS_JSON_KEYS = ["GMAIL_CREDENTIALS_JSON"]

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_ENABLED = _bool(os.getenv("OPENROUTER_ENABLED"), default=bool(OPENROUTER_API_KEY))
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    # Bob calls out to a hosted provider (OpenAI/Mistral/Claude/Gemini, via
    # services/ai_service.py) whenever at least one of the keys above is
    # configured -- cheap to justify while the user base is still small.
    # BOB_LOCAL_ONLY can still force the old fully-local/deterministic
    # engine explicitly (e.g. "BOB_LOCAL_ONLY=true") regardless of which
    # keys are present; with no keys AND no override it defaults to local,
    # so an empty/misconfigured key set degrades to the old deterministic
    # behavior rather than to AIService's much weaker generic Demo Mode.
    _any_external_ai_key_configured = bool(
        OPENAI_API_KEY or MISTRAL_API_KEY or CLAUDE_API_KEY or GEMINI_API_KEY
    )
    BOB_LOCAL_ONLY = _bool(
        os.getenv("BOB_LOCAL_ONLY"), default=not _any_external_ai_key_configured
    )
    OLLAMA_ENABLED = _bool(os.getenv("OLLAMA_ENABLED"), default=False)
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # "-latest"/dated aliases the providers themselves keep pointed at their
    # current flagship, so these stay valid without needing to be bumped by
    # hand -- override via env var for a specific pinned version instead.
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
    MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-large-latest")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

    # OpenRouter's own model selection -- previously referenced via getattr()
    # in services/openrouter_service.py with no definition here at all, so
    # self.primary_model was always None and every OpenRouter call
    # unconditionally raised RuntimeError regardless of API key. Defining
    # them (empty-string default, matching that prior no-op state) is a
    # pure bugfix; OpenRouter stays inert until an operator sets one.
    OPENROUTER_PRIMARY_MODEL = os.getenv("OPENROUTER_PRIMARY_MODEL", "")
    OPENROUTER_MODEL_FALLBACK = os.getenv("OPENROUTER_MODEL_FALLBACK", "")

    # Cheap-tier model siblings, one per provider -- each defaults to that
    # provider's own strong model above, so a deployment that never sets
    # these sees byte-for-byte identical behavior to before tiering existed.
    # AIService picks cheap vs strong per task (see AI_TASK_TIER_* below),
    # not per provider -- these just say *which model* a given provider
    # uses once a task has already picked a tier.
    OPENAI_MODEL_CHEAP = os.getenv("OPENAI_MODEL_CHEAP", "") or OPENAI_MODEL
    MISTRAL_MODEL_CHEAP = os.getenv("MISTRAL_MODEL_CHEAP", "") or MISTRAL_MODEL
    CLAUDE_MODEL_CHEAP = os.getenv("CLAUDE_MODEL_CHEAP", "") or CLAUDE_MODEL
    GEMINI_MODEL_CHEAP = os.getenv("GEMINI_MODEL_CHEAP", "") or GEMINI_MODEL
    OLLAMA_MODEL_CHEAP = os.getenv("OLLAMA_MODEL_CHEAP", "") or OLLAMA_MODEL
    OPENROUTER_PRIMARY_MODEL_CHEAP = (
        os.getenv("OPENROUTER_PRIMARY_MODEL_CHEAP", "") or OPENROUTER_PRIMARY_MODEL
    )

    AI_PRIMARY_PROVIDER = os.getenv("AI_PRIMARY_PROVIDER", "openrouter")
    AI_PROVIDER_ORDER = os.getenv("AI_PROVIDER_ORDER", "openrouter,openai,mistral,claude,gemini")
    AI_REQUEST_TIMEOUT = int(os.getenv("AI_REQUEST_TIMEOUT", 20))
    AI_MAX_CONTEXT_MESSAGES = int(os.getenv("AI_MAX_CONTEXT_MESSAGES", 10))
    # These are character budgets (not output-token budgets).  The previous
    # 450/2800 defaults cut Bob's safety/language contract and, for intent
    # classification, even removed the latest user message before it reached
    # the provider.
    AI_MAX_INPUT_CHARS = int(os.getenv("AI_MAX_INPUT_CHARS", 12000))
    AI_MAX_SYSTEM_PROMPT_CHARS = int(os.getenv("AI_MAX_SYSTEM_PROMPT_CHARS", 12000))
    AI_DEFAULT_MAX_TOKENS = int(os.getenv("AI_DEFAULT_MAX_TOKENS", 220))
    AI_AGENT_MAX_TOKENS = int(os.getenv("AI_AGENT_MAX_TOKENS", 700))
    AI_SUMMARY_MAX_TOKENS = int(os.getenv("AI_SUMMARY_MAX_TOKENS", 180))
    AI_REPLY_MAX_TOKENS = int(os.getenv("AI_REPLY_MAX_TOKENS", 220))
    AI_ANALYZE_MAX_TOKENS = int(os.getenv("AI_ANALYZE_MAX_TOKENS", 180))
    AI_OVERVIEW_BRIEF_MAX_TOKENS = int(os.getenv("AI_OVERVIEW_BRIEF_MAX_TOKENS", 260))
    AI_MEETING_CONFIRM_MAX_TOKENS = int(os.getenv("AI_MEETING_CONFIRM_MAX_TOKENS", 220))

    AI_TASK_PROVIDERS_CHAT = os.getenv("AI_TASK_PROVIDERS_CHAT", "")
    AI_TASK_PROVIDERS_SUMMARY = os.getenv("AI_TASK_PROVIDERS_SUMMARY", "")
    AI_TASK_PROVIDERS_REPLY = os.getenv("AI_TASK_PROVIDERS_REPLY", "")
    AI_TASK_PROVIDERS_ANALYZE = os.getenv("AI_TASK_PROVIDERS_ANALYZE", "")
    AI_TASK_PROVIDERS_INTENT_CLASSIFICATION = os.getenv("AI_TASK_PROVIDERS_INTENT_CLASSIFICATION", "")
    AI_TASK_PROVIDERS_OVERVIEW_BRIEF = os.getenv("AI_TASK_PROVIDERS_OVERVIEW_BRIEF", "")
    AI_TASK_PROVIDERS_MEETING_CONFIRM = os.getenv("AI_TASK_PROVIDERS_MEETING_CONFIRM", "")

    # Which model size each task uses. 'chat' (Bob's free-text synthesis) is
    # the one task worth paying for quality; everything else -- intent
    # classification and the two new AI-assist features below -- gets a
    # fast/cheap model by default since their inputs are small and
    # structured. Falls back to the strong model automatically wherever a
    # provider has no cheap sibling configured (see *_MODEL_CHEAP above).
    AI_TASK_TIER_CHAT = os.getenv("AI_TASK_TIER_CHAT", "strong")
    AI_TASK_TIER_INTENT_CLASSIFICATION = os.getenv("AI_TASK_TIER_INTENT_CLASSIFICATION", "cheap")
    AI_TASK_TIER_SUMMARY = os.getenv("AI_TASK_TIER_SUMMARY", "cheap")
    AI_TASK_TIER_REPLY = os.getenv("AI_TASK_TIER_REPLY", "cheap")
    AI_TASK_TIER_ANALYZE = os.getenv("AI_TASK_TIER_ANALYZE", "cheap")
    AI_TASK_TIER_OVERVIEW_BRIEF = os.getenv("AI_TASK_TIER_OVERVIEW_BRIEF", "cheap")
    AI_TASK_TIER_MEETING_CONFIRM = os.getenv("AI_TASK_TIER_MEETING_CONFIRM", "cheap")

    # Caps the worst case of detect_workflow_with_ai fanning one message into
    # up to 8 parts, each of which can itself trigger up to 2 intent-
    # classification LLM calls (an initial attempt plus one self-correction
    # retry) -- i.e. up to 16 calls for a single user message. Once this
    # many of those calls have actually reached the AI fallback, remaining
    # parts use the free, already-computed rule-based classifier result
    # instead of escalating further. Does not affect the typical 2-3 part
    # message, and does not touch any single-message (non-workflow) call.
    AI_WORKFLOW_MAX_AI_CLASSIFICATIONS = int(os.getenv("AI_WORKFLOW_MAX_AI_CLASSIFICATIONS", 4))

    # Kill switches for the two new AI-assist features below (Daily Overview
    # narrative synthesis, meeting-detection AI confirmation). Both also
    # hard-gate on BOB_LOCAL_ONLY/no configured providers regardless of this
    # flag, so a zero-provider deployment is unaffected either way; this is
    # for an operator who HAS providers configured but wants to disable just
    # one of these specific features without touching provider config.
    AI_OVERVIEW_BRIEF_ENABLED = _bool(os.getenv("AI_OVERVIEW_BRIEF_ENABLED"), default=True)
    AI_MEETING_CONFIRM_ENABLED = _bool(os.getenv("AI_MEETING_CONFIRM_ENABLED"), default=True)

    # Observability only -- never gates behavior, just whether ai_cost_log
    # rows get written. Postgres-only and fail-open regardless (see
    # models/ai_cost_log.py), so this is purely an extra off-switch for an
    # operator who wants to silence the writes without a redeploy.
    AI_COST_TRACKING_ENABLED = _bool(os.getenv("AI_COST_TRACKING_ENABLED"), default=True)

    # Offline by default: local RAG remains fully available, while public web
    # retrieval must be an explicit deployment choice.
    WEB_RESEARCH_ENABLED = _bool(os.getenv("WEB_RESEARCH_ENABLED"), default=False)
    WEB_RESEARCH_AUTO_LEARN_ENABLED = _bool(os.getenv("WEB_RESEARCH_AUTO_LEARN_ENABLED"), default=False)
    WEB_RESEARCH_MAX_RESULTS = int(os.getenv("WEB_RESEARCH_MAX_RESULTS", 3))
    WEB_RESEARCH_FETCH_PAGES = int(os.getenv("WEB_RESEARCH_FETCH_PAGES", 2))
    WEB_RESEARCH_TIMEOUT = int(os.getenv("WEB_RESEARCH_TIMEOUT", 8))
    WEB_RESEARCH_MAX_BYTES = int(os.getenv("WEB_RESEARCH_MAX_BYTES", 180000))
    WEB_RESEARCH_MAX_CHARS = int(os.getenv("WEB_RESEARCH_MAX_CHARS", 1800))
    WEB_RESEARCH_ACADEMIC_ENABLED = _bool(
        os.getenv("WEB_RESEARCH_ACADEMIC_ENABLED"), default=True
    )
    WEB_RESEARCH_LEARNING_MAX_PER_DAY = int(os.getenv("WEB_RESEARCH_LEARNING_MAX_PER_DAY", 6))

    AI_MENTOR_LEARNING_ENABLED = _bool(os.getenv("AI_MENTOR_LEARNING_ENABLED"), default=True)
    AI_MENTOR_ALLOW_PRIVATE_CONTEXT = _bool(os.getenv("AI_MENTOR_ALLOW_PRIVATE_CONTEXT"), default=False)
    AI_MENTOR_PROVIDERS = os.getenv("AI_MENTOR_PROVIDERS", "openai,gemini,claude,openrouter,mistral,ollama")
    AI_MENTOR_MAX_PROVIDERS = int(os.getenv("AI_MENTOR_MAX_PROVIDERS", 2))
    AI_MENTOR_MAX_TOKENS = int(os.getenv("AI_MENTOR_MAX_TOKENS", 260))
    AI_MENTOR_MIN_MESSAGE_CHARS = int(os.getenv("AI_MENTOR_MIN_MESSAGE_CHARS", 18))
    AI_MENTOR_LEARNING_MAX_PER_DAY = int(os.getenv("AI_MENTOR_LEARNING_MAX_PER_DAY", 6))

    SESSION_COOKIE_SECURE = _bool(os.getenv("SESSION_COOKIE_SECURE"), default=False)
    # Explicit override; otherwise derived from RAILWAY_PUBLIC_DOMAIN below so
    # the session cookie (holding oauth_state/oauth_code_verifier) is shared
    # between the apex domain and its "www." host -- the OAuth flow can start
    # on either one, but Google always redirects back to whichever exact
    # redirect_uri is registered in Cloud Console, which may be the other.
    SESSION_COOKIE_DOMAIN = os.getenv("SESSION_COOKIE_DOMAIN", "")
    if not SESSION_COOKIE_DOMAIN:
        _public_domain = (os.getenv("RAILWAY_PUBLIC_DOMAIN", "") or "").strip().lower()
        if _public_domain and "." in _public_domain:
            SESSION_COOKIE_DOMAIN = "." + _public_domain.removeprefix("www.")
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
