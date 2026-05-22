from flask import Flask, send_from_directory, jsonify, session as flask_session
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import sys
import logging

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Allow insecure OAuth transport for local development (HTTP)
# Must be set before importing google oauth flow modules
os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')

from config import Config
from models.schedule import Schedule
from models.history import History
from models.user import User
from routes.chat import chat_bp
from routes.email import email_bp
from routes.schedule import schedule_bp
from routes.user import user_bp
from routes.calendar import calendar_bp
from routes._background import bg_bp

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# Enhanced session configuration for OAuth and user tracking
app.config.update(
    SESSION_COOKIE_SECURE=False,  # HTTP in development, set to True for HTTPS production
    SESSION_COOKIE_HTTPONLY=True,  # Prevent JS from accessing session cookie
    SESSION_COOKIE_SAMESITE='Lax',  # Allow cross-site redirects from OAuth providers
    PERMANENT_SESSION_LIFETIME=86400,  # 24 hours
    SESSION_REFRESH_EACH_REQUEST=True,  # Extend session lifetime on each request
)

# Set permanent session to persist across server restarts
@app.before_request
def make_session_permanent():
    flask_session.permanent = True

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
# Allow CORS with credentials for the frontend origin(s) so session cookies are preserved
allowed_origins = [
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://192.168.0.102:5000"
]
CORS(app, resources={r"/api/*": {"origins": allowed_origins}}, supports_credentials=True)

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
