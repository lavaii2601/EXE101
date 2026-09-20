# FlowMate Mobile (Flutter)

Bản Flutter của ứng dụng FlowMate, song song với bản React Native ở
`../mobile`. Cả hai đều là client cho cùng một backend
(`web/backend`) — không có hai phiên bản dữ liệu tách biệt.

## Cấu trúc

- `lib/main.dart`: entry của ứng dụng.
- `lib/api/`: cấu hình API (`config.dart`) và HTTP client (`client.dart`).
- `lib/screens/`: các màn hình Chat, Email, Lịch, Work Hub, Cài đặt...
- `lib/state/`: `AppState` (phiên đăng nhập, đồng bộ đa thiết bị),
  `ThemeController`, `LanguageController`.
- `lib/theme/`, `lib/widgets/`: màu sắc/theme và UI component dùng lại.

## Chạy thử nhanh (cần Flutter SDK)

```powershell
cd mobile_flutter
flutter pub get
flutter run
```

Chọn thiết bị đích khi được hỏi (`flutter devices` để xem danh sách máy ảo/
thiết bị thật đang kết nối).

## Backend mặc định

Mặc định app trỏ thẳng tới backend FlowMate đã deploy trên Railway:

```text
https://flowmate.pro/api
```

Giá trị này được hardcode trong `lib/api/config.dart` (`kApiBase`) — **khác
với bản React Native**, bản Flutter chưa hỗ trợ override qua biến môi trường
lúc build. Muốn trỏ về backend local khi phát triển, sửa trực tiếp
`kApiBase` trong file đó (đừng commit lại giá trị local).

Nghĩa là: bất kỳ ai clone repo này và chạy `flutter run` đều tự động kết nối
vào backend production thật — không cần cấu hình gì thêm. Đăng ký tài khoản
mới qua email/mật khẩu hoặc đăng nhập Google đều hoạt động bình thường, vì
các endpoint đó không giới hạn theo domain/allowlist (khác với `/admin`, vốn
chỉ dành cho các email trong `ADMIN_EMAILS`).

## Build APK Android

Bản debug (cài thử nhanh, cần bật "Install from unknown sources" trên máy
Android):

```powershell
cd mobile_flutter
flutter build apk --debug
```

Bản release độc lập, không cần máy dev đứng cạnh:

```powershell
cd mobile_flutter
flutter build apk --release
```

APK được tạo tại:

```text
mobile_flutter/build/app/outputs/flutter-apk/app-release.apk
```

Bản release local hiện dùng debug keystore mặc định của Flutter, chỉ phù hợp
cài thử nghiệm/nội bộ — chia sẻ file `.apk` này cho người khác là đủ để họ
cài và dùng thử, không cần họ cài Flutter SDK. Muốn phát hành Play Store cần
cấu hình production keystore riêng, không dùng debug keystore.

## iOS

Chưa có project iOS native (`ios/`) cho bản Flutter lẫn bản React Native
trong repo này — build/chạy trên iOS hiện chưa được thiết lập.

## Đồng bộ với web

Giống hệt bản React Native (xem [`../mobile/README.md`](../mobile/README.md)
mục "Đồng bộ với web"): cùng Google identity, cùng PostgreSQL workspace,
cùng cơ chế polling `/api/sync/state?since=<revision>` khi app đang
foreground, cùng cơ chế `409` chống ghi đè khi web và app cùng sửa một
lịch/checklist.

## Chính sách bảo mật và điều khoản

```text
https://flowmate.pro/privacy
https://flowmate.pro/terms
```
