@echo off
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
pip install -r requirements.txt -r requirements-azure.txt -q

REM Load .env from parent directory
set DOTENV_PATH=%~dp0.env
if exist "%DOTENV_PATH%" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%DOTENV_PATH%") do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
    )
    echo Loaded .env
)

echo.
echo Starting Swasthya Sahayak backend on http://localhost:8080
echo Press Ctrl+C to stop.
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
