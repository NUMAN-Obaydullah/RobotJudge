@echo off
setlocal

echo [RobotJudge-CI] Starting automated setup for Windows...

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10 or higher.
    pause
    exit /b 1
)

:: Create Virtual Environment
if not exist .venv (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
) else (
    echo [1/3] Virtual environment already exists.
)

:: Activate and install requirements
echo [2/3] Installing dependencies...
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

:: Setup .env
if not exist .env (
    echo [3/3] Creating .env from .env.example...
    copy .env.example .env
    echo [!] Remember to edit .env and add your NGROK_AUTHTOKEN if needed.
) else (
    echo [3/3] .env already exists.
)

echo [RobotJudge-CI] Setup complete! 
echo To start the server, run: .venv\Scripts\activate ^&^& python web/server.py
pause
