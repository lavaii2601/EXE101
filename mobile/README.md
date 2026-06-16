# FlowMate Mobile

Thu muc nay chua ung dung Expo/React Native cua FlowMate.

## Cau truc

- `App.js`: entry cua ung dung Expo.
- `src/api/`: cau hinh API va HTTP client.
- `src/components/`: UI components dung lai.
- `src/screens/`: cac man hinh Chat, Email, Calendar, Activity, Settings.
- `src/theme/`: mau sac va theme context.

Android native rieng cua project nam trong thu muc `../app`. Thu muc
`mobile/android` neu duoc Expo tao ra khi prebuild la generated output va khong
duoc commit.

## Chay Expo

```powershell
cd mobile
npm install
npm start
```

Backend Flask can chay truoc tai `http://127.0.0.1:5000`.

Mac dinh:

- Android emulator dung `http://10.0.2.2:5000/api`.
- iOS simulator va web dung `http://127.0.0.1:5000/api`.
- Thiet bi that nen dat `EXPO_PUBLIC_API_BASE_URL`, vi du:

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
