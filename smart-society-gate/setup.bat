@echo off
REM One-time setup: creates .venv, installs packages, creates .env
cd /d "%~dp0"
where py >nul 2>nul && (py -3.11 -m venv .venv) || (python -m venv .venv)
if not exist .venv\Scripts\python.exe (
  echo Could not create virtual environment. Install Python 3.11 and tick "Add to PATH".
  pause & exit /b 1
)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Setup done. Edit .env if you want to change the secrets, then run seed_db.bat
pause
