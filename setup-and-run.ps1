[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$SkipTraining,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $ProjectRoot ".venv"
$PythonPath = Join-Path $VenvPath "Scripts\python.exe"
$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"
$EnvPath = Join-Path $ProjectRoot "web\.env"
$AppPath = Join-Path $ProjectRoot "web\backend\app.py"
$TrainingPath = Join-Path $ProjectRoot "docs\bob-training"
$TrainingScript = Join-Path $ProjectRoot "scripts\train_bob.py"
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

# Bob suy luan va hoc hoan toan cuc bo qua Ollama + RAG:
BOB_LOCAL_ONLY=true
OPENROUTER_ENABLED=false
AI_PRIMARY_PROVIDER=ollama
AI_PROVIDER_ORDER=ollama
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:8b
WEB_RESEARCH_ENABLED=false
AI_MENTOR_LEARNING_ENABLED=true
AI_MENTOR_PROVIDERS=ollama

# Google chi can neu dung Gmail/Calendar:
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_CREDENTIALS_JSON=
GMAIL_REDIRECT_URI=http://127.0.0.1:5000/api/email/oauth2callback
"@ | Set-Content -LiteralPath $EnvPath -Encoding UTF8
}

if (-not $SkipTraining) {
    Write-Step "Nap corpus local vao kho kien thuc cua Bob"
    & $PythonPath $TrainingScript $TrainingPath `
        --tags "noi bo,quy tac,bob,offline" `
        --source "bob-local-corpus-v1"
}

$OllamaCommand = Get-Command "ollama" -ErrorAction SilentlyContinue
if ($OllamaCommand) {
    Write-Step "Da tim thay Ollama local; Bob se dung model cau hinh trong web/.env"
} else {
    Write-Warning "Khong tim thay Ollama. Bob van chay bang RAG/deterministic local; cai Ollama de bat suy luan tu do."
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
