@echo off
setlocal

set "BRANCH=%~1"
if "%BRANCH%"=="" set "BRANCH=dev"
set "DEPLOY_PASSWORD="
if exist "%~dp0deploy.password.txt" (
    set /p DEPLOY_PASSWORD=<"%~dp0deploy.password.txt"
)

for /f "delims=" %%i in ('git branch --show-current 2^>nul') do set "CURRENT_BRANCH=%%i"
if not defined CURRENT_BRANCH (
    echo Unable to determine the current git branch.
    exit /b 1
)

echo [1/4] Building latest client package...
call "%~dp0build-client.bat"
if errorlevel 1 (
    echo Client build failed. Deployment aborted.
    exit /b %errorlevel%
)

echo [2/4] Capturing latest local changes for deployment...
git add -A
if errorlevel 1 (
    echo Failed to stage local changes.
    exit /b %errorlevel%
)

git diff --cached --quiet
if errorlevel 1 (
    set "DEPLOY_TIMESTAMP=%DATE% %TIME%"
    git commit -m "deploy: snapshot %DEPLOY_TIMESTAMP%"
    if errorlevel 1 (
        echo Failed to create deployment snapshot commit.
        exit /b %errorlevel%
    )
) else (
    echo No local file changes detected after build. Reusing current HEAD.
)

echo [3/4] Pushing current HEAD from "%CURRENT_BRANCH%" to origin/%BRANCH%...
git push origin HEAD:%BRANCH%
if errorlevel 1 (
    echo Git push to origin/%BRANCH% failed.
    exit /b %errorlevel%
)

echo [4/4] Deploying latest server branch "%BRANCH%"...
if defined DEPLOY_PASSWORD (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\deploy_remote.ps1" -User root -Branch "%BRANCH%" -Password "%DEPLOY_PASSWORD%"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\deploy_remote.ps1" -User root -Branch "%BRANCH%"
)
if errorlevel 1 (
    echo Server deployment failed.
    exit /b %errorlevel%
)

echo Client build, local snapshot commit, push, and server deployment completed successfully.
