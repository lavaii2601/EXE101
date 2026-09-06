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
WORKSPACE_SYNC_POLL_AFTER_MS=10000

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
the Railway container only at runtime. PostgreSQL is authoritative on every
credential acquisition: a token refreshed or revoked by one Gunicorn
worker/replica invalidates the local Gmail/Calendar service cache on another.
If users connected Google before database-backed token persistence shipped,
ask them to reconnect Google once after redeploy so the token can be stored
durably.

On each deploy, `python scripts/deploy_postgres_schema.py` runs first. It is
idempotent: existing tables/data are preserved, and only missing schema pieces
or safe migrations are applied.

Bob's knowledge corpus is synchronized by content fingerprint. A deploy imports
the corpus only when the checked-in `docs/bob-training/modes/*.json` files have
changed, then stores a manifest row in PostgreSQL. Later deploys with the same
fingerprint skip the import, avoiding repeated startup delays. Set
`IMPORT_BOB_TRAINING_ON_DEPLOY=true` only when a full refresh must be forced.

## Đồng bộ web và APK

Schema deploy tạo `user_identities` và `workspace_sync_state`. Google `sub`
được dùng làm identity bất biến, vì vậy web cookie và APK Bearer token cùng
trỏ vào một workspace dù email có dấu chấm/gạch dễ va chạm khi sanitize.

Mỗi mutation thành công tăng revision theo user và domain. Web và APK poll
`GET /api/sync/state?since=<revision>` chỉ khi visible/foreground, mặc định
10 giây và được client giới hạn trong khoảng 10–15 giây. Có thể điều chỉnh hint
bằng `WORKSPACE_SYNC_POLL_AFTER_MS`; không nên đặt quá thấp vì mỗi client đang
mở sẽ tạo một request đọc trạng thái theo chu kỳ.

Schedule và checklist dùng optimistic concurrency. HTTP `409` có nghĩa một
client khác đã lưu trước; client phải tải lại payload hiện tại thay vì retry
mù quáng. Remote `calendar` revision chỉ nên làm mới dữ liệu local hiện có,
không gọi lại `POST /api/schedule/sync`, để tránh vòng lặp revision giữa các
thiết bị.

To verify the deployed service can see the variables, open:

```text
https://exe101.up.railway.app/api/email/oauth-config-check
```

The response should show `has_client_id: true` and `has_client_secret: true`,
or `has_credentials_json: true`.

## Admin dashboard

The admin dashboard is web-only and is intentionally not part of the Android
APK bundle.

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

`/admin` redirects unverified visitors to the sign-in shell at `/admin/login`;
the shell contains no metrics, and every dashboard API request repeats the
allowlist + TOTP check. Gmail logout also clears the elevated admin session.

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

### Finance and subscription tab

The admin dashboard also exposes a **Finance & Subscription** tab backed by
the provider-neutral PostgreSQL tables `subscriptions` and
`payment_transactions`. Railway creates these tables automatically during the
next deploy.

The tab reports each currency separately and includes:

- monthly gross revenue, gateway fees, refunds, and estimated net revenue;
- active, trialing, past-due, new, and canceled subscriptions;
- normalized monthly recurring revenue (MRR);
- a 12-month revenue trend, plan distribution, recent payments, and recent
  subscriptions.

Amounts are stored as integers in each currency's smallest unit (VND = đồng,
USD = cents). Estimated net revenue is `gross - fees - refunds`; it must not be
treated as confirmation that a payment provider has settled funds to a bank
account.

The dashboard never fabricates billing data. Until a payment provider webhook
or another trusted billing process writes subscriptions and transactions into
the ledger, the finance tab displays a clear empty state with zero totals.

## Public privacy policy and terms

FlowMate serves public privacy and terms pages from the same Railway deployment:

```text
https://flowmate.pro/privacy
https://flowmate.pro/terms
```

Use these URLs for Google OAuth consent screen, Android APK review, Play Console
privacy policy, terms of service, and user-facing security/data handling
references.

## AI limitation on Railway

Railway does not provide GPU instances, so it is not a practical host for
`qwen3:8b`/Ollama inference. A Railway Volume can persist model files but does
not solve CPU/RAM inference cost or latency. In a strict no-hosted-AI setup,
the Railway deployment therefore runs Bob's deterministic tools, offline
classifier, and PostgreSQL RAG only. Full free-form generation requires moving
the backend and Ollama together to a GPU-capable machine where Ollama is
available on loopback.

```env
OPENROUTER_ENABLED=false
BOB_LOCAL_ONLY=true
OLLAMA_ENABLED=false
WEB_RESEARCH_ENABLED=false
AI_MAX_CONTEXT_MESSAGES=10
AI_MAX_INPUT_CHARS=12000
AI_MAX_SYSTEM_PROMPT_CHARS=12000
AI_AGENT_MAX_TOKENS=700
```

The three prompt-budget values keep Bob's current user turn, bilingual/context
policy, grounding rules, and bounded same-session history in the provider
payload. Do not restore the former `2800` / `450` limits: those values can cut
the intent prompt before the current request reaches the model.

Local knowledge on Railway:

```env
WEB_RESEARCH_ENABLED=false
WEB_RESEARCH_AUTO_LEARN_ENABLED=false
WEB_RESEARCH_LEARNING_MAX_PER_DAY=6

AI_MENTOR_LEARNING_ENABLED=false
AI_MENTOR_ALLOW_PRIVATE_CONTEXT=false
AI_MENTOR_LEARNING_MAX_PER_DAY=6
```

`WEB_RESEARCH_ENABLED=false` prevents public-web requests. The deploy script
imports trusted documents into PostgreSQL and the TF-IDF index retrieves them
without hosted AI APIs. On Railway there is no Ollama synthesis layer.

For full local-model behavior, deploy FlowMate on a GPU-capable host and use the
local configuration documented in `README.md`; do not point Railway at
`127.0.0.1:11434`, because that address refers to the Railway container itself.

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
