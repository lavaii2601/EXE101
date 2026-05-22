<#
Start development server for EXE101 (Windows PowerShell)

What it does:
- Create and activate `.venv` if missing
- Install `requirements.txt` if missing packages
- Create `.env` from `.env.example` if `.env` not present
- Set `FLASK_ENV=development` and run `backend/app.py`

Usage:
  .\start.ps1
#>

$ErrorActionPreference = 'Stop'

Write-Host "Starting EXE101 development environment..."

if (-not (Test-Path -Path ".venv")) {
    Write-Host "Creating virtual environment .venv..."
    python -m venv .venv
}

Write-Host "Activating virtual environment..."
& .\.venv\Scripts\Activate.ps1

if (Test-Path -Path "requirements.txt") {
    Write-Host "Installing requirements (may skip if already installed)..."
    pip install -r requirements.txt
} else {
    Write-Host "No requirements.txt found; skipping install."
}

if (-not (Test-Path -Path ".env")) {
    if (Test-Path -Path ".env.example") {
        Copy-Item .env.example .env
        Write-Host ".env created from .env.example — edit it with your credentials before continuing."
    } else {
        Write-Host "No .env or .env.example found — create .env manually if needed."
    }
} else {
    Write-Host ".env already exists."
}

Write-Host "Starting server (development)..."
$env:FLASK_ENV = "development"
python backend/app.py
