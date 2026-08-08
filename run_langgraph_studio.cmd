@echo off
setlocal
cd /d "%~dp0"

rem Prevent Windows GBK defaults from breaking UTF-8 OpenAPI/project files.
rem Keep this process in the foreground so Uvicorn's spawned worker inherits
rem the UTF-8 settings reliably.
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
call .venv\Scripts\activate.bat

echo Starting LangGraph local server...
echo When the server reports ready, open:
echo https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2034

rem Open the current LangSmith Studio after the local server has had time to start.
start "LangGraph server" cmd /k "langgraph dev --port 2034"
timeout /t 5 /nobreak >nul
start "LangSmith Studio" "https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2034"

echo LangGraph is running on http://127.0.0.1:2034
echo Close the server window to stop it.
