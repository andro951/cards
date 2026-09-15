@echo off
setlocal
cd /d "%~dp0"
title Proxy Foundry Tests
if not exist ".venv\Scripts\python.exe" (
  echo Start Proxy Foundry once to create its isolated Python environment.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\verify_vendor.py
if errorlevel 1 goto failed
set "PF_BROWSER="
set "PF_LIVE_CC="
set "PF_DOM="
echo.
echo 1 = Core unit and local API tests (no Chromium download)
echo 2 = Full browser and genuine CardConjurer tests (requires network)
choice /c 12 /n /m "Choose 1 or 2: "
if errorlevel 2 (
  ".venv\Scripts\python.exe" -m playwright install chromium
  if errorlevel 1 goto failed
  set "PF_BROWSER=1"
  set "PF_LIVE_CC=1"
)
".venv\Scripts\python.exe" -m pytest -q --tb=short --junitxml=test-results\local.xml
if errorlevel 1 goto failed
echo.
echo All selected tests passed.
pause
exit /b 0
:failed
echo.
echo A test or setup step failed. Read the error above; test-results contains evidence when available.
pause
exit /b 1
