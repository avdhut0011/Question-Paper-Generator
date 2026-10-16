@echo off
REM QPG Network Server Launcher
REM Created by Avadhut Jagtap
REM This script starts the QPG application on the network using Waitress

echo ========================================
echo QPG Network Server Launcher
echo Created by Avadhut Jagtap
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.12+ and try again
    pause
    exit /b 1
)

REM Check if virtual environment exists and activate it
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo [INFO] No virtual environment found, using system Python
)

REM Check if waitress is installed
python -c "import waitress" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing Waitress...
    pip install waitress
    if errorlevel 1 (
        echo [ERROR] Failed to install Waitress
        pause
        exit /b 1
    )
)

REM Check if .env file exists
if not exist ".env" (
    echo [WARNING] .env file not found
    echo Configure DATABASE_URL and FLASK_SECRET_KEY in .env. See README.md.
    echo Example:
    echo DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/ashoka_qpg
    echo FLASK_SECRET_KEY=your_unique_random_secret
    echo.
    pause
)

echo [INFO] Starting QPG Network Server...
echo [INFO] The server will be accessible from other computers on your network
echo [INFO] Press Ctrl+C to stop the server
echo.

REM Start the server with default settings
python serve.py

echo.
echo [INFO] Server stopped
pause
