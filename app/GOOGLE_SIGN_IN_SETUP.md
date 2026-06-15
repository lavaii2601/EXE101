# Google Sign-In Setup

Google error code `10` means the Android OAuth identity does not match the
installed APK.

In the Google Cloud project that owns the Web OAuth client configured in
`app/src/main/res/values/strings.xml`, create an OAuth client with:

- Application type: Android
- Android client ID: `307526067911-70k2adf2t48fi2bcdubd4hd6g4mnkodd.apps.googleusercontent.com`
- Google Cloud project: `exe101-498801`
- Package name: `com.exe101.teacherbot`
- SHA-1: `69:8C:F1:A4:A6:5D:38:A9:D6:54:4C:39:DE:8B:AE:87:B0:8E:93:20`

Do not use the Android client ID in `requestServerAuthCode`. That method must
use the Web client ID because the Flask backend exchanges the returned code.
Create that Web application client inside the same `exe101-498801` project,
then configure its client ID in `google_web_client_id` and its client ID/secret
for the Flask backend.

Current Web client ID:

`307526067911-rbdm9k0gqbjvbtqphogvmuo090chhlq9.apps.googleusercontent.com`

Also complete the OAuth consent screen, add the testing Google account as a
test user, and enable Gmail API, Google Calendar API, and People API.

After saving the client:

1. Wait a few minutes for Google configuration to propagate.
2. Uninstall the old app from the emulator.
3. Run the app again from Android Studio.
4. Tap **Login by Google**.

To print the SHA-1 again:

```powershell
cd D:\clone\EXE101\mobile\android
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
.\gradlew.bat signingReport
```

Release builds use a different signing certificate and need a separate Android
OAuth client with the release SHA-1.
