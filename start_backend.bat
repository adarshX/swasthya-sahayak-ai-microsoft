@echo off
setlocal enabledelayedexpansion
REM Swasthya Sahayak AI - Backend Startup Script (Windows)
REM Runs the FastAPI backend on port 8080

cd /d "%~dp0backend"

REM Check if virtual environment exists
if not exist "..\venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv ..\venv
)

call ..\venv\Scripts\activate.bat

REM Install dependencies
pip install -r requirements.txt -q

REM Load .env from project root
call "%~dp0load_env.bat"

echo.
echo Starting Swasthya Sahayak backend on http://localhost:8080
echo Press Ctrl+C to stop.
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
