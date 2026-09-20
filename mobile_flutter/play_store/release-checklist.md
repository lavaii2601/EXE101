# Google Play release checklist

## Completed in source

- [x] Canonical production API URL, HTTPS, and Android Internet permission.
- [x] Unique package/application ID: `pro.flowmate.app`.
- [x] App label: `FlowMate AI`.
- [x] Target/compile SDK 36 through Flutter 3.47.1.
- [x] Release signing configuration rejects a missing production upload key.
- [x] Version bumped to `1.0.1+2`.
- [x] In-app permanent account deletion with a public deletion page.
- [x] External SEPay purchase flow disabled by default for Play builds.
- [x] Privacy and Terms public URLs.
- [x] Store listing drafts, 512×512 icon, and 1024×500 feature graphic.
- [x] Three real 1080×2400 phone screenshots (welcome, login, registration).
- [x] Offline Poppins fonts and branded native/Flutter startup screens.
- [x] Android backup disabled, cleartext traffic blocked, and deep-link hosts restricted.
- [x] Reused HTTPS connection pool and cold-start Google OAuth callback recovery.

## Requires the production/Play/OAuth account owner

- [ ] Review and deploy the pending backend/frontend changes to Railway, then
      verify `https://www.flowmate.pro/account-deletion` shows the dedicated
      deletion page and test deletion with a disposable production account.
- [ ] Confirm `pro.flowmate.app` before the first upload; it becomes permanent.
- [ ] Create and securely back up the upload keystore and passwords.
- [ ] Create the Play Console app and pay/verify the developer account.
- [ ] Enable Play App Signing and retain its SHA-1/SHA-256 certificates.
- [ ] After receiving the Play App Signing certificate, migrate the OAuth
      callback to a verified HTTPS App Link and publish `assetlinks.json` to
      remove the remaining custom-scheme interception risk.
- [ ] Complete App content: Data Safety, ads, target audience, content rating,
      app access, privacy policy, and account-deletion URL.
- [ ] Create a stable reviewer account and fill in `review-access.md` privately.
- [ ] Review the supplied screenshots and optionally add authenticated feature
      screens after creating the stable reviewer account.
- [ ] Complete Google OAuth brand/scope verification and any required CASA
      assessment for restricted Gmail scopes.
- [ ] If the developer account is subject to the rule, keep at least 12 closed
      testers opted in continuously for 14 days, then request Production access.
- [ ] Upload the signed AAB to Internal testing, run the pre-launch report, fix
      blockers, then promote through Closed testing to Production.

## Product decision deferred

The Play build is consumption-only for Premium today. To sell Premium inside
the Play build, implement Google Play Billing plus server-side purchase-token
verification and subscription lifecycle notifications before enabling a buy
button. Do not restore the SEPay link in the Play artifact.
