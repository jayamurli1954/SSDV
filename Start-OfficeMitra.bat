@echo off
title OfficeMitra
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-OfficeMitra.ps1"
pause
