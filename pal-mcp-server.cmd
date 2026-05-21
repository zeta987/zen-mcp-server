@echo off
cd /d "%~dp0"
if exist ".pal_venv\Scripts\python.exe" (
    .pal_venv\Scripts\python.exe server.py %*
) else (
    python server.py %*
)
