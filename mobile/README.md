# FlowMate AI Mobile

Ung dung mobile cho project FlowMate AI. Thu muc nay co 2 ban:

- `android/`: app Android native de mo truc tiep bang Android Studio.
- Cac file Expo/React Native cu van duoc giu lai neu can chay bang Expo.
- Ban Android native co tab duoi man hinh kem icon: Hoi AI, Hop thu, Lich hen, Nhat ky.

## Tinh nang co ban

- Chat voi AI va nhan goi y tao lich.
- Xem lich su hoat dong, xoa lich su.
- Gmail: dang nhap OAuth, xem inbox, loc email, hien email da doc, xem chi tiet, tom tat email.
- Hop thu quet toi da 70 email moi lan, chi tai metadata de danh sach mo nhanh.
- Moi email co 2 cach xem: noi dung day du hoac ban tom tat AI co cau truc.
- Noi dung day du va tom tat AI duoc cache de lan mo sau nhanh hon.
- Soan va gui email qua Gmail API.
- Tao bao cao email theo ngay va tao lich tu goi y hop.
- Lich: xem lich sap toi, tao lich hen, cap nhat trang thai, xoa lich.
- Google Calendar: xem va xoa su kien sap toi.

## Cai dat

### Android Studio

1. Mo Android Studio.
2. Chon `Open`.
3. Chon thu muc `mobile/android`.
4. Cho Gradle sync va cai Android SDK 35 neu Android Studio yeu cau.
5. Run app tren emulator Android.

Backend Flask can chay truoc:

```powershell
python backend/app.py
```

Android emulator dung san URL `http://10.0.2.2:5000/api`.

Neu chay tren dien thoai that, vao man Email trong app va sua `Backend API` thanh IP may tinh, vi du:

```text
http://192.168.1.20:5000/api
```

Backend nen chay bang host co the truy cap tu dien thoai:

```powershell
$env:API_HOST='0.0.0.0'
python backend/app.py
```

### Expo

```powershell
cd mobile
npm install
npm start
```

Chay backend Flask truoc:

```powershell
python backend/app.py
```

## Cau hinh API

File API nam tai `src/api/config.js`.

- Android emulator mac dinh dung `http://10.0.2.2:5000/api`.
- iOS simulator va web dung `http://127.0.0.1:5000/api`.
- Expo Go tren dien thoai that can doi thanh IP may tinh, vi du:

```js
export const API_BASE = 'http://192.168.1.20:5000/api';
```

## Gmail va Google Calendar tren mobile

Backend web luu token Gmail theo user id la dia chi Gmail da duoc sanitize. Mobile gui header `X-User-Id` de dung lai token do.

Quy trinh de test nhanh:

1. Mo web app va dang nhap Gmail mot lan, hoac bam Dang nhap trong mobile de mo OAuth.
2. Trong man Email cua mobile, nhap dung dia chi Gmail da ket noi vao o "Gmail da ket noi tren backend".
3. Bam "Dung tai khoan nay".
4. Inbox, gui email va Calendar se dung token da luu tren backend.

Neu backend chua co token cho Gmail do, cac endpoint Gmail/Calendar se bao chua dang nhap.
