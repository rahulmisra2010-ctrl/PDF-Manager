# =============================================================================
#  PDF-Manager — Windows PowerShell Setup Script
#  Automates the full developer setup: directories, .env, pip deps, DB, server
#
#  Usage:
#    powershell -ExecutionPolicy Bypass -File setup.ps1
# =============================================================================

#Requires -Version 5.1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helper: coloured status messages
# ---------------------------------------------------------------------------
function Write-Ok   ([string]$msg) { Write-Host "[OK]    $msg" -ForegroundColor Green  }
function Write-Skip ([string]$msg) { Write-Host "[SKIP]  $msg" -ForegroundColor Cyan   }
function Write-Info ([string]$msg) { Write-Host "[INFO]  $msg" -ForegroundColor Yellow }
function Write-Warn ([string]$msg) { Write-Host "[WARN]  $msg" -ForegroundColor DarkYellow }
function Write-Fail ([string]$msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red    }

Write-Host ""
Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host "  PDF-Manager Setup" -ForegroundColor Cyan
Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# 0. Verify Python is available
# ---------------------------------------------------------------------------
Write-Host "[STEP 0] Checking Python installation..."

$pythonCmd = $null
foreach ($candidate in @("python", "python3")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($LASTEXITCODE -eq 0) { $pythonCmd = $candidate; break }
    } catch { }
}

if (-not $pythonCmd) {
    Write-Fail "Python was not found. Please install Python 3.11+ and add it to PATH."
    exit 1
}

$pythonVersion = & $pythonCmd --version 2>&1
Write-Ok "Found $pythonVersion"

# ---------------------------------------------------------------------------
# 1. Create required directories
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 1] Creating required directories..."

foreach ($dir in @("instance", "uploads", "exports")) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Ok "Created directory: $dir"
    } else {
        Write-Skip "Directory already exists: $dir"
    }
}

# ---------------------------------------------------------------------------
# 2. Create .env file from .env.example (if .env is missing)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 2] Configuring .env file..."

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Ok "Created .env from .env.example"
        Write-Info "Review .env and set SECRET_KEY and ADMIN_PASSWORD before production use."
    } else {
        Write-Warn ".env.example not found — creating a minimal .env"
        @"
APP_NAME="PDF-Manager API"
API_VERSION="1.0.0"
DEBUG=false
HOST=0.0.0.0
PORT=5000
SECRET_KEY=change-me-in-production
ADMIN_PASSWORD=
ALLOWED_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
DATABASE_URL=sqlite:///instance/pdf_manager.db
UPLOAD_DIR=uploads
EXPORT_DIR=exports
MAX_UPLOAD_SIZE_MB=50
ML_MODEL_DIR=models
ML_CONFIDENCE_THRESHOLD=0.75
USE_GPU=false
"@ | Set-Content ".env" -Encoding UTF8
        Write-Ok "Created minimal .env"
    }
} else {
    Write-Skip ".env already exists — keeping current configuration"
}

# ---------------------------------------------------------------------------
# 3. Delete old database and __pycache__ directories
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 3] Cleaning old database and cached bytecode..."

$dbPath = "instance\pdf_manager.db"
if (Test-Path $dbPath) {
    Remove-Item $dbPath -Force
    Write-Ok "Deleted old database: $dbPath"
} else {
    Write-Skip "No existing database found"
}

$caches = Get-ChildItem -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue
if ($caches) {
    foreach ($cache in $caches) {
        Remove-Item $cache.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Ok "Removed $($caches.Count) __pycache__ director(ies)"
} else {
    Write-Skip "No __pycache__ directories found"
}

# ---------------------------------------------------------------------------
# 4. Install / upgrade pip and project dependencies
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 4] Installing Python dependencies..."

& $pythonCmd -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to upgrade pip."; exit 1 }
Write-Ok "pip upgraded"

$reqFile = $null
if (Test-Path "backend\requirements.txt") { $reqFile = "backend\requirements.txt" }
elseif (Test-Path "requirements.txt")     { $reqFile = "requirements.txt" }

if ($reqFile) {
    Write-Info "Installing from $reqFile ..."
    & $pythonCmd -m pip install -r $reqFile --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Dependency installation failed. Check $reqFile."
        exit 1
    }
    Write-Ok "Dependencies installed from $reqFile"
} else {
    Write-Warn "No requirements.txt found — skipping dependency installation"
}

# ---------------------------------------------------------------------------
# 5. Initialise the database (create all tables)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 5] Initializing database tables..."

$initScript = "from app import create_app; app = create_app(); print('Database initialised successfully.')"
$output = & $pythonCmd -c $initScript 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Database initialisation failed:"
    Write-Host $output
    exit 1
}
Write-Ok "Database tables initialized"

# ---------------------------------------------------------------------------
# 6. Start the backend server
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 6] Starting the PDF-Manager backend server..."
Write-Host ""
Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host "  Server starting at http://localhost:5000" -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop the server." -ForegroundColor Cyan
Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host ""

& $pythonCmd app.py
