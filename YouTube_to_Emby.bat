@echo off
title YouTube to Emby Menu

:menu
cls
echo ========================================
echo    YouTube to Emby Tool Suite
echo ========================================
echo.
echo [1] Start Web Interface (Recommended)
echo [2] Start Desktop GUI
echo [3] Install Dependencies
echo [4] Help
echo [0] Exit
echo.
echo ========================================

set /p choice=Enter option (0-4): 

if "%choice%"=="1" goto web
if "%choice%"=="2" goto gui
if "%choice%"=="3" goto install
if "%choice%"=="4" goto help
if "%choice%"=="0" goto exit
goto invalid

:web
cls
echo ========================================
echo    Starting Web Interface...
echo ========================================
echo.

:: Check if app.py exists
if not exist "app.py" (
    echo [ERROR] app.py not found
    echo Please ensure you are in the correct project directory
    pause
    goto menu
)

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found
    echo Please install Python or run option [3] to install dependencies
    pause
    goto menu
)

echo [OK] Starting web server...
echo [INFO] Access URL: http://localhost:5000
echo [INFO] Press Ctrl+C to stop the server
echo ========================================
echo.

:: Start the web application
python app.py

echo.
echo [INFO] Web server stopped
pause
goto menu

:gui
cls
echo Starting Desktop GUI...
if exist "youtube_to_emby_gui.py" (
    python youtube_to_emby_gui.py
) else (
    echo GUI file not found
    pause
)
goto menu

:install
cls
echo ========================================
echo    Installing Dependencies...
echo ========================================
echo.

:: Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found
    echo.
    echo Please install Python 3.7 or higher:
    echo 1. Visit https://www.python.org/downloads/
    echo 2. Download the latest Python version
    echo 3. Check "Add Python to PATH" during installation
    echo 4. Run this script again
    echo.
    pause
    goto menu
)

echo [OK] Python is installed
python --version
echo.

:: Check pip
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pip not found
    echo Please reinstall Python with pip included
    pause
    goto menu
)

echo [OK] pip is installed
pip --version
echo.

:: Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip
echo.

:: Install dependencies
echo Installing project dependencies...
echo ----------------------------------------
pip install -r requirements.txt
echo.
echo Installing yt-dlp nightly version...
pip install --upgrade --pre yt-dlp
echo ----------------------------------------

if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] All dependencies installed successfully!
    echo.
    echo You can now start the application:
    echo   [1] Web Interface (Recommended)
    echo   [2] Desktop GUI
    echo.
) else (
    echo.
    echo [ERROR] Dependencies installation failed
    echo.
    echo Try these solutions:
    echo 1. Run this script as Administrator
    echo 2. Check your internet connection
    echo 3. Manually run: pip install -r requirements.txt
    echo.
)

pause
goto menu

:help
cls
echo ========================================
echo           Help Information
echo ========================================
echo.
echo Web Interface Version [1]:
echo   - Modern browser-based interface
echo   - Real-time progress monitoring
echo   - Remote access support
echo   - Access URL: http://localhost:5000
echo.
echo Desktop GUI Version [2]:
echo   - Traditional desktop application
echo   - Local operation, no browser needed
echo   - Modern Material Design interface
echo.
echo Install Dependencies [3]:
echo   - Installs all required Python packages
echo   - Updates yt-dlp to latest nightly version
echo   - Required for first-time setup
echo.
echo First Time Setup:
echo   1. Select [3] Install Dependencies
echo   2. Select [1] Start Web Interface (Recommended)
echo   or
echo   2. Select [2] Start Desktop GUI
echo.
echo Features:
echo   - YouTube video download
echo   - Automatic subtitle download
echo   - Emby NFO metadata generation
echo   - Thumbnail download
echo   - Multiple video formats (MP4/MKV)
echo.
pause
goto menu

:invalid
echo.
echo Invalid option, please try again
timeout /t 2 >nul
goto menu

:exit
echo.
echo Thank you for using YouTube to Emby Tool!
timeout /t 2 >nul
exit