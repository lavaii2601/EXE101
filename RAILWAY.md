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
```

You can use either:

- `GMAIL_CLIENT_ID` plus `GMAIL_CLIENT_SECRET`
- or `GMAIL_CREDENTIALS_JSON` with the full Google OAuth client JSON on one line

After changing variables, redeploy the Railway service.

On each deploy, `python scripts/deploy_postgres_schema.py` runs first. It is
idempotent: existing tables/data are preserved, and only missing schema pieces
or safe migrations are applied.

To verify the deployed service can see the variables, open:

```text
https://exe101.up.railway.app/api/email/oauth-config-check
```

The response should show `has_client_id: true` and `has_client_secret: true`,
or `has_credentials_json: true`.

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

## Google OAuth redirect URI

In Google Cloud OAuth Client, add:

```text
https://exe101.up.railway.app/api/email/oauth2callback
```
