# FlowMate AI

FlowMate AI là trợ lý năng suất đa nền tảng với trợ lý **Bob**, giúp người dùng
quản lý email, lịch, công việc và ngữ cảnh cá nhân trong một workspace thống
nhất. Ứng dụng hỗ trợ các chế độ Student, Worker, Freelancer, Creator,
Business, Mentor và Teacher.

Production: [https://exe101.up.railway.app](https://exe101.up.railway.app)

## Tính năng chính

- Chat với Bob bằng tiếng Việt, tiếng Anh hoặc code-switch trong cùng một câu;
  hỗ trợ trả lời song ngữ khi user yêu cầu.
- Hiểu câu nối tiếp theo đúng phiên như “đổi nó sang 4 giờ”, “the second one”
  và ưu tiên correction/negation mới nhất.
- Đọc, tìm kiếm, tóm tắt và soạn trả lời Gmail.
- Nhận diện email có nội dung hẹn gặp và đề xuất lịch.
- Tạo, cập nhật, xóa và đồng bộ lịch với Google Calendar.
- Overview tổng hợp email, lịch và việc cần chú ý.
- Web và APK dùng chung workspace PostgreSQL, tự phát hiện thay đổi theo tài
  khoản trong 10–15 giây và làm mới đúng màn hình đang mở.
- Chống ghi đè âm thầm khi web và APK cùng sửa một lịch hoặc checklist.
- AI Audit Log ghi lại các quyết định và hành động đã thực hiện.
- Knowledge/RAG và bộ dữ liệu huấn luyện theo từng user mode.
- Ứng dụng Expo/React Native cho Android, iOS và Web.
- Dashboard quản trị bảo vệ bằng Google allowlist và TOTP.
- Dashboard tài chính theo dõi subscription, doanh thu, phí, hoàn tiền và MRR.

## Kiến trúc

```text
EXE101/
├── web/
│   ├── backend/              Flask API, models, routes và AI services
│   └── frontend/             Landing page, web workspace và admin dashboard
├── mobile/                   Expo/React Native và Android native project
├── database/
│   ├── postgres_schema.sql   PostgreSQL schema đầy đủ
│   └── migrations/           Migration idempotent cho Railway
├── docs/bob-training/        Knowledge/RAG theo user mode
├── scripts/                  Deploy schema và import training corpus
└── tests/                    Unit và integration tests
```

Backend sử dụng:

- PostgreSQL khi có `DATABASE_URL` — cấu hình production trên Railway.
- SQLite làm fallback khi phát triển local.

## Chạy local

### Yêu cầu

- Python 3.10+
- Node.js và npm
- Git
- Google OAuth credentials nếu sử dụng Gmail/Calendar

### 1. Cài backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Cấu hình `web/.env`

Ví dụ tối thiểu:

```env
DEBUG=true
API_HOST=0.0.0.0
API_PORT=5000
SECRET_KEY=development-only-change-me
SESSION_COOKIE_SECURE=false
ALLOWED_ORIGINS=http://localhost:5000,http://127.0.0.1:5000

OPENROUTER_API_KEY=
AI_MAX_CONTEXT_MESSAGES=10
AI_MAX_INPUT_CHARS=12000
AI_MAX_SYSTEM_PROMPT_CHARS=8000

GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_CREDENTIALS_JSON=
GMAIL_REDIRECT_URI=http://127.0.0.1:5000/api/email/oauth2callback

# Chỉ cần khi kiểm tra admin dashboard local.
ADMIN_EMAILS=admin@example.com
ADMIN_TOTP_SECRET=
```

Không commit `.env`, OAuth credentials, API key, database URL hoặc TOTP secret.

### 3. Khởi động backend

```powershell
python web/backend/app.py
```

Hoặc dùng script thiết lập tự động:

```powershell
.\setup-and-run.ps1
```

Các URL local:

- Landing page: <http://127.0.0.1:5000>
- Web workspace: <http://127.0.0.1:5000/app>
- Admin: <http://127.0.0.1:5000/admin>
- Health check: <http://127.0.0.1:5000/api/health>

### 4. Khởi động mobile

```powershell
cd mobile
npm install
npm start
```

Android Emulator gọi backend trên máy host bằng:

```powershell
$env:EXPO_PUBLIC_API_BASE_URL='http://10.0.2.2:5000/api'
npm start
```

Xem thêm hướng dẫn APK/EAS trong [mobile/README.md](mobile/README.md).

## API chính

| Nhóm | Endpoint |
|---|---|
| Trạng thái | `GET /api/health`, `GET /api/status` |
| Chat/Bob | `/api/chat/*` |
| Gmail | `/api/email/*` |
| Lịch nội bộ | `/api/schedule/*` |
| Google Calendar | `/api/calendar/*` |
| Overview | `/api/overview/*` |
| User profile | `/api/user/*` |
| Đồng bộ web/APK | `GET /api/sync/state?since=<revision>` |
| Knowledge/RAG | `/api/knowledge/*` |
| Admin | `/api/admin/*` |

Các API nghiệp vụ yêu cầu session Google hoặc Bearer token hợp lệ. API admin
luôn kiểm tra lại Google allowlist và TOTP.

### Đồng bộ web và APK

Web và APK không giữ hai bản dữ liệu riêng. Cùng một Google identity được ánh
xạ tới một `user_id` bất biến và mọi dữ liệu nghiệp vụ được cô lập theo
`user_id` trong PostgreSQL. Sau một mutation thành công, backend tăng một
revision toàn cục cùng revision của các domain bị ảnh hưởng (`email`,
`schedule`, `chat`, `overview`, `profile`, ...).

Hai client chỉ poll endpoint trạng thái nhẹ khi đang foreground/visible. Khi
revision đổi, client chỉ đọc lại tab liên quan; tín hiệu từ Calendar không tự
gọi lại Google sync nên không tạo vòng lặp. Lịch và checklist gửi revision lúc
sửa, backend trả `409` nếu một client khác đã lưu trước.

Theme và ngôn ngữ hiển thị vẫn là tùy chọn cục bộ của từng thiết bị. User mode,
profile, chat, history, email state, lịch và checklist là dữ liệu workspace
dùng chung.

## Admin dashboard

Dashboard production:

```text
https://exe101.up.railway.app/admin
```

Railway cần có:

```env
ADMIN_EMAILS=owner@example.com
ADMIN_TOTP_SECRET=<base32-secret>
ADMIN_TOTP_SESSION_SECONDS=28800
SESSION_COOKIE_SECURE=true
```

Tạo TOTP secret:

```powershell
python -c "import base64,secrets; print(base64.b32encode(secrets.token_bytes(20)).decode().rstrip('='))"
```

Thêm secret vào Google Authenticator, Authy hoặc 1Password dưới dạng khóa
time-based. `SESSION_COOKIE_SECURE` phải là `true` trên Railway HTTPS và chỉ nên
là `false` khi chạy local bằng HTTP.

Dashboard có hai khu vực:

- **Tổng quan:** người dùng, Google OAuth, lịch, hoạt động, sync jobs và dung
  lượng PostgreSQL.
- **Tài chính & Subscription:** doanh thu gộp, phí, hoàn tiền, thực thu ước
  tính, active/trial/past-due subscription, MRR, biểu đồ 12 tháng và giao dịch
  gần đây.

Số liệu tài chính được tách theo currency. `Thực thu ước tính` được tính bằng
`doanh thu gộp - phí - hoàn tiền`; đây không phải xác nhận tiền đã settlement
về ngân hàng.

Hai bảng nguồn là:

- `subscriptions`
- `payment_transactions`

Dashboard không tạo số liệu giả. Cần tích hợp webhook hoặc một billing process
đáng tin cậy từ Stripe, MoMo, VNPay hoặc nhà cung cấp khác để ghi dữ liệu vào
hai bảng này.

## PostgreSQL và migration

Schema gốc nằm tại [database/postgres_schema.sql](database/postgres_schema.sql).
Các thay đổi production nằm trong [database/migrations](database/migrations).

Các bảng nền tảng cho đồng bộ đa client:

- `user_identities`: ánh xạ Google subject bất biến, tránh va chạm giữa các
  email có dấu câu khác nhau.
- `workspace_sync_state`: cursor revision theo user và domain.
- `oauth_tokens`: nguồn chuẩn credential dùng chung giữa các Railway worker;
  pickle trên filesystem chỉ là cache cục bộ.

Railway chạy lệnh sau trước khi khởi động Gunicorn:

```text
python scripts/deploy_postgres_schema.py
```

Script áp dụng schema/migration theo cách idempotent rồi mới khởi động backend.
Migration tài chính hiện tại:

```text
database/migrations/20260724_admin_finance.sql
```

Không đưa `DATABASE_URL` vào source code. Railway PostgreSQL cung cấp biến này
trực tiếp cho service.

## Deploy Railway

Các biến production quan trọng:

```env
DEBUG=false
SECRET_KEY=<long-random-secret>
SESSION_COOKIE_SECURE=true
ALLOWED_ORIGINS=https://exe101.up.railway.app
DATABASE_URL=<railway-postgres-reference>

GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_CREDENTIALS_JSON=

ADMIN_EMAILS=
ADMIN_TOTP_SECRET=

AI_MAX_CONTEXT_MESSAGES=10
AI_MAX_INPUT_CHARS=12000
AI_MAX_SYSTEM_PROMPT_CHARS=8000
```

`railpack.json` tự chạy migration và Gunicorn. Chi tiết đầy đủ nằm trong
[RAILWAY.md](RAILWAY.md).

## Google OAuth

Trong Google Cloud Console:

1. Bật Gmail API và Google Calendar API.
2. Tạo OAuth Client ID loại Web application.
3. Thêm local origins:
   - `http://127.0.0.1:5000`
   - `http://localhost:5000`
4. Thêm redirect URI:
   - `http://127.0.0.1:5000/api/email/oauth2callback`
   - `http://localhost:5000/api/email/oauth2callback`
   - `https://exe101.up.railway.app/api/email/oauth2callback`
5. Thêm tài khoản test nếu OAuth consent screen vẫn ở chế độ Testing.

Endpoint kiểm tra cấu hình production:

```text
https://exe101.up.railway.app/api/email/oauth-config-check
```

## Training Bob

Bob sử dụng knowledge/RAG thay vì fine-tune trọng số model trong repository.
Khả năng Việt–Anh/code-switch và hiểu follow-up được triển khai ở ba lớp:
language policy luôn có trong system prompt, intent contextualizer dùng lịch sử
đúng chat session, và corpus semantic pair Việt–Anh. Câu hiện tại vẫn có ưu
tiên cao nhất; lịch sử chỉ dùng để giải tham chiếu, không được xem như lệnh mới.

Import corpus:

```powershell
python scripts/train_bob.py .\docs\bob-training --tags "noi-bo,quy-tac,bob"
```

Xem trước mà không ghi database:

```powershell
python scripts/train_bob.py .\docs\bob-training --dry-run
```

Railway chỉ import lại corpus khi fingerprint của tài liệu training thay đổi.

## Kiểm thử

Chạy toàn bộ test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Kiểm tra JavaScript admin:

```powershell
node --check web/frontend/js/admin.js
node --check web/frontend/js/app.js
```

## Bảo mật

- Không commit API key, OAuth token, TOTP secret hoặc database credentials.
- Production phải sử dụng HTTPS và `SESSION_COOKIE_SECURE=true`.
- Admin yêu cầu đồng thời Google allowlist và TOTP.
- API responses chứa dữ liệu người dùng đặt `Cache-Control: no-store`.
- OAuth token production được lưu trong PostgreSQL.
- Worker Railway luôn đối chiếu PostgreSQL trước khi dùng credential cục bộ;
  token đã đổi/thu hồi sẽ vô hiệu cache Gmail và Calendar.
- Nếu credential từng được gửi qua chat, log hoặc issue, hãy rotate ngay.

Chính sách công khai:

- [Privacy Policy](https://exe101.up.railway.app/privacy)
- [Terms of Service](https://exe101.up.railway.app/terms)
