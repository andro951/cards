@echo off
setlocal
cd /d "%~dp0"
title Bulk Proxy Forge
where py >nul 2>nul
if not errorlevel 1 (
  set "PYTHON=py -3"
) else (
  set "PYTHON=python"
)
%PYTHON% -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 or newer is required. Install Python from python.org with the launcher enabled.
  echo Then double-click this file again.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Preparing the isolated Bulk Proxy Forge environment...
  %PYTHON% -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "from PIL import Image" >nul 2>nul
if errorlevel 1 (
  echo Installing the image-processing dependency. No CardConjurer repository is downloaded.
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
echo Opening Bulk Proxy Forge. Your decks are stored outside this extracted app folder.
".venv\Scripts\python.exe" run.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Bulk Proxy Forge could not start. The error is shown above; your saved decks are unchanged.
pause
exit /b 1
