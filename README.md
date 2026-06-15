# EXE101

Trợ lý nhỏ cho giáo viên: tự động đọc email, tạo lịch và đồng bộ Google Calendar.

Mục tiêu chính
- Đọc email (Gmail) — chỉ tải nội dung đầy đủ khi cần (lazy load).
- Chat với AI để tóm tắt email hoặc đề xuất tạo lịch.
- Quản lý lịch (tạo, sửa, xoá) và đồng bộ với Google Calendar ở chế độ nền.

Cấu trúc thư mục
- `web/` — backend Flask (`web/backend`) + frontend web (`web/frontend`), dữ liệu (`web/data`) và `web/.env`.
- `app/` — ứng dụng Android native (TeacherBot) gọi API của `web/backend`.
- `mobile/` — ứng dụng Expo/React Native (FlowMate AI), cũng gọi API của `web/backend`.

Liên kết web <-> app
- `app` và `mobile` gọi backend qua URL cấu hình sẵn cho máy ảo Android: `http://10.0.2.2:5000/api`
  (mặc định trong `app/app/src/main/java/com/exe101/teacherbot/ApiClient.java` và `mobile/src/api/config.js`).
- Trên thiết bị thật, đổi URL này thành `http://<IP-máy-chạy-backend>:5000/api`.

Nhanh: cài và chạy (development)

Yêu cầu trước
- Python 3.10+, Git
- Nếu dùng Gmail/Calendar: tạo project trên Google Cloud để lấy OAuth credentials

1) Tạo môi trường và cài thư viện

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) Cấu hình
- Chỉnh `web/backend/config.py` hoặc đặt biến môi trường như `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `OPENROUTER_API_KEY`,... tùy bạn dùng dịch vụ nào (đọc từ `web/.env`).

3) Chạy ứng dụng

```powershell
python web/backend/app.py
```

Mở http://127.0.0.1:5000

Một số endpoint thường dùng
- `GET /api/health` — kiểm tra chạy
- `GET /api/status` — xem AI provider và Gmail đã cấu hình chưa
- Email: `/api/email/*` (lấy danh sách, lấy nội dung email theo id)
- Chat: `/api/chat/*` (gửi câu hỏi, tạo tóm tắt)
- Lịch: `/api/schedule/*` (tạo, liệt kê, sửa, xóa)

Dữ liệu & token
- DB chính: `web/data/assistant.db`
- DB người dùng: `web/data/users/<user>.db`
- Token Gmail lưu dưới `web/data/users/gmail_token_<user>.pickle`

Ghi chú phát triển
- Nội dung email tải khi cần để giảm số lần gọi API.
- Kết quả AI được cache (DB) để giảm chi phí.
- Đồng bộ Calendar chạy ở background (hiện là thread nhẹ). Nên dùng hàng đợi (Redis/Celery) khi vào production.

Cách nhanh test

```powershell
curl http://127.0.0.1:5000/api/health
curl http://127.0.0.1:5000/api/status
curl -X POST http://127.0.0.1:5000/api/schedule/create -H "Content-Type: application/json" -d '{"title":"Test","start_time":"2026-05-22T10:00:00","duration_minutes":60}'
```

Google OAuth (tóm tắt nhanh)
1. Tạo project trên https://console.cloud.google.com/
2. Bật API: Gmail API, Google Calendar API, (People API nếu cần)
3. OAuth consent screen: đặt tên app, thêm scope cơ bản, thêm test users nếu cần
4. Tạo OAuth Client ID (Web app) — thêm `http://127.0.0.1:5000` vào Authorized origins và `http://127.0.0.1:5000/oauth2callback` vào redirect URI
5. Lưu client ID/secret an toàn (không commit lên git)

