@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Tori.ps1"
if errorlevel 1 pause
