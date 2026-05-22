# UI Workspace — Designer Guide

This folder is the UI/UX workspace for designers. If you are a designer, you can safely clone this repository and only work inside the `ui/` directory to change the web UI (HTML/CSS/JS).

Goals
- Keep design work isolated from backend logic.
- Allow designers to preview UI locally without running the backend.
- Provide a simple sync step to copy final design into the runtime `frontend/` folder when ready.

Local preview (quick)
1. Open `ui/index.html` in your browser (double-click) — static preview.
2. Or run a local static server (recommended):

```powershell
# PowerShell
cd ui
python -m http.server 8000
# then open http://127.0.0.1:8000
```

Designer workflow
1. Edit files inside `ui/` (HTML/CSS/JS and assets).
2. Test in the browser and iterate.
3. When ready to update the running app, run the sync script from repo root:

PowerShell (Windows):
```powershell
.\scripts\sync-ui.ps1
```

macOS / Linux:
```bash
./scripts/sync-ui.sh
```

This will copy the content of `ui/` into `frontend/` (overwriting runtime frontend files). After syncing the developer or maintainer runs/tests the app.

Notes
- Do not edit `frontend/` directly if you are a designer — make changes in `ui/` and sync.
- If you are a developer, you can accept designer changes by reviewing and committing the synced files from `frontend/`.
