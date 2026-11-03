@echo off
rem Double-click to set Brushtalk up on this PC, or to repair or update it. It runs setup.ps1, beside it.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
echo.
pause
