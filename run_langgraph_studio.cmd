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

rem Never open Studio against an older process already occupying port 2034.
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":2034" ^| findstr "LISTENING"') do (
    echo Port 2034 is already occupied by PID %%P.
    echo Close the old LangGraph server window, then run this file again.
    pause
    exit /b 1
)

echo Starting LangGraph local server...
echo When the server reports ready, open:
echo https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2034
echo Shadow capabilities: role_narration,presentation_content_plan

rem Open the current LangSmith Studio after the local server has had time to start.
start "LangGraph server" cmd /k "set CJC_READ_ONLY_ROLLOUT_MODE=shadow&& set CJC_READ_ONLY_ROLLOUT_CAPABILITIES=role_narration,presentation_content_plan&& echo CJC_READ_ONLY_ROLLOUT_MODE=shadow&& echo CJC_READ_ONLY_ROLLOUT_CAPABILITIES=role_narration,presentation_content_plan&& langgraph dev --port 2034"
timeout /t 5 /nobreak >nul
start "LangSmith Studio" "https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2034"

echo LangGraph is running on http://127.0.0.1:2034
echo Close the server window to stop it.
