@echo off
cd /d "%~dp0"
echo Starting Gateway on port 8000 (ESP32 uses http://YOUR-LAPTOP-IP:8000)
.venv\Scripts\python -m uvicorn gateway.main:app --host 0.0.0.0 --port 8000
pause
