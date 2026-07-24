# Railway Deployment

Railway/Railpack deploys from the repository root, while the Flask app lives in
`web/backend/app.py`. The `railpack.json` file applies the PostgreSQL schema and
migrations automatically before starting Gunicorn.

## Required variables

Set these in Railway **Variables**. Do not rely on `web/.env`; Railway does not
read your local file.

```env
DEBUG=false
SECRET_KEY=change-this-to-a-long-random-value
SESSION_COOKIE_SECURE=true
ALLOWED_ORIGINS=https://exe101.up.railway.app
SCHEDULE_FULL_SYNC_DAYS=90
POSTGRES_POOL_MIN=1
POSTGRES_POOL_MAX=8

GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_CREDENTIALS_JSON=

# Admin dashboard: both values are required (Google allowlist + TOTP MFA).
ADMIN_EMAILS=owner@example.com
ADMIN_TOTP_SECRET=
# Optional: require a new TOTP after 8 hours.
ADMIN_TOTP_SESSION_SECONDS=28800

# Optional Outlook / Microsoft Graph provider
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT=common
MICROSOFT_REDIRECT_URI=https://exe101.up.railway.app/api/outlook/oauth2callback
MICROSOFT_SCOPES=openid profile email offline_access User.Read Mail.Read Calendars.Read
```

You can use either:

- `GMAIL_CLIENT_ID` plus `GMAIL_CLIENT_SECRET`
- or `GMAIL_CREDENTIALS_JSON` with the full Google OAuth client JSON on one line

After changing variables, redeploy the Railway service.

Google OAuth tokens are persisted in PostgreSQL (`oauth_tokens`) and cached in
the Railway container only at runtime. If users connected Google before the
database-backed token persistence shipped, ask them to reconnect Google once
after redeploy so the token can be stored durably.

On each deploy, `python scripts/deploy_postgres_schema.py` runs first. It is
idempotent: existing tables/data are preserved, and only missing schema pieces
or safe migrations are applied.

Bob's knowledge corpus is synchronized by content fingerprint. A deploy imports
the corpus only when the checked-in `docs/bob-training/modes/*.json` files have
changed, then stores a manifest row in PostgreSQL. Later deploys with the same
fingerprint skip the import, avoiding repeated startup delays. Set
`IMPORT_BOB_TRAINING_ON_DEPLOY=true` only when a full refresh must be forced.

To verify the deployed service can see the variables, open:

```text
https://exe101.up.railway.app/api/email/oauth-config-check
```

The response should show `has_client_id: true` and `has_client_secret: true`,
or `has_credentials_json: true`.

## Admin dashboard

The server operations dashboard is available at:

```text
https://exe101.up.railway.app/admin
```

It reports aggregate PostgreSQL usage, users, Google OAuth health, Calendar
events, schedules, activity, sync jobs, cache entries, and table sizes. Access
requires both:

- a signed-in Google account explicitly listed in `ADMIN_EMAILS`;
- a current six-digit TOTP from an authenticator app using
  `ADMIN_TOTP_SECRET`.

The dashboard fails closed when either variable is missing or invalid. There
is no first-user bootstrap and no single-header bypass.

Generate a Base32 TOTP secret locally:

```powershell
python -c "import base64,secrets; print(base64.b32encode(secrets.token_bytes(20)).decode().rstrip('='))"
```

Store that output only in Railway Variables as `ADMIN_TOTP_SECRET`, then add it
manually to Google Authenticator/Authy/1Password with issuer `FlowMate` and the
admin email as the account name. Never commit or paste the secret into source
files.

## Public privacy policy and terms

FlowMate serves public privacy and terms pages from the same Railway deployment:

```text
https://exe101.up.railway.app/privacy
https://exe101.up.railway.app/terms
```

Use these URLs for Google OAuth consent screen, Android APK review, Play Console
privacy policy, terms of service, and user-facing security/data handling
references.

## AI provider variables

Set at least one provider key. If none are set, the app starts in Demo Mode.

```env
OPENROUTER_ENABLED=true
OPENROUTER_API_KEY=
AI_PRIMARY_PROVIDER=openrouter
AI_PROVIDER_ORDER=openrouter,openai,mistral,claude,gemini
```

Optional provider keys:

```env
OPENAI_API_KEY=
MISTRAL_API_KEY=
CLAUDE_API_KEY=
GEMINI_API_KEY=
```

Optional web research and AI mentor learning:

```env
WEB_RESEARCH_ENABLED=true
WEB_RESEARCH_AUTO_LEARN_ENABLED=true
WEB_RESEARCH_LEARNING_MAX_PER_DAY=6

AI_MENTOR_LEARNING_ENABLED=true
AI_MENTOR_ALLOW_PRIVATE_CONTEXT=false
AI_MENTOR_PROVIDERS=openai,gemini,claude,openrouter,mistral,ollama
AI_MENTOR_MAX_PROVIDERS=2
AI_MENTOR_LEARNING_MAX_PER_DAY=6
```

`AI_MENTOR_ALLOW_PRIVATE_CONTEXT=false` keeps mentor learning away from turns
grounded in private email, calendar, history, or profile context unless you
explicitly choose to allow that data flow.
Web research is always available as live answer context; long-term learning
stores only curated lessons, not raw search result dumps.

## Google OAuth redirect URI

In Google Cloud OAuth Client, add:

```text
https://exe101.up.railway.app/api/email/oauth2callback
```

## Outlook / Microsoft OAuth redirect URI

Outlook is designed as an optional provider that users connect later from
Settings. Register a Microsoft Entra app and add this redirect URI:

```text
https://exe101.up.railway.app/api/outlook/oauth2callback
```

For local development, also add:

```text
http://127.0.0.1:5000/api/outlook/oauth2callback
```

Use delegated Microsoft Graph permissions. Start with read-only scopes:

```text
openid profile email offline_access User.Read Mail.Read Calendars.Read
```

Only add `Mail.Send` or `Calendars.ReadWrite` when FlowMate actually supports
sending Outlook mail or creating Outlook calendar events.

The implementation plan is documented in:

```text
OUTLOOK_RAILWAY_DESIGN.md
```
