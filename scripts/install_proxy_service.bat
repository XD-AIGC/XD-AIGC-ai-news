@echo off
:: Install HTTP proxy as a Windows scheduled task (runs at startup, auto-restart)
:: Run this script as Administrator

set SCRIPT_DIR=%~dp0
set PYTHON=C:\Python312\python.exe
set PORT=18888

:: Kill existing task if any
schtasks /delete /tn "AINewsProxy" /f >nul 2>&1

:: Create the scheduled task - runs at system startup, restarts on failure
schtasks /create /tn "AINewsProxy" /tr "\"%PYTHON%\" \"%SCRIPT_DIR%http_proxy.py\" --port %PORT%" /sc onstart /ru SYSTEM /rl HIGHEST /f

if %errorlevel% equ 0 (
    echo.
    echo [OK] Service installed. Starting now...
    schtasks /run /tn "AINewsProxy"
    echo [OK] Proxy running on 0.0.0.0:%PORT%
) else (
    echo [ERROR] Failed to install. Make sure to run as Administrator.
)

pause
