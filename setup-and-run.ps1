[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $ProjectRoot ".venv"
$PythonPath = Join-Path $VenvPath "Scripts\python.exe"
$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"
$EnvPath = Join-Path $ProjectRoot "web\.env"
$AppPath = Join-Path $ProjectRoot "web\backend\app.py"
$HealthUrl = "http://127.0.0.1:5000/api/health"
$AppUrl = "http://127.0.0.1:5000"

Set-Location $ProjectRoot

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Find-SystemPython {
    foreach ($candidate in @("py", "python", "python3")) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $candidate
        }
    }
    throw "Khong tim thay Python. Hay cai Python 3.10+ va chon 'Add Python to PATH'."
}

Write-Step "Kiem tra Python"
$SystemPython = Find-SystemPython

if (-not (Test-Path $PythonPath)) {
    Write-Step "Tao moi truong ao tai .venv"
    if ($SystemPython -eq "py") {
        & py -3 -m venv $VenvPath
    } else {
        & $SystemPython -m venv $VenvPath
    }
}

if (-not (Test-Path $PythonPath)) {
    throw "Khong the tao moi truong ao .venv."
}

if (-not $SkipInstall) {
    Write-Step "Cap nhat pip va cai dependencies"
    & $PythonPath -m pip install --upgrade pip
    & $PythonPath -m pip install -r $RequirementsPath
}

if (-not (Test-Path $EnvPath)) {
    Write-Step "Tao web/.env mac dinh"
    @"
DEBUG=true
API_HOST=0.0.0.0
API_PORT=5000
SECRET_KEY=development-only-change-me
SESSION_COOKIE_SECURE=false
ALLOWED_ORIGINS=http://localhost:5000,http://127.0.0.1:5000

# Dien key neu can dung AI hoac Google:
OPENROUTER_API_KEY=
OPENAI_API_KEY=
MISTRAL_API_KEY=
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_REDIRECT_URI=http://127.0.0.1:5000/api/email/oauth2callback
"@ | Set-Content -LiteralPath $EnvPath -Encoding UTF8
}

Write-Step "Khoi dong FlowMate tai $AppUrl"
$Server = Start-Process `
    -FilePath $PythonPath `
    -ArgumentList @($AppPath) `
    -WorkingDirectory $ProjectRoot `
    -NoNewWindow `
    -PassThru

try {
    $Ready = $false
    for ($attempt = 1; $attempt -le 40; $attempt++) {
        if ($Server.HasExited) {
            throw "Backend da dung voi exit code $($Server.ExitCode)."
        }

        try {
            $response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
            if ($response.status -eq "ok") {
                $Ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    if (-not $Ready) {
        throw "Backend khong san sang sau 20 giay."
    }

    Write-Host "FlowMate dang chay: $AppUrl" -ForegroundColor Green
    Write-Host "Nhan Ctrl+C de dung server." -ForegroundColor DarkGray

    if (-not $NoBrowser) {
        Start-Process $AppUrl
    }

    Wait-Process -Id $Server.Id
} finally {
    if ($Server -and -not $Server.HasExited) {
        Stop-Process -Id $Server.Id -Force
    }
}
