# QUICKSTART

Hướng dẫn nhanh để cài và chạy project trên môi trường development (Windows - PowerShell).

Yêu cầu:
- Python 3.10+ installed
- Git

1) Clone repo (nếu chưa có)

```powershell
git clone https://github.com/lavaii2601/EXE101.git
cd EXE101
cd testing-local-deploy-version
```

2) Tạo virtualenv và cài dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

3) Tạo file cấu hình môi trường

Copy file mẫu và chỉnh giá trị thực tế (không commit file `.env` chứa secret).

```powershell
Copy-Item .env.example .env
# Mở .env và thêm giá trị của bạn, ví dụ GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, OPENROUTER_API_KEY, v.v.
notepad .env
```

Mẫu `.env.example` (ví dụ):

```
FLASK_ENV=development
SECRET_KEY=change-me
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
OPENROUTER_API_KEY=
OPENAI_API_KEY=
```

4) Chạy ứng dụng (development)

```powershell
python web/backend/app.py
```

Mở trình duyệt: http://127.0.0.1:5000

5) Kiểm tra server

```powershell
curl http://127.0.0.1:5000/api/health
curl http://127.0.0.1:5000/api/status
```

6) OAuth (Gmail/Calendar)
- Nếu bạn cần Gmail/Calendar, làm theo phần Google OAuth trong `README.md` để tạo Client ID/Secret và đặt vào `.env`.

7) Lưu ý bảo mật
- Không lưu `data/` hoặc file token (`*.pickle`) trong Git. `.gitignore` đã loại trừ các tệp này.
- Nếu bạn đã lỡ commit secrets, hãy rotate/revoke keys ngay (mình có thể hỗ trợ).

8) Chạy ở production (gợi ý)
- Dùng HTTPS, đặt Flask vào WSGI server (Gunicorn/uvicorn), và chuyển background jobs sang hàng đợi (Redis + RQ/Celery).

Nếu muốn, mình sẽ tạo `start.ps1` hoặc script Docker để tự động hoá các bước trên.
