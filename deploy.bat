@echo off
setlocal

set "BRANCH=%~1"
if "%BRANCH%"=="" set "BRANCH=dev"

for /f "delims=" %%i in ('git branch --show-current 2^>nul') do set "CURRENT_BRANCH=%%i"
if not defined CURRENT_BRANCH (
    echo Unable to determine the current git branch.
    exit /b 1
)

git diff --quiet
if errorlevel 1 (
    echo Working tree has uncommitted changes. Commit them before deploy so the push-to-%BRANCH% step is reproducible.
    exit /b 1
)

git diff --cached --quiet
if errorlevel 1 (
    echo Index has staged but uncommitted changes. Commit them before deploy so the push-to-%BRANCH% step is reproducible.
    exit /b 1
)

echo [1/3] Building latest client package...
call "%~dp0build-client.bat"
if errorlevel 1 (
    echo Client build failed. Deployment aborted.
    exit /b %errorlevel%
)

echo [2/3] Pushing current HEAD from "%CURRENT_BRANCH%" to origin/%BRANCH%...
git push origin HEAD:%BRANCH%
if errorlevel 1 (
    echo Git push to origin/%BRANCH% failed.
    exit /b %errorlevel%
)

echo [3/3] Deploying latest server branch "%BRANCH%"...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\deploy_remote.ps1" -User root -Branch "%BRANCH%"
if errorlevel 1 (
    echo Server deployment failed.
    exit /b %errorlevel%
)

echo Client build, push, and server deployment completed successfully.
