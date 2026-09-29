@echo off
setlocal EnableExtensions

rem One-click launcher for Windows. The working directory is always the project folder.
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [1/3] Creating Python virtual environment...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv "%~dp0.venv"
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo Python 3 was not found. Install Python 3.10+ and try again.
            pause
            exit /b 1
        )
        python -m venv "%~dp0.venv"
    )
    if errorlevel 1 (
        echo Failed to create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Virtual environment is ready.
)

echo [2/3] Checking Python dependencies...
"%PYTHON%" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo Dependency installation failed. Check your network and try again.
    pause
    exit /b 1
)

if not exist "%~dp0.venv\.chromium-ready" (
    echo [3/3] Installing Playwright Chromium browser...
    "%PYTHON%" -m playwright install chromium
    if errorlevel 1 (
        echo Chromium installation failed. Check your network and try again.
        pause
        exit /b 1
    )
    >"%~dp0.venv\.chromium-ready" echo ready
) else (
    echo [3/3] Playwright Chromium is ready.
)

if not exist "%~dp0playlist.csv" if "%*"=="" (
    echo.
    echo No playlist.csv was found in the project folder.
    echo Export a playlist CSV, save it as playlist.csv, and double-click start.bat again.
    echo You can also pass a different file, for example:
    echo start.bat --csv C:\path\to\playlist.csv
    pause
    exit /b 2
)

echo.
echo Starting the downloader...
"%PYTHON%" "%~dp0gequhai_downloader.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

set "SKIP_CONVERSION=0"
for %%A in (%*) do (
    if /I "%%~A"=="--dry-run" set "SKIP_CONVERSION=1"
    if /I "%%~A"=="--help" set "SKIP_CONVERSION=1"
    if /I "%%~A"=="-h" set "SKIP_CONVERSION=1"
)
if not "%EXIT_CODE%"=="0" goto :skip_conversion
if "%SKIP_CONVERSION%"=="1" goto :skip_conversion

echo.
echo Converting downloaded .acc/.aac files to MP3 with FFmpeg...
"%PYTHON%" "%~dp0convert_aac_to_mp3.py" --dir "%~dp0downloads" --download-args %*
if errorlevel 1 set "EXIT_CODE=1"
goto :after_conversion

:skip_conversion
echo Skipping audio conversion for dry-run/help or failed download.

:after_conversion

echo.
if not "%EXIT_CODE%"=="0" echo Downloader exited with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
