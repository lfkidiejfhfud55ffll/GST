@echo off
rem ---------------------------------------------------------------------------
rem  GST - Directory Structure Tree Generator   (no console window)
rem  Prefer ..\venv312\Scripts\pythonw.exe, fall back to the system pythonw.
rem  Note: this file is ASCII-only on purpose; cmd.exe reads .bat in the OEM
rem  codepage, so non-ASCII text here can break the parser on some locales.
rem ---------------------------------------------------------------------------
setlocal
set "HERE=%~dp0"
set "PY=%HERE%..\venv312\Scripts\pythonw.exe"

if not exist "%PY%" (
    where pythonw >nul 2>nul
    if errorlevel 1 (
        echo [GST] venv312 pythonw.exe not found, and no pythonw on PATH.
        echo      Expected: %HERE%..\venv312\Scripts\pythonw.exe
        pause
        exit /b 1
    )
    set "PY=pythonw"
)

start "" "%PY%" "%HERE%app.py"
exit /b 0
