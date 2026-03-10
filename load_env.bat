@echo off
REM Shared .env loader — call this from other bat files to load key=value pairs.
REM Usage:  call load_env.bat  (run from repo root, or adjust DOTENV_PATH first)
REM Requires: setlocal enabledelayedexpansion must already be active in the caller.

set DOTENV_PATH=%~dp0.env
if not exist "%DOTENV_PATH%" (
    echo   [load_env] .env not found at %DOTENV_PATH% — skipping
    goto :eof
)
for /f "usebackq tokens=1,* delims==" %%a in ("%DOTENV_PATH%") do (
    if not "%%a"=="" (
        set "_k=%%a"
        if not "!_k:~0,1!"=="#" set "%%a=%%b"
    )
)
echo Loaded .env
