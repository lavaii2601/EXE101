# EXE101

Lightweight assistant for teachers: email + AI + scheduling with Google Calendar sync.

## Features
- Chat with AI (multi-provider orchestration: OpenRouter, OpenAI, Mistral, Claude, Gemini)
- Gmail integration (OAuth, lazy body loading, daily email report + meeting detection)
- Schedule management (create/update/delete, duration support)
- Google Calendar sync (background, create/update/delete events)
- DB-backed caching for email lists and AI outputs
- Simple web frontend (vanilla JS) with polling for background sync

## Quickstart (development)

Prerequisites
- Python 3.10+ (recommended)
- Git
- Google Cloud project with OAuth credentials (if you want Gmail/Calendar features)

1. Create virtualenv and install deps

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Configuration
- Copy or edit `backend/config.py` or provide environment variables. Important settings:
	- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` (or provide credentials JSON via `GMAIL_CREDENTIALS_JSON`)
	- `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `MISTRAL_API_KEY`, `CLAUDE_API_KEY`, `GEMINI_API_KEY` as available
	- `API_HOST`/`API_PORT` (defaults: 127.0.0.1:5000)

For local OAuth testing you can allow insecure transport (already set in development app). In production use HTTPS and set `OAUTHLIB_INSECURE_TRANSPORT` off.

3. Run the app

```powershell
# from repo root
python backend/app.py
```

Open http://127.0.0.1:5000 in your browser.

## Important endpoints
- `GET /api/health` — health check
- `GET /api/status` — providers & config status
- Email: `/api/email/*` (auth, list, `get-email-body/<id>`, `summarize-by-date`)
- Chat: `/api/chat/*` (send message, summarize, generate reply)
- Schedule: `/api/schedule/*` (create, list, upcoming, update, delete)
- Background sync: internal `POST /api/_background/sync-schedule` (used by server)

## Data & tokens
- Global DB: `data/assistant.db`
- Per-user DBs: `data/users/<sanitized_user_id>.db` (schedules, history, cache)
- Gmail token files: stored under `data/users/gmail_token_<user>.pickle`

## Development notes
- Email bodies are lazy-loaded to reduce API usage. Caching is DB-backed (`backend/models/cache.py`).
- AI responses are cached per-user (DB) to reduce repeated calls and cost.
- Calendar sync is performed in a background thread; for production consider a durable queue (Redis + RQ or Celery).

## Mobile / PWA
You can package the frontend as a PWA and wrap with Capacitor for quick mobile apps, or build a native app (React Native / Flutter) that calls the same REST API. See `backend/routes/email.py` for OAuth details — mobile will need PKCE and a proper redirect URI (custom scheme or App Link).

## Testing tips
- Health: `curl http://127.0.0.1:5000/api/health`
- Status: `curl http://127.0.0.1:5000/api/status`
- Create schedule (example):

```powershell
curl -X POST http://127.0.0.1:5000/api/schedule/create -H "Content-Type: application/json" -d '{"title":"Test","start_time":"2026-05-22T10:00:00","duration_minutes":60}'
```

## Deploy / production recommendations
- Use HTTPS and secure cookie/session configuration.
- Replace thread-based background sync with a durable worker (Redis/RQ, Celery) for reliability.
- Store credentials and secrets in a secure store (Vault, environment variables, or cloud secret manager).
- Add monitoring & alerts for AI provider failures or quota issues.

## License & contact
This is a private/internal project. For questions or next steps (mobile wrap, queue integration, CI/CD), ping the maintainer.

## Google Cloud Console (OAuth) setup
Follow these steps to configure Google APIs and obtain OAuth credentials for Gmail and Calendar integration.

1. Create a Google Cloud project
	- Go to https://console.cloud.google.com/ and create a new project (e.g., "EXE101").

2. Enable APIs
	- In the project dashboard, open "APIs & Services" → "Library" and enable:
	  - Gmail API
	  - Google Calendar API
	  - People API (optional, for profile info)

3. Configure OAuth consent screen
	- In "APIs & Services" → "OAuth consent screen":
	  - User Type: select "External" (or "Internal" if you have a Workspace account).
	  - App name, support email: fill with project info.
	  - Add scopes: at minimum include `../auth/gmail.readonly`, `../auth/calendar.events`, and `../auth/userinfo.email` or the specific scopes your app needs.
	  - Add test users if the app is not published.

4. Create OAuth credentials
	- In "APIs & Services" → "Credentials" → "Create Credentials" → "OAuth client ID".
	- Select application type:
	  - Web application: for the web frontend. Set **Authorized JavaScript origins** to `http://127.0.0.1:5000` (or your host) and **Authorized redirect URIs** to `http://127.0.0.1:5000/oauth2callback` and `http://localhost:5000/oauth2callback`.
	  - Desktop / Mobile: for local desktop testing or native/mobile apps, create separate credentials and use PKCE in the client.

5. Download credentials
	- Download the JSON credentials file and store it securely. You can either:
	  - Set environment variables: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`.
	  - Or place the JSON file and set `GMAIL_CREDENTIALS_JSON` to its contents or path (see `backend/config.py`).

6. Redirect URIs for mobile (PKCE)
	- For mobile apps, use a custom scheme redirect URI (e.g., `com.example.app:/oauth2redirect`) or the recommended platform-specific redirect for Android/iOS.
	- Make sure the OAuth client you create supports the chosen redirect type and that you implement PKCE on the client.

7. Testing the flow
	- Start the app and visit the Gmail auth endpoint (`/api/email/auth-url` or the UI button). Sign in with the test user and grant scopes.
	- Confirm that a token file appears under `data/users/` (e.g., `gmail_token_<user>.pickle`) and that `/api/status` shows `gmail_configured: true`.

Security notes
- Never commit OAuth client secrets or downloaded JSON to version control. Use environment variables or a secrets manager.
- For production, enforce HTTPS and verify redirect URIs precisely.

If you'd like, I can add a short `DEPLOY.md` with screenshots and sample values for the redirect URIs and environment variables.
