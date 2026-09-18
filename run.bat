@echo off
setlocal
cd /d "%~dp0"

:: Activate virtual environment if present
if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
) else if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

python main.py
if errorlevel 1 (
    echo.
    echo Desktop AI stopped with an error. Check logs/desktop_ai.log for details.
    pause
)
endlocal
