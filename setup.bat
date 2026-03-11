@echo off
REM =============================================================================
REM  PDF-Manager — Windows Setup Script
REM  Automates the full developer setup: directories, .env, pip deps, DB, server
REM =============================================================================

setlocal EnableDelayedExpansion

echo.
echo =============================================================================
echo   PDF-Manager Setup
echo =============================================================================
echo.

REM ---------------------------------------------------------------------------
REM 0. Check Python is available
REM ---------------------------------------------------------------------------
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found. Please install Python 3.11+ and add it to PATH.
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYTHON_VER=%%v
echo [OK]    Found %PYTHON_VER%

REM ---------------------------------------------------------------------------
REM 1. Create required directories
REM ---------------------------------------------------------------------------
echo.
echo [STEP 1] Creating required directories...

for %%d in (instance uploads exports) do (
    if not exist "%%d" (
        mkdir "%%d"
        echo [OK]    Created directory: %%d
    ) else (
        echo [SKIP]  Directory already exists: %%d
    )
)

REM ---------------------------------------------------------------------------
REM 2. Create .env file from .env.example (if .env is missing)
REM ---------------------------------------------------------------------------
echo.
echo [STEP 2] Configuring .env file...

if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo [OK]    Created .env from .env.example
        echo [NOTE]  Review .env and set SECRET_KEY and ADMIN_PASSWORD before production use.
    ) else (
        echo [WARN]  .env.example not found — creating a minimal .env
        (
            echo APP_NAME="PDF-Manager API"
            echo API_VERSION="1.0.0"
            echo DEBUG=false
            echo HOST=0.0.0.0
            echo PORT=5000
            echo SECRET_KEY=change-me-in-production
            echo ADMIN_PASSWORD=
            echo ALLOWED_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
            echo DATABASE_URL=sqlite:///instance/pdf_manager.db
            echo UPLOAD_DIR=uploads
            echo EXPORT_DIR=exports
            echo MAX_UPLOAD_SIZE_MB=50
            echo ML_MODEL_DIR=models
            echo ML_CONFIDENCE_THRESHOLD=0.75
            echo USE_GPU=false
        ) > ".env"
        echo [OK]    Created minimal .env
    )
) else (
    echo [SKIP]  .env already exists — keeping current configuration
)

REM ---------------------------------------------------------------------------
REM 3. Delete old database and __pycache__ directories
REM ---------------------------------------------------------------------------
echo.
echo [STEP 3] Cleaning old database and cached bytecode...

if exist "instance\pdf_manager.db" (
    del /f /q "instance\pdf_manager.db"
    echo [OK]    Deleted old database: instance\pdf_manager.db
) else (
    echo [SKIP]  No existing database found
)

REM Remove all __pycache__ directories recursively
set CACHE_COUNT=0
for /d /r "." %%c in (__pycache__) do (
    if exist "%%c" (
        rd /s /q "%%c"
        set /a CACHE_COUNT+=1
    )
)
if !CACHE_COUNT! gtr 0 (
    echo [OK]    Removed !CACHE_COUNT! __pycache__ director(ies)
) else (
    echo [SKIP]  No __pycache__ directories found
)

REM ---------------------------------------------------------------------------
REM 4. Install / upgrade pip and project dependencies
REM ---------------------------------------------------------------------------
echo.
echo [STEP 4] Installing Python dependencies...

python -m pip install --upgrade pip --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Failed to upgrade pip.
    exit /b 1
)
echo [OK]    pip upgraded

if exist "backend\requirements.txt" (
    echo [INFO]  Installing from backend\requirements.txt ...
    python -m pip install -r backend\requirements.txt --quiet
    if %errorlevel% neq 0 (
        echo [ERROR] Dependency installation failed. Check backend\requirements.txt.
        exit /b 1
    )
    echo [OK]    Backend dependencies installed
) else if exist "requirements.txt" (
    echo [INFO]  Installing from requirements.txt ...
    python -m pip install -r requirements.txt --quiet
    if %errorlevel% neq 0 (
        echo [ERROR] Dependency installation failed. Check requirements.txt.
        exit /b 1
    )
    echo [OK]    Dependencies installed
) else (
    echo [WARN]  No requirements.txt found — skipping dependency installation
)

REM ---------------------------------------------------------------------------
REM 5. Initialise the database (create tables)
REM ---------------------------------------------------------------------------
echo.
echo [STEP 5] Initializing database tables...

python -c "from app import create_app; app = create_app(); print('Database initialised successfully.')" 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Database initialisation failed. Check the error above.
    exit /b 1
)
echo [OK]    Database tables initialized

REM ---------------------------------------------------------------------------
REM 6. Start the backend server
REM ---------------------------------------------------------------------------
echo.
echo [STEP 6] Starting the PDF-Manager backend server...
echo.
echo =============================================================================
echo   Server starting at http://localhost:5000
echo   Press Ctrl+C to stop the server.
echo =============================================================================
echo.

python app.py

endlocal
