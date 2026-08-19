@echo off
title OfficeMitra Setup
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\gui-install.ps1"
if errorlevel 1 pause
