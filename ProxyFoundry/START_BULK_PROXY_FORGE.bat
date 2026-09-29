@echo off
setlocal
cd /d "%~dp0"
title Bulk Proxy Forge
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 "%~dp0START_BULK_PROXY_FORGE.pyw"
  exit /b 0
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "%~dp0START_BULK_PROXY_FORGE.pyw"
  exit /b 0
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0START_BULK_PROXY_FORGE.pyw"
  exit /b 0
)
powershell -NoProfile -WindowStyle Hidden -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('Install Python 3.10 or newer, then double-click START_BULK_PROXY_FORGE.bat again.','Bulk Proxy Forge')"
exit /b 1
