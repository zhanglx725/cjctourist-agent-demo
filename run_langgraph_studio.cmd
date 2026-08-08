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

rem Force role narration and presentation-plan Shadow into the child server.
rem This prevents an old process/environment value from disabling the test.
set "CJC_READ_ONLY_ROLLOUT_MODE=shadow"
set "CJC_READ_ONLY_ROLLOUT_CAPABILITIES=role_narration,presentation_content_plan"

rem Use a fresh local port so stale 2034 processes cannot shadow this Graph.
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":2035" ^| findstr "LISTENING"') do (
    echo Port 2035 is already occupied by PID %%P.
    echo Close the process using 2035, then run this file again.
    pause
    exit /b 1
)

echo Starting LangGraph local server...
echo When the server reports ready, open:
echo https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2035
echo Shadow capabilities: role_narration,presentation_content_plan

rem Open the current LangSmith Studio after the local server has had time to start.
start "LangGraph server" cmd /k "set CJC_READ_ONLY_ROLLOUT_MODE=shadow&& set CJC_READ_ONLY_ROLLOUT_CAPABILITIES=role_narration,presentation_content_plan&& echo CJC_READ_ONLY_ROLLOUT_MODE=shadow&& echo CJC_READ_ONLY_ROLLOUT_CAPABILITIES=role_narration,presentation_content_plan&& langgraph dev --port 2035"
timeout /t 5 /nobreak >nul
start "LangSmith Studio" "https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2035"

echo LangGraph is running on http://127.0.0.1:2035
echo Close the server window to stop it.
