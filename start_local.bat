@echo off
setlocal EnableDelayedExpansion
title SyncBoard Setup

REM ══════════════════════════════════════════════════════════════
REM  SyncBoard — Windows Startup
REM  Usage: .\start_local.bat  (from PowerShell)
REM         start_local.bat    (from Command Prompt)
REM ══════════════════════════════════════════════════════════════

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo.
echo  +-------------------------------------------+
echo  ^|   SyncBoard  -  Windows Startup           ^|
echo  +-------------------------------------------+
echo.

REM ════════════════════════════════════════════════════════════════
REM  1. CHECK PREREQUISITES
REM ════════════════════════════════════════════════════════════════
echo [1/5] Checking prerequisites...
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python not found.
    echo  Install from https://python.org  ^(tick "Add to PATH"^)
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  OK: %%v

where node >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Node.js not found.
    echo  Install from https://nodejs.org
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('node --version') do echo  OK: Node %%v

where tesseract >nul 2>&1
if %errorlevel% equ 0 (
    echo  OK: Tesseract found
) else (
    if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
        echo  OK: Tesseract at C:\Program Files\Tesseract-OCR\
    ) else (
        echo  WARN: Tesseract not installed - OCR will return empty text.
        echo  Get it from: https://github.com/UB-Mannheim/tesseract/wiki
        echo  Install to: C:\Program Files\Tesseract-OCR\
        echo  ^(App will still run - install Tesseract later for OCR^)
    )
)
echo.

REM ════════════════════════════════════════════════════════════════
REM  2. POSTGRESQL ^(optional^)
REM ════════════════════════════════════════════════════════════════
echo [2/5] Starting PostgreSQL ^(optional^)...

where docker >nul 2>&1
if %errorlevel% equ 0 (
    docker info >nul 2>&1
    if %errorlevel% equ 0 (
        cd /d "%ROOT%"
        docker compose up postgres -d >nul 2>&1
        echo  OK: PostgreSQL container started
        timeout /t 3 /nobreak >nul
    ) else (
        echo  INFO: Docker not running. Start Docker Desktop for DB persistence.
        echo  App works without it - sessions won't be saved to disk.
    )
) else (
    echo  INFO: Docker not installed. App works without PostgreSQL.
)
echo.

REM ════════════════════════════════════════════════════════════════
REM  3. PYTHON BACKEND
REM ════════════════════════════════════════════════════════════════
echo [3/5] Setting up Python backend...

cd /d "%ROOT%\backend"

if not exist ".venv" (
    echo  Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo  ERROR: Could not create venv.
        pause & exit /b 1
    )
)
echo  OK: venv ready

call ".venv\Scripts\activate.bat"

echo  Installing packages ^(first run takes ~60s^)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo  ERROR: pip install failed.
    pause & exit /b 1
)
echo  OK: packages installed

if not exist ".env" (
    python -c "f=open('.env','w'); f.write('DATABASE_URL=postgresql+asyncpg://syncboard:syncboard_secret@localhost:5432/syncboard\n'); f.write('OCR_ENGINE=tesseract\n'); f.write('MIN_CONFIDENCE=30\n'); f.write('CLEAR_THRESHOLD=0.05\n'); f.write('CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173\n'); f.close()"
    echo  OK: created backend\.env
)

REM Write a helper script to launch backend (avoids nested-quote path issues)
set "HELPER=%TEMP%\syncboard_backend.bat"
echo @echo off > "%HELPER%"
echo cd /d "%ROOT%\backend" >> "%HELPER%"
echo call ".venv\Scripts\activate.bat" >> "%HELPER%"
echo uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload >> "%HELPER%"

echo  Starting backend...
start "SyncBoard Backend ^(port 8000^)" cmd /k ""%HELPER%""

echo  Waiting for backend ^(up to 30s^)...
set TRIES=0
:wait_backend
timeout /t 1 /nobreak >nul
set /a TRIES+=1
curl -sf http://localhost:8000/health >nul 2>&1
if %errorlevel% equ 0 (
    echo  OK: Backend ready at http://localhost:8000
    goto frontend
)
if %TRIES% lss 30 goto wait_backend
echo  WARN: Backend slow - check the "SyncBoard Backend" window for errors.

:frontend
echo.
cd /d "%ROOT%"

REM ════════════════════════════════════════════════════════════════
REM  4. NODE FRONTEND
REM ════════════════════════════════════════════════════════════════
echo [4/5] Setting up frontend...

cd /d "%ROOT%\frontend"

if not exist "node_modules" (
    echo  Installing npm packages ^(first run ~30s^)...
    call npm install --loglevel error
    if %errorlevel% neq 0 (
        echo  ERROR: npm install failed.
        pause & exit /b 1
    )
)
echo  OK: npm packages ready

REM Write helper script to launch frontend
set "FHELPER=%TEMP%\syncboard_frontend.bat"
echo @echo off > "%FHELPER%"
echo cd /d "%ROOT%\frontend" >> "%FHELPER%"
echo npm run dev >> "%FHELPER%"

echo  Starting frontend...
start "SyncBoard Frontend ^(port 5173^)" cmd /k ""%FHELPER%""

echo  Waiting for frontend ^(up to 25s^)...
set TRIES=0
:wait_frontend
timeout /t 1 /nobreak >nul
set /a TRIES+=1
curl -sf http://localhost:5173 >nul 2>&1
if %errorlevel% equ 0 (
    echo  OK: Frontend ready at http://localhost:5173
    goto done
)
if %TRIES% lss 25 goto wait_frontend
echo  WARN: Frontend slow - check the "SyncBoard Frontend" window.

:done
echo.
cd /d "%ROOT%"

REM ════════════════════════════════════════════════════════════════
REM  5. OPEN BROWSER
REM ════════════════════════════════════════════════════════════════
echo [5/5] Opening browser...
timeout /t 1 /nobreak >nul
start "" "http://localhost:5173"

echo.
echo  +==================================================+
echo  ^|  SyncBoard is running!                          ^|
echo  ^|                                                 ^|
echo  ^|  App      http://localhost:5173                ^|
echo  ^|  API      http://localhost:8000                ^|
echo  ^|  Docs     http://localhost:8000/docs           ^|
echo  ^|                                                 ^|
echo  ^|  Close the two terminal windows to stop.       ^|
echo  +==================================================+
echo.
pause
endlocal
