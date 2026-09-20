// Same deployed backend the React Native app talks to -- there is only
// one FlowMate API, both clients are just different frontends for it.
// Use the canonical host directly. The apex domain redirects to `www` with
// HTTP 308; POST redirects are not handled consistently by native HTTP
// clients and caused login/register requests to fail before reaching Flask.
const String kApiBase = 'https://www.flowmate.pro/api';
const String kPrivacyUrl = 'https://www.flowmate.pro/privacy';
const String kTermsUrl = 'https://www.flowmate.pro/terms';
const String kAccountDeletionUrl = 'https://www.flowmate.pro/account-deletion';

// Google Play builds must not lead users to SEPay for digital Premium
// features. Direct/internal distributions can opt in explicitly with
// --dart-define=ENABLE_EXTERNAL_PAYMENTS=true.
const bool kExternalPaymentsEnabled = bool.fromEnvironment(
  'ENABLE_EXTERNAL_PAYMENTS',
  defaultValue: false,
);
