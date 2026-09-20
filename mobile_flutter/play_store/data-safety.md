# Data Safety draft — owner must verify before submission

This is a technical inventory, not a completed legal attestation.

## Collection likely requiring declaration

| Play category | FlowMate examples | Purpose | Required/optional |
| --- | --- | --- | --- |
| Personal info | Name, email address, internal user ID, profile image | Account management, app functionality | Email/account required; profile fields optional |
| Emails | Gmail message metadata/content selected or fetched for inbox, summaries, replies | App functionality | Optional Google connection |
| Calendar | Google Calendar events and FlowMate schedules | App functionality | Optional Google connection |
| App activity | Chat prompts/responses, search queries, feature activity/history | App functionality, personalization, security | Core features |
| User-generated content | Projects, tasks, reports, checklist and workspace documents | App functionality | Optional by feature |
| Financial info | Subscription tier, transaction ID, amount, currency and payment status; no card/bank credentials stored by FlowMate | Account/subscription management | Only for paid users |
| Diagnostics/security | IP-derived rate-limit identity, request/correlation IDs, server error logs | Security, fraud prevention, reliability | Collected during requests |

## Sharing/processing destinations to verify

- Railway/PostgreSQL: hosting and durable storage.
- Google APIs: Gmail/Calendar functionality requested by the user.
- Public search/web sources: only when the user asks Bob to research the web.
- SEPay: not reachable from the Google Play build; may exist on web/direct builds.
- Confirm that no advertising, analytics, crash-reporting, or external LLM SDK
  has been added before selecting "not collected/shared" for those categories.

## Security and deletion answers supported by the implementation

- Data is encrypted in transit via HTTPS.
- Users can request deletion in-app.
- Public deletion URL: `https://www.flowmate.pro/account-deletion`.
- Privacy URL: `https://www.flowmate.pro/privacy`.
- The app contains no ads in the current source tree.
- Active account data is deleted on completion; Railway PITR disaster-recovery
  copies currently have an approximately four-week rolling retention window.

The Play Console owner must compare every answer with the deployed backend,
third-party contracts, retention/backups, and the exact production build.
