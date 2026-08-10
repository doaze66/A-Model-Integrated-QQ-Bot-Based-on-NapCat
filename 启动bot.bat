@echo off
title QQ AI Bot - One Click Start
set "BASE=%~dp0"

rem ---- NapCat 位置：优先用户目录（setup.bat 安装的目标），回退到本地目录 ----
set "NAPCAT_BAT=%USERPROFILE%\napcat\start_napcat.bat"
if not exist "%NAPCAT_BAT%" set "NAPCAT_BAT=%BASE%napcat\start_napcat.bat"
if not exist "%NAPCAT_BAT%" (
    echo [FATAL] napcat start_napcat.bat not found!
    echo Please run setup.bat first, or keep this file inside the QQBot folder.
    pause
    exit /b 1
)

echo ================================================
echo    QQ AI Bot One-Click Start
echo ================================================
echo.

rem ---- 1. cleanup ----
echo [1/4] Cleaning up old processes (QQ/NapCat/bot)...
taskkill /f /im QQ.exe >nul 2>&1
taskkill /f /im NapCatWinBootMain.exe >nul 2>&1
taskkill /f /im qq_ai.exe >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*qq_ai*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
ping -n 4 127.0.0.1 >nul

rem ---- 2. start NapCat ----
echo [2/4] Starting NapCat (QQ window will popup)...
start /min "" "%NAPCAT_BAT%"

rem ---- 3. wait for port 3001 (max 120s) ----
echo [3/4] Waiting for OneBot WS 3001 (max 120s)...
set /a tries=0
:wait_loop
set /a tries+=1
netstat -ano | findstr /r ":3001[^0-9].*LISTENING" >nul 2>&1
if not errorlevel 1 goto ws_ready
if %tries% geq 24 goto ws_timeout
ping -n 6 127.0.0.1 >nul
goto wait_loop

:ws_ready
echo        WebSocket 3001 ready
goto start_ai

:ws_timeout
echo        [WARN] port 3001 not detected in 120s
echo        Possible: QQ needs QR-code login / login failed

rem ---- 4. start bot ----
:start_ai
echo [4/4] Starting QQ AI bot...
start "" "%BASE%qq_ai\start_qqai.bat"

echo.
echo ================================================
echo    All done!
echo    - Bot log: %BASE%qq_ai\qq_ai.log
echo    - Stop: Task Manager, kill QQ.exe / NapCatWinBootMain.exe / qq_ai.exe
echo    - This window can be closed safely
echo ================================================
pause
