@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Start Proxy Foundry once to set up its private Python environment.
  pause
  exit /b 1
)
echo Opening the unchanged Card Tools v58 interface for advanced legacy workflows.
cd /d "%~dp0vendor\card_tools"
"%~dp0.venv\Scripts\python.exe" local_pipeline_ui.py
if errorlevel 1 pause
