# Outlook on Railway Design

This document describes the target design for adding Outlook Mail and Calendar
as an optional provider in FlowMate while keeping the Email UI simple.

## Goals

- Outlook is optional and connected later from Settings.
- Email stays as one unified inbox, not separate Gmail and Outlook screens.
- Overview can summarize data from all connected providers.
- Railway deployment uses environment variables only, never local `.env` files.
- Gmail behavior remains unchanged while Outlook is introduced.

## External Setup

Create an app registration in Microsoft Entra admin center.

Recommended account support:

- Use `common` if you want both work/school accounts and personal Microsoft accounts.
- Use a tenant ID if you only want one organization.

Redirect URI for Railway:

```text
https://exe101.up.railway.app/api/outlook/oauth2callback
```

Redirect URI for local development:

```text
http://127.0.0.1:5000/api/outlook/oauth2callback
```

Use the OAuth 2.0 authorization code flow. Microsoft Graph calls should be made
from the Flask server after the token exchange, not from browser JavaScript.

## Railway Variables

Add these to Railway Variables:

```env
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT=common
MICROSOFT_REDIRECT_URI=https://exe101.up.railway.app/api/outlook/oauth2callback
MICROSOFT_SCOPES=openid profile email offline_access User.Read Mail.Read Calendars.Read
```

Future write features can add:

```env
# Only request these when the product actually sends mail or writes calendar events.
MICROSOFT_OPTIONAL_WRITE_SCOPES=Mail.Send Calendars.ReadWrite
```

## OAuth Flow

Server routes:

```text
GET  /api/outlook/auth-url
GET  /api/outlook/oauth2callback
GET  /api/outlook/auth-status
POST /api/outlook/logout
```

Flow:

1. User opens Settings.
2. User clicks "Connect Outlook".
3. Frontend requests `/api/outlook/auth-url`.
4. Server returns Microsoft authorize URL with state.
5. User consents on Microsoft.
6. Microsoft redirects to `/api/outlook/oauth2callback`.
7. Server exchanges authorization code for tokens.
8. Server stores token in `oauth_tokens` with `provider = 'microsoft'`.
9. Server redirects user back to Settings or posts OAuth success.

## Token Storage

Use the existing `oauth_tokens` table:

```text
provider = "microsoft"
account_email = Outlook account email
token_json = access token, refresh token, expiry, token type
scopes = granted scopes
expires_at = token expiry
```

This keeps provider connection state separate from email messages.

## Backend Modules

Add:

```text
web/backend/services/outlook_service.py
web/backend/routes/outlook.py
web/backend/services/email_provider_service.py
```

Register the Outlook blueprint in:

```text
web/backend/app.py
```

### OutlookService responsibilities

- Load and refresh Microsoft token.
- Call Microsoft Graph `/me`.
- List messages from `/me/messages`.
- Fetch one message from `/me/messages/{id}`.
- List calendar events from `/me/calendarView`.
- Normalize Outlook data to FlowMate's internal format.

Normalized email shape:

```json
{
  "provider": "outlook",
  "provider_label": "Outlook",
  "id": "outlook:<graph-message-id>",
  "external_id": "<graph-message-id>",
  "subject": "Project update",
  "sender": "Name <name@example.com>",
  "snippet": "Short preview",
  "body": "",
  "date": "2026-06-27T08:30:00Z",
  "is_unread": true,
  "tag": "work",
  "web_link": "https://outlook.office.com/..."
}
```

Normalized calendar event shape:

```json
{
  "provider": "outlook",
  "source": "outlook",
  "google_event_id": null,
  "outlook_event_id": "<graph-event-id>",
  "title": "Team meeting",
  "description": "",
  "start_time": "2026-06-27T09:00:00+07:00",
  "end_time": "2026-06-27T10:00:00+07:00",
  "location": "Teams",
  "attendees": ["a@example.com"],
  "html_link": "https://outlook.office.com/..."
}
```

## Unified Provider Service

`email_provider_service.py` should keep the Email UI clean.

Target server API:

```text
GET /api/email/unified?source=all|gmail|outlook&filter=all|meeting|work|...
GET /api/email/unified/<provider>/<message_id>
POST /api/email/unified/<provider>/<message_id>/summary
```

Behavior:

- `source=all`: merge Gmail and Outlook.
- `source=gmail`: Gmail only.
- `source=outlook`: Outlook only.
- Sort merged results by received date descending.
- Add `provider` and `provider_label` to every item.
- Keep old Gmail endpoints for backward compatibility while migrating UI.

## Outlook Calendar Integration

Outlook Calendar should be integrated through the same provider model as email.
The initial Outlook release uses read-only calendar access through:

```text
GET https://graph.microsoft.com/v1.0/me/calendarView
```

Required query parameters:

```text
startDateTime=<ISO datetime>
endDateTime=<ISO datetime>
```

Recommended Graph select fields:

```text
$select=id,subject,bodyPreview,start,end,location,attendees,webLink,lastModifiedDateTime,isCancelled
```

Server routes:

```text
GET /api/outlook/events?start=<iso>&end=<iso>
```

Schedule unified behavior:

```text
GET /api/schedule/unified
GET /api/schedule/week
POST /api/schedule/sync
```

