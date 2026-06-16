# Project Structure

FlowMate co 3 phan chinh dung chung backend Flask.

## Source directories

- `web/backend/`: Flask API, models, services, routes.
- `web/frontend/`: web UI tinh, duoc Flask serve truc tiep.
- `mobile/`: Expo/React Native app.
- `app/`: Android native app.
- `image/`: tai lieu hinh anh phuc vu README/quickstart.

## Runtime and generated directories

Cac thu muc/file sau khong commit:

- `.venv/`: Python virtual environment.
- `web/data/`: SQLite DB, Gmail token, cache runtime.
- `web/backend-local.pid`: PID cua backend local.
- `mobile/node_modules/`, `mobile/.expo/`, `mobile/dist/`, `mobile/android/`.
- `app/.gradle/`, `app/build/`, `app/app/build/`.
- `__pycache__/`, `*.pyc`, `*.log`, `*.pid`.

## Dependency sources

- Python dependencies: `requirements.txt`.
- Expo dependencies: `mobile/package.json` va `mobile/package-lock.json`.
- Android native dependencies: Gradle files trong `app/`.

## API synchronization

Web, Expo mobile va Android native nen dung cung endpoint backend. Khi them
tinh nang moi, cap nhat theo thu tu:

1. Backend route/service/model trong `web/backend`.
2. Web client trong `web/frontend/js/app.js`.
3. Expo client trong `mobile/src`.
4. Android native client trong `app/app/src/main/java`.

Lich nen uu tien local-first de UI nhanh:

- Week view: `/api/schedule/week?sync=0` neu chi can doc nhanh.
- Unified list: `/api/schedule/unified?live=0` neu khong can keo Google live.

Backend se sync Google Calendar trong nen khi can, tranh chan UI.
