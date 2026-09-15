@echo off
setlocal
cd /d "%~dp0"
title MTG Card Pipeline Local UI

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -c "import PIL" >nul 2>&1
    if errorlevel 1 (
        echo Installing required Pillow image package...
        py -3 -m pip install --disable-pip-version-check Pillow
        if errorlevel 1 goto :pillow_error
    )
    py -3 local_pipeline_ui.py
    goto :done
)

where python >nul 2>&1
if %errorlevel%==0 (
    python -c "import PIL" >nul 2>&1
    if errorlevel 1 (
        echo Installing required Pillow image package...
        python -m pip install --disable-pip-version-check Pillow
        if errorlevel 1 goto :pillow_error
    )
    python local_pipeline_ui.py
    goto :done
)

echo.
echo ERROR: Python 3 was not found.
echo Install Python 3 from https://www.python.org/downloads/
echo During installation, check "Add python.exe to PATH".
echo.
goto :done

:pillow_error
echo.
echo ERROR: Pillow could not be installed.
echo Run: py -3 -m pip install Pillow
echo Then start the UI again.
echo.

:done
if not %errorlevel%==0 pause
endlocal
