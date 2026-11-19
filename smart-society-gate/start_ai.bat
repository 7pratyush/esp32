@echo off
cd /d "%~dp0"
echo Starting AI service on http://127.0.0.1:8001 (first start downloads EasyOCR models)
.venv\Scripts\python -m uvicorn ai_service.main:app --host 127.0.0.1 --port 8001
pause
