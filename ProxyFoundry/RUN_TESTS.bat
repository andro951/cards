@echo off
setlocal
cd /d "%~dp0"
title Bulk Proxy Forge Tests
if not exist ".venv\Scripts\python.exe" (
  echo Start Bulk Proxy Forge once to create its isolated Python environment.
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
set "PF_LIVE_GITHUB_SETUP="
set "PF_LARGE_TRANSFER="
set "PF_LIVE_DECK_SITES="
set "TIMING_PRUNE="
echo.
echo 1 = Routine tests and deck-adapter checks
echo 2 = Extended browser/live/stress tests and live deck sites
echo 3 = Full sweep of both groups
choice /c 123 /n /m "Choose 1, 2 or 3: "
if errorlevel 3 goto full
if errorlevel 2 goto extended
set "PYTEST_SELECTOR=-m routine"
goto run
:extended
set "PYTEST_SELECTOR=-m extended"
goto browser_setup
:full
set "PYTEST_SELECTOR="
set "TIMING_PRUNE=--prune"
:browser_setup
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto failed
for /f "delims=" %%I in ('.venv\Scripts\python.exe -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); print(p.chromium.executable_path); p.stop()"') do set "PF_BROWSER_EXECUTABLE=%%I"
if not defined PF_BROWSER_EXECUTABLE goto failed
set "PF_DOM_EXECUTABLE=%PF_BROWSER_EXECUTABLE%"
set "PF_BROWSER=1"
set "PF_LIVE_CC=1"
set "PF_DOM=1"
set "PF_LIVE_GITHUB_SETUP=1"
set "PF_LARGE_TRANSFER=1"
set "PF_LIVE_DECK_SITES=1"
:run
".venv\Scripts\python.exe" -m pytest -q --tb=short %PYTEST_SELECTOR% --junitxml=test-results\local.xml
set "TEST_EXIT=%ERRORLEVEL%"
".venv\Scripts\python.exe" scripts\update_test_timings.py test-results\local.xml %TIMING_PRUNE%
if errorlevel 1 goto failed
if not "%TEST_EXIT%"=="0" goto failed
for %%F in (tests_web\*.test.mjs) do (
  node --test "%%F"
  if errorlevel 1 goto failed
)
echo.
echo All selected tests passed.
pause
exit /b 0
:failed
echo.
echo A test or setup step failed. Read the error above; test-results contains evidence when available.
pause
exit /b 1
