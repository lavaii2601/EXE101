# FlowMate AI — Google Play release pack

Package ID: `pro.flowmate.app`

This folder contains the editable Play Store listing copy, policy declaration
drafts, reviewer instructions, and ready-sized graphic assets. The declarations
are evidence-based drafts; the Play Console account owner must verify and
submit them because they are legal/policy attestations.

`console-values.md` and the localized `release-notes-*.txt` files cover the
remaining copy-ready Play Console fields.

## Release build

1. Create the private upload keystore (once):

   ```powershell
   & 'C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe' -genkeypair -v `
     -keystore "$env:USERPROFILE\flowmate-upload.jks" `
     -storetype JKS -keyalg RSA -keysize 2048 -validity 10000 -alias upload
   ```

2. Copy `android/key.properties.example` to `android/key.properties` and fill
   in the passwords and keystore path. Both private files are gitignored.

3. Build the Play bundle (external SEPay checkout is disabled by default):

   ```powershell
   cd mobile_flutter
   D:\flutter\bin\flutter.bat clean
   D:\flutter\bin\flutter.bat pub get
   D:\flutter\bin\flutter.bat build appbundle --release
   ```

4. Upload `build/app/outputs/bundle/release/app-release.aab` to Internal testing.

Do not pass `--dart-define=ENABLE_EXTERNAL_PAYMENTS=true` to a Google Play
build. That switch exists only for separately distributed internal/direct APKs.

## Files that need owner action

- Deploy the reviewed backend/frontend changes to Railway before distributing
  the mobile build; the account-deletion endpoint and public page must be live.
- `review-access.md`: replace placeholders with a stable reviewer account.
- `data-safety.md`: confirm the draft against production before attesting.
- `release-checklist.md`: complete Play Console, OAuth verification, and tests.
- `assets/`: app icon, feature graphic, and three real phone screenshots are ready.
  Add authenticated feature screens later if you want a stronger store listing.
