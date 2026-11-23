@echo off
setlocal DisableDelayedExpansion
where.exe py.exe >nul 2>nul
if errorlevel 1 goto python
py -3 -X utf8 "%~dp0writing-assistant" %*
exit /b %errorlevel%
:python
python -X utf8 "%~dp0writing-assistant" %*
exit /b %errorlevel%
