from flask import Flask, send_from_directory, jsonify, session as flask_session, request
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import sys
import logging

# Ensure stdout/stderr can print emoji/unicode log messages on Windows consoles
# (default cp1252 encoding raises UnicodeEncodeError on prints like "🔄").
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors='replace')

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config

# OAuthlib requires HTTPS except for explicitly allowed local development.
# Set this after Config loads web/.env, but before importing OAuth routes.
_gmail_redirect_uri = (Config.GMAIL_REDIRECT_URI or '').lower()
_local_oauth_redirect = (
    _gmail_redirect_uri.startswith('http://127.0.0.1')
    or _gmail_redirect_uri.startswith('http://localhost')
)
if Config.DEBUG or _local_oauth_redirect:
    os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')

from models.schedule import Schedule
from models.history import History
from models.user import User
from routes.chat import chat_bp
from routes.email import email_bp
from routes.schedule import schedule_bp
from routes.user import user_bp
from routes.calendar import calendar_bp
from routes._background import bg_bp
from utils.security import authenticated_user_id, enforce_rate_limit, valid_request_origin

# Keep application diagnostics without logging OAuth request/response tokens.
logging.basicConfig(level=logging.INFO)
logging.getLogger('requests_oauthlib').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# Enhanced session configuration for OAuth and user tracking
app.config.update(
    SESSION_COOKIE_SECURE=Config.SESSION_COOKIE_SECURE,
    SESSION_COOKIE_HTTPONLY=True,  # Prevent JS from accessing session cookie
    SESSION_COOKIE_SAMESITE='Lax',  # Allow cross-site redirects from OAuth providers
    SESSION_COOKIE_NAME='flowmate_session',
    PERMANENT_SESSION_LIFETIME=86400,  # 24 hours
    SESSION_REFRESH_EACH_REQUEST=True,  # Extend session lifetime on each request
)

# Set permanent session to persist across server restarts
@app.before_request
def make_session_permanent():
    flask_session.permanent = True
    limited = enforce_rate_limit()
    if limited:
        return jsonify(limited[0]), limited[1]
    if request.path.startswith('/api/') and not valid_request_origin():
        return jsonify({'error': 'invalid_request_origin'}), 403
    public_api_paths = {
        '/api/health',
        '/api/status',
        '/api/email/auth',
        '/api/email/auth_url',
        '/api/email/auth-status',
        '/api/email/oauth2callback',
        '/api/email/oauth-config-check',
        '/api/email/google-auth',
    }
    if (
        request.path.startswith('/api/')
        and request.path not in public_api_paths
        and not authenticated_user_id()
    ):
        return jsonify({'error': 'not_authenticated'}), 401

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
# Allow CORS with credentials for the frontend origin(s) so session cookies are preserved
allowed_origins = Config.ALLOWED_ORIGINS
CORS(app, resources={r"/api/*": {"origins": allowed_origins}}, supports_credentials=True)


@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin-allow-popups'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "img-src 'self' data: https://*.googleusercontent.com; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# Register blueprints
app.register_blueprint(chat_bp)
app.register_blueprint(email_bp)
app.register_blueprint(schedule_bp)
app.register_blueprint(user_bp)
app.register_blueprint(calendar_bp)
app.register_blueprint(bg_bp)

# Ensure data directory exists
os.makedirs(os.path.dirname(Config.DATABASE_PATH), exist_ok=True)

# Initialize databases
Schedule.init_db()
History.init_db()
User.init_db()

# Serve frontend
@app.route('/')
def serve_frontend():
    """Serve frontend index.html"""
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files"""
    if path.startswith('css/') or path.startswith('js/'):
        return send_from_directory('../frontend', path)
    return send_from_directory('../frontend', 'index.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok'})

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get system status"""
    gmail_from_env = bool(Config.GMAIL_CLIENT_ID and Config.GMAIL_CLIENT_SECRET)
    gmail_from_json = bool(Config.GMAIL_CREDENTIALS_JSON)
    gmail_from_file = os.path.exists(Config.GMAIL_CREDENTIALS_FILE)

    ai_map = {
        'openrouter': bool(getattr(Config, 'OPENROUTER_API_KEY', None)),
        'openai': bool(Config.OPENAI_API_KEY),
        'mistral': bool(Config.MISTRAL_API_KEY),
        'claude': bool(Config.CLAUDE_API_KEY),
        'gemini': bool(Config.GEMINI_API_KEY)
    }
    missing_ai = [name for name, ok in ai_map.items() if not ok]

    return jsonify({
        'gmail_configured': gmail_from_env or gmail_from_json or gmail_from_file,
        'gmail_methods': {
            'env_vars': gmail_from_env,
            'json_env': gmail_from_json,
            'credentials_file': gmail_from_file
        },
        'ai_providers': {k: v for k, v in ai_map.items()},
        'missing_ai_providers': missing_ai,
        'all_ready': not missing_ai
    })

@app.route('/api/debug/session', methods=['GET'])
def debug_session():
    """Debug: Check session state (development only)"""
    if not app.debug:
        return jsonify({'error': 'Not available in production'}), 403
    
    session_data = dict(flask_session)
    # Don't expose sensitive data
    safe_data = {
        'user_id': session_data.get('user_id'),
        'gmail_user_email': session_data.get('gmail_user_email'),
        'gmail_user_name': session_data.get('gmail_user_name'),
        'has_oauth_state': bool(session_data.get('oauth_state')),
        'keys': list(session_data.keys())
    }
    
    return jsonify({
        'session': safe_data,
        'cookies_sent': bool(app.config.get('SESSION_COOKIE_SECURE'))
    })


if __name__ == '__main__':
    app.run(host=Config.API_HOST, port=Config.API_PORT, debug=Config.DEBUG)
