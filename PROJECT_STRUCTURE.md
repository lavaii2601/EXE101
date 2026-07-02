# Project Structure

FlowMate co 2 phan chinh dung chung backend Flask.

## Source directories

- `web/backend/`: Flask API, models, services, routes.
- `web/frontend/`: web UI tinh, duoc Flask serve truc tiep.
- `mobile/`: Expo/React Native app (Android/iOS/Web) - ban mobile duy nhat cua du an.
- `docs/bob-training/`: tai lieu training/RAG de nap vao knowledge base cua Bob.
- `database/`: PostgreSQL schema va migration.
- `scripts/`: script deploy schema va import training cho Bob.

## Runtime and generated directories

Cac thu muc/file sau khong commit:

- `.venv/`: Python virtual environment.
- `web/data/`: SQLite DB, Gmail token, cache runtime.
- `web/backend-local.pid`: PID cua backend local.
- `mobile/node_modules/`, `mobile/.expo/`, `mobile/dist/`, `mobile/android/`.
- `mobile/*.apk`: APK build artifact local.
- `__pycache__/`, `*.pyc`, `*.log`, `*.pid`.

## Dependency sources

- Python dependencies: `requirements.txt`.
- Expo dependencies: `mobile/package.json` va `mobile/package-lock.json`.

## API synchronization

Web va Expo mobile nen dung cung endpoint backend. Khi them tinh nang moi,
cap nhat theo thu tu:

1. Backend route/service/model trong `web/backend`.
2. Web client trong `web/frontend/js/app.js`.
3. Expo client trong `mobile/src`.
4. Neu la tinh nang Bob/agent, dong bo capability trong
   `web/backend/services/tool_catalog.py` va training trong `docs/bob-training`.

Lich nen uu tien local-first de UI nhanh:

- Week view: `/api/schedule/week?sync=0` neu chi can doc nhanh.
- Unified list: `/api/schedule/unified?live=0` neu khong can keo Google live.

Backend se sync Google Calendar trong nen khi can, tranh chan UI.
