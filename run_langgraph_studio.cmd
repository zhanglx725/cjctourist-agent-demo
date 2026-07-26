@echo off
setlocal
cd /d "%~dp0"
call .venv\Scripts\activate.bat

rem Prevent Windows GBK defaults from breaking UTF-8 OpenAPI/project files.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo Starting LangGraph local server...
echo Keep the new server window open while testing in LangSmith Studio.
start "Chen Clan Academy LangGraph Server" cmd /k "cd /d \"%~dp0\" && call .venv\Scripts\activate.bat && set PYTHONUTF8=1 && set PYTHONIOENCODING=utf-8 && langgraph dev"

timeout /t 3 /nobreak >nul
start "Chen Clan Academy LangSmith Studio" "https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024"

echo Studio opening in your browser. If the server is still warming up, wait for the server window to show it is ready, then refresh the page.
endlocal
