@echo off
title ShelfAI — AI Retail Inventory Monitor
color 0A

echo.
echo  ============================================
echo    ShelfAI — AI Retail Inventory Monitor
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found. Install Python 3.10+ from python.org
    pause
    exit /b 1
)

:: Check Node
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Node.js not found. Install Node.js 18+ from nodejs.org
    pause
    exit /b 1
)

echo  [1/4] Installing Python dependencies...
cd /d "%~dp0backend"
pip install -r requirements.txt --quiet >nul 2>&1
if %errorlevel% neq 0 (
    echo  [WARN] Some pip packages may have failed. Continuing...
)

echo  [2/4] Installing frontend dependencies...
cd /d "%~dp0frontend"
if not exist node_modules (
    call npm install --silent >nul 2>&1
) else (
    echo         node_modules exists, skipping...
)

echo  [3/4] Building frontend...
call npm run build --silent >nul 2>&1

echo  [4/4] Starting backend server...
echo.
echo  ============================================
echo    Dashboard:  http://localhost:8000
echo    API Docs:   http://localhost:8000/docs
echo  ============================================
echo.
echo  Press Ctrl+C to stop the server.
echo.

cd /d "%~dp0backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
