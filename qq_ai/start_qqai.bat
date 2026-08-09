@echo off
rem Start QQ AI bot: prefer packaged exe, fallback to python
set BASE=%~dp0
cd /d "%BASE%"
if exist "%BASE%dist\qq_ai.exe" (
    rem Sync config.yaml and persona.txt next to the exe (exe reads from its own dir)
    if exist "%BASE%config.yaml" copy /y "%BASE%config.yaml" "%BASE%dist\config.yaml" >nul
    if exist "%BASE%persona.txt" copy /y "%BASE%persona.txt" "%BASE%dist\persona.txt" >nul
    start "" "%BASE%dist\qq_ai.exe"
    echo qq_ai.exe started, log: qq_ai.log
) else (
    start "" "%BASE%main.py"
    echo qq_ai (python) started, log: qq_ai.log
)
