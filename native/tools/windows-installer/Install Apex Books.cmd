@echo off
rem Per-user install of Apex Books: no administrator rights needed.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 pause