should eventually include Outlook Calendar events when Outlook is connected.

Response flags:

```json
{
  "calendar_connected": true,
  "google_calendar_connected": true,
  "outlook_calendar_connected": true,
  "items": []
}
```

Normalized Outlook calendar item:

```json
{
  "provider": "outlook",
  "source": "outlook",
  "local_id": null,
  "outlook_event_id": "<graph-event-id>",
  "title": "Team meeting",
  "description": "Agenda preview",
  "start_time": "2026-06-27T09:00:00+07:00",
  "end_time": "2026-06-27T10:00:00+07:00",
  "location": "Microsoft Teams",
  "attendees": ["a@example.com"],
  "html_link": "https://outlook.office.com/..."
}
```

Read/write policy:

- With `Calendars.Read`, Outlook events are read-only in FlowMate.
- Show "Open event" instead of edit/delete for Outlook-only events.
- Only add `Calendars.ReadWrite` when FlowMate supports creating or deleting
  Outlook events from the app.

Storage:

- The existing `calendar_events` table already has a generic `provider` column.
- Store Outlook events with `provider = 'outlook'`.
- Use `external_event_id = Graph event id`.
- Keep `calendar_id = 'primary'` unless multi-calendar support is added.

## Settings UI

Settings should own provider connection management.

Connection card:

```text
Gmail & Google Calendar        Connected
Outlook Mail & Calendar        Connect
```

Outlook states:

- Not configured: "Outlook is not configured on this deployment."
- Not connected: "Connect Outlook"
- Connected: show account email and "Disconnect"
- Error: show recoverable OAuth/config error

## Email UI

Do not create separate Outlook pages.

Add source filter:

```text
All | Gmail | Outlook
```

Each email card gets a small badge:

```text
[Gmail] Weekly report
[Outlook] Team sync notes
```

Compose/reply rule:

- Reply to Gmail message defaults to Gmail sender.
- Reply to Outlook message defaults to Outlook sender.
- New compose requires a "Send from" selector once more than one sending
  provider is connected.

## Overview UI

Overview should call unified endpoints.

Data sources:

```text
Emails: Gmail + Outlook
Calendar: Google Calendar + Outlook Calendar
Tasks/deadlines: derived from unified email and unified calendar items
```

Show source summary quietly:

```text
Sources: Gmail, Google Calendar, Outlook
```

Do not split the main overview by provider. Split by priority:

- Deadlines
- Email needing attention
- Meetings
- Open tasks

## Mobile Parity

The mobile app should expose the same Outlook model as web.

Settings mobile:

- Add `Outlook Mail & Calendar` under service connections.
- Call `/api/outlook/auth-status` on screen load.
- Call `/api/outlook/auth-url` and open the returned URL with Expo WebBrowser.
- Call `/api/outlook/logout` to disconnect.
- If the endpoint is not deployed yet, show "Outlook is not configured on this deployment."

Email mobile:

- Keep one Email screen.
- Add source filter:

```text
Tất cả | Gmail | Outlook
```

- Prefer `/api/email/unified`.
- Fallback to the existing Gmail endpoint while the unified server endpoint is
  not available.
- Show small provider badges on every email card.

Overview mobile:

- Continue showing one daily overview.
- Display a quiet source line such as:

```text
Nguồn: Gmail, Google, Outlook
```

- Show provider badges beside individual email/calendar items only as metadata,
  not as separate sections.

Schedule mobile:

- Treat Outlook Calendar as a read-only external calendar until
  `Calendars.ReadWrite` is enabled.
- Show source badges: `FlowMate`, `Google`, `Outlook`.
- For Outlook-only events, show `Mở lịch` when `html_link` or `web_link` is
  available.
- Do not call the Google delete endpoint for Outlook events.

## Database Migration Later

The current schema has Gmail-specific message tables. For the first Outlook
release, avoid a large migration by fetching Outlook live or through the current
cache model.

When Outlook usage is stable, migrate toward generic tables:

```text
email_messages
email_attachments
email_summaries
email_daily_reports
```

Recommended generic key:

```text
UNIQUE (user_id, provider, external_message_id)
```

## Implementation Order

1. Add Microsoft config values to `Config`.
2. Add `routes/outlook.py` with auth-url, callback, status, logout.
3. Store Microsoft token in `oauth_tokens`.
4. Add `OutlookService` for `/me`, messages, and calendarView.
5. Add Settings Outlook card.
6. Add source filter and provider badges in Email UI.
7. Add `/api/email/unified` and point Overview to it.
8. Add Outlook Calendar into schedule unified data.
9. Add optional write scopes only when sending mail or creating Outlook events.

## References

- Microsoft OAuth authorization code flow: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow
- Microsoft redirect URI rules: https://learn.microsoft.com/en-us/entra/identity-platform/reply-url
- Microsoft Graph API usage and calendarView examples: https://learn.microsoft.com/en-us/graph/use-the-api
- Microsoft Graph Outlook mail overview: https://learn.microsoft.com/en-us/graph/outlook-mail-concept-overview
- Railway variables: https://docs.railway.com/variables
- Railway public networking and `$PORT`: https://docs.railway.com/public-networking
