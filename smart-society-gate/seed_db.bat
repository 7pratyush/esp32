@echo off
cd /d "%~dp0"
.venv\Scripts\python tools\seed_db.py
pause
