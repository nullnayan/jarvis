@echo off
title Stop Jarvis PC Agent

echo ========================================================
echo             STOPPING JARVIS PC AGENT
echo ========================================================

powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*backend\pc_agent\agent.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host 'Stopped PC Agent process ID:' $_.ProcessId }"

taskkill /F /FI "WINDOWTITLE eq Jarvis PC Agent*" 2>nul

echo.
echo [✓] Jarvis PC Agent has been completely stopped!
echo.
timeout /t 3 >nul
