@echo off
setlocal

set "BRANCH=%~1"
if "%BRANCH%"=="" set "BRANCH=dev"

echo [1/2] Building latest client package...
call "%~dp0build-client.bat"
if errorlevel 1 (
    echo Client build failed. Deployment aborted.
    exit /b %errorlevel%
)

echo [2/2] Deploying latest server branch "%BRANCH%"...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\deploy_remote.ps1" -User root -Branch "%BRANCH%"
if errorlevel 1 (
    echo Server deployment failed.
    exit /b %errorlevel%
)

echo Client build and server deployment completed successfully.
