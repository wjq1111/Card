@echo off
setlocal

echo Running one-click master deployment: build client + deploy server...
call "%~dp0deploy.bat" master
exit /b %errorlevel%
