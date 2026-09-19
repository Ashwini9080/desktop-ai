@echo off
title Desktop AI - Phone Connection Check
cls
echo ========================================================
echo   Checking Connected Android Devices (ADB)
echo ========================================================
echo.

cd /d "%~dp0platform-tools"
adb.exe devices

echo.
echo ========================================================
echo   If you see 'device' next to your ID, phone is ready!
echo   If you see 'unauthorized', check your mobile screen.
echo ========================================================
echo.
pause
