# FlowMate Mobile

Thu muc nay chua ung dung Expo/React Native cua FlowMate.

## Cau truc

- `App.js`: entry cua ung dung Expo.
- `src/api/`: cau hinh API va HTTP client.
- `src/components/`: UI components dung lai.
- `src/screens/`: cac man hinh Chat, Email, Calendar, Activity, Settings.
- `src/theme/`: mau sac va theme context.

Toan bo source mobile nam trong thu muc nay. Project Android native nam tai
`mobile/android`; khong con project Android rieng o thu muc `../app`. Project
native duoc commit de Android Studio va CI co the build Android truc tiep.

## Chay Expo

```powershell
cd mobile
npm install
npm start
```

Nhan `a` trong Expo CLI de mo app tren Android Emulator.

## Chay bang Android Studio

Mo truc tiep thu muc `mobile/android` bang Android Studio. Khi thay doi native
dependency hoac `app.json`, cap nhat project native:

```powershell
cd mobile
npx expo prebuild --platform android
```

Trong Android Studio chon **File > Open** va mo `mobile/android`. Android Studio
se nhan module `app` sau khi Gradle Sync hoan tat.

Build APK debug tu command line:

```powershell
cd mobile/android
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
.\gradlew.bat assembleDebug
```

APK duoc tao tai:

```text
mobile/android/app/build/outputs/apk/debug/app-debug.apk
```

Build APK release chay doc lap, khong can Metro:

```powershell
cd mobile/android
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
$env:NODE_ENV='production'
.\gradlew.bat assembleRelease
```

APK release duoc tao tai:

```text
mobile/android/app/build/outputs/apk/release/app-release.apk
```

Ban release local hien dung debug keystore, chi phu hop cai thu nghiem/noi bo.
De phat hanh Play Store, dung EAS profile `production` ben duoi hoac cau hinh
production keystore rieng; khong phat hanh bang debug keystore.

## Tao APK Android

Ban cai thu nghiem dung profile `preview` de EAS tra ve file `.apk` cai truc tiep:

```powershell
cd mobile
npx eas-cli build --platform android --profile preview
```

Ban phat hanh Play Store dung profile `production` va tao Android App Bundle (`.aab`):

```powershell
npx eas-cli build --platform android --profile production
```

Mac dinh mobile dung backend Railway:

```text
https://exe101.up.railway.app/api
```

Khi can test backend local, dat `EXPO_PUBLIC_API_BASE_URL` truoc khi chay Expo:

- Android emulator:

```powershell
$env:EXPO_PUBLIC_API_BASE_URL='http://10.0.2.2:5000/api'
npm start
```

- Thiet bi that:

```powershell
$env:EXPO_PUBLIC_API_BASE_URL='http://192.168.1.20:5000/api'
npm start
```

## Dong bo voi web

Mobile dung cung backend `web/backend` va cac endpoint chinh voi web:

- Chat: `/api/chat/*`
- Email/Gmail: `/api/email/*`
- Lich: `/api/schedule/*`
- Google Calendar: `/api/calendar/*`

Lich tren mobile dang dung che do local-first de mo nhanh:

- `/schedule/unified?live=0`
- `/schedule/week?sync=0`

Google Calendar van duoc backend sync nen trong nen man hinh khong bi chan boi
network cham.

## Chính sách bảo mật và điều khoản

APK trỏ người dùng đến chính sách bảo mật và điều khoản public của bản Railway:

```text
https://exe101.up.railway.app/privacy
https://exe101.up.railway.app/terms
```

Các URL này dùng cho Google OAuth consent screen, Play Console privacy policy
và terms of service.
