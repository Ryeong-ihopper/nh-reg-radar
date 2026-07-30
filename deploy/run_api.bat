@echo off
REM Local API server. Docs: http://localhost:8000/docs
setlocal
cd /d "%~dp0.." || exit /b 1
set "PYTHONPATH=%CD%\src"
python -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload
endlocal
