@echo off
setlocal enabledelayedexpansion
title QQ AI 替身 - 一键安装

rem ============ Administrator check ============
net session >nul 2>&1
if not errorlevel 1 goto :admin_ok
echo [INFO] Installing QQ / Node.js requires administrator rights
set /p ADM_CHOICE=Run again as administrator? (Y/N, default Y): 
if /i "!ADM_CHOICE!"=="N" goto :admin_ok
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
exit /b
:admin_ok

set "BASE=%~dp0"
set "QQ_EXE=C:\Program Files\Tencent\QQNT\QQ.exe"
set "DEST=%USERPROFILE%\napcat"

echo ================================================
echo    QQ AI 替身 - 一键安装
echo ================================================
echo.

rem ============ 0. 文件完整性 ============
echo [0/5] 检查分发文件...
if not exist "%BASE%napcat\napcat.mjs" (
    echo [FATAL] 缺少 napcat 目录，请保持分发目录结构完整
    pause
    exit /b 1
)
if not exist "%BASE%napcat\NapCatWinBootMain.exe" (
    echo [FATAL] 缺少 NapCatWinBootMain.exe
    pause
    exit /b 1
)
if not exist "%BASE%qq_ai\dist\qq_ai.exe" (
    echo [WARN] 未找到 qq_ai\dist\qq_ai.exe，AI 主程序将无法启动
)
if not exist "%BASE%templates\render_napcat.ps1" (
    echo [FATAL] 缺少 templates 目录
    pause
    exit /b 1
)
echo        检查通过

rem ============ 1. QQ 检测 ============
echo.
echo [1/5] 检测 QQ 客户端...
if exist "%QQ_EXE%" (
    echo        QQ 已安装: %QQ_EXE%
    goto qq_ok
)
echo        [WARN] 未检测到 QQ 客户端！
echo        机器人依赖 QQ，请先安装 QQ 到默认路径:
echo        %QQ_EXE%
echo        官方下载: https://im.qq.com
echo.
set /p QQ_CHOICE=Install QQ silently from this folder? (Y=yes / N=no, default N): 
if /i "!QQ_CHOICE!"=="Y" (
    set "QQ_INSTALLER="
    for %%F in ("%BASE%QQ_*.exe" "%BASE%installers\QQ_*.exe") do (
        if exist "%%F" set "QQ_INSTALLER=%%F"
    )
    if defined QQ_INSTALLER (
        echo        Installing QQ silently: !QQ_INSTALLER!
        start /wait "" "!QQ_INSTALLER!" /s
        echo        Installer finished, checking result...
    ) else (
        echo        [WARN] QQ installer not found, please install manually
    )
)
if not exist "%QQ_EXE%" (
    echo        [WARN] QQ still not detected!
    echo        Possible: installer does not support /s silent, or installed elsewhere
    echo        Please install QQ to: %QQ_EXE%
)
:qq_ok

rem ============ 2. Node.js 检测 ============
echo.
echo [2/5] 检测 Node.js...
node --version >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%v in ('node --version') do set "NODE_VER=%%v"
    echo        Node.js 已安装: !NODE_VER!
    goto node_ok
)
echo        [WARN] 未检测到 Node.js！
echo        NapCat 框架需要 Node.js 运行环境
echo        下载: https://nodejs.org (推荐 LTS 版本)
echo.
set /p NODE_CHOICE=Install Node.js silently from this folder? (Y=yes / N=no, default N): 
if /i "!NODE_CHOICE!"=="Y" (
    set "NODE_MSI="
    for %%F in ("%BASE%node-*.msi" "%BASE%installers\node-*.msi") do (
        if exist "%%F" set "NODE_MSI=%%F"
    )
    if defined NODE_MSI (
        echo        Installing Node.js silently: !NODE_MSI!
        start /wait "" msiexec /i "!NODE_MSI!" /quiet /norestart
        echo        Install finished, refreshing PATH...
        call :reload_path
        node --version >nul 2>&1
        if not errorlevel 1 (
            for /f "delims=" %%v in ('node --version') do set "NODE_VER=%%v"
            echo        Node.js installed: !NODE_VER!
        ) else (
            echo        [WARN] Node.js not usable yet, reboot may be required
        )
    ) else (
        echo        [WARN] Node.js installer not found, please install manually
    )
)
:node_ok

rem ============ 3. 安装 NapCat 到用户目录 ============
echo.
echo [3/5] 安装 NapCat 到 %DEST% ...
if exist "%DEST%\napcat.mjs" (
    echo        已存在 NapCat，跳过复制（保留现有配置）
    goto napcat_copy_done
)
if not exist "%DEST%" mkdir "%DEST%"
robocopy "%BASE%napcat" "%DEST%" /E /NFL /NDL /NJH /NJS /NC /NS /R:1 /W:1
if errorlevel 8 (
    echo        [FATAL] 复制 NapCat 失败（错误码 %ERRORLEVEL%）
    pause
    exit /b 1
)
echo        NapCat 复制完成
:napcat_copy_done

rem ============ 4. 重写硬编码路径 ============
echo.
echo [4/5] 生成启动文件（写入本机路径）...
powershell -NoProfile -ExecutionPolicy Bypass -File "%BASE%templates\render_napcat.ps1" -NapcatDir "%DEST%"
if errorlevel 1 (
    echo        [FATAL] 路径写入失败
    pause
    exit /b 1
)
echo        启动文件已生成: %DEST%\loadNapCat.js / start_napcat.bat

rem ============ 5. 校验 qq_ai ============
echo.
echo [5/5] 校验 AI 主程序...
if exist "%BASE%qq_ai\dist\qq_ai.exe" (
    set "EXE_SIZE=?"
    for %%F in ("%BASE%qq_ai\dist\qq_ai.exe") do set "EXE_SIZE=%%~zF"
    echo        qq_ai.exe 就绪 !EXE_SIZE! 字节
) else (
    echo        [WARN] qq_ai.exe 缺失，机器人无法回复消息
)

rem ============ 完成 ============
echo.
echo ================================================
echo    安装完成！
echo ================================================
echo.
echo 接下来:
echo   1. 编辑 qq_ai\config.yaml 确认配置:
echo      - llm.api_key   : 你的 API Key
echo      - bot_qq        : 机器人 QQ 号
echo      - whitelist     : 允许回复的群/人
echo   2. 双击 "启动QQ替身.bat"
echo   3. 首次运行 QQ 会弹出登录窗口，扫码登录后
echo      看到 "All done!" 即启动完成
echo.
echo 日志位置: qq_ai\qq_ai.log
echo.
pause
