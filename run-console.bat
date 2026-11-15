@echo off
rem ---------------------------------------------------------------------------
rem  GST - Directory Structure Tree Generator   (keeps the console visible)
rem  Use this one when the GUI fails to start: tracebacks stay on screen.
rem  ASCII-only on purpose (cmd.exe reads .bat in the OEM codepage).
rem ---------------------------------------------------------------------------
setlocal
set "HERE=%~dp0"
set "PY=%HERE%..\venv312\Scripts\python.exe"

if not exist "%PY%" (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [GST] venv312 python.exe not found, and no python on PATH.
        echo      Expected: %HERE%..\venv312\Scripts\python.exe
        pause
        exit /b 1
    )
    set "PY=python"
)

"%PY%" "%HERE%app.py"
if errorlevel 1 (
    echo.
    echo [GST] The program exited with an error. Press any key to close.
    pause >nul
)
exit /b 0
