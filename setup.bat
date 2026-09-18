@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ============================================================
echo   Desktop AI Assistant -- One-Click Setup for Windows
echo ============================================================
echo.

:: 1. Check Python availability
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found in your PATH!
    echo Please install Python 3.10+ from https://www.python.org/
    echo IMPORTANT: Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Check Python version
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.10 or higher is required.
    python --version
    echo.
    pause
    exit /b 1
)
echo [+] Python detected: 
python --version

:: 3. Create virtual environment if not already present
if not exist "venv\Scripts\activate.bat" (
    echo.
    echo [+] Creating virtual environment in .\venv ...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [+] Virtual environment .\venv already exists.
)

:: 4. Activate virtual environment
call venv\Scripts\activate.bat

:: 5. Install dependencies
echo.
echo [+] Installing/updating dependencies from requirements.txt ...
python -m pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

:: 6. Setup config/.env if not present
if not exist "config\.env" (
    if exist "config\.env.example" (
        echo.
        echo [+] Creating config\.env from template ...
        copy "config\.env.example" "config\.env" >nul
        echo [NOTE] Remember to open config\.env and paste your API keys if you want AI features!
    )
)

:: 7. Run system diagnostic
echo.
python doctor.py

echo.
echo ============================================================
echo   Setup Complete!
echo   You can now launch the assistant by double-clicking run.bat
echo ============================================================
echo.
pause
endlocal
