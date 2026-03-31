@echo off
:: Uninstall HTTP proxy scheduled task
:: Run this script as Administrator

schtasks /delete /tn "AINewsProxy" /f

if %errorlevel% equ 0 (
    echo [OK] Service removed.
) else (
    echo [ERROR] Failed to remove. Make sure to run as Administrator.
)

:: Kill any remaining python proxy processes
taskkill /f /fi "WINDOWTITLE eq *http_proxy*" >nul 2>&1

pause
