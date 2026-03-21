@echo off
REM Wan2.2 Video Generator - Launch Script for Windows
REM This script kills any existing processes and launches the GUI in your browser

setlocal enabledelayedexpansion

echo.
echo 4D 56 69 64 65 6F 20 47 65 6E 65 72 61 74 6F 72
echo ==================================================
echo.

REM Kill any existing processes
echo Stopping any existing processes...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq*src.main*" >nul 2>&1 || true

REM Wait a moment
timeout /t 1 /nobreak >nul

REM Check if diffusion environment exists
if not exist "diffusion" (
    echo Error: 'diffusion' environment not found
    echo Please run setup first
    pause
    exit /b 1
)

REM Launch the GUI
echo.
echo Launching Wan2.2 Video Generator...
echo Opening browser at http://127.0.0.1:7860
echo.
echo Press Ctrl+C to stop the server
echo.

REM Launch in background
start "" diffusion\Scripts\python.exe -m src.main

REM Wait for server to start
timeout /t 3 /nobreak >nul

REM Open browser
start http://127.0.0.1:7860

REM Keep window open
pause
