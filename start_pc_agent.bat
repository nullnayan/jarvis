@echo off
title Jarvis PC Agent (Cloud Bridge)
cd /d "%~dp0"

echo ========================================================
echo         JARVIS PC AGENT - CLOUD BRIDGE (PHASE 2)
echo ========================================================
echo Connecting to Cloud Jarvis Gateway...
echo.

if exist "backend\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=backend\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" backend\pc_agent\agent.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [PCAgent] Process ended with code %ERRORLEVEL%.
    pause
)
