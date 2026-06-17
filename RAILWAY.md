# Railway Deployment

Railway/Railpack deploys from the repository root, while the Flask app lives in
`web/backend/app.py`. The `railpack.json` file sets the production start command.

## Required variables

Set these in Railway **Variables**. Do not rely on `web/.env`; Railway does not
read your local file.

```env
DEBUG=false
SECRET_KEY=change-this-to-a-long-random-value
SESSION_COOKIE_SECURE=true
ALLOWED_ORIGINS=https://exe101.up.railway.app

GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_CREDENTIALS_JSON=
```

You can use either:

- `GMAIL_CLIENT_ID` plus `GMAIL_CLIENT_SECRET`
- or `GMAIL_CREDENTIALS_JSON` with the full Google OAuth client JSON on one line

After changing variables, redeploy the Railway service.

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
