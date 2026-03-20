@echo off
REM Build script for Wan2.2 Video Generator GUI (Windows)
REM Creates standalone executable using PyInstaller

setlocal enabledelayedexpansion

echo.
echo 🔨 Building Wan2.2 Video Generator GUI...
echo ==========================================

REM Check if PyInstaller is installed
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo ❌ PyInstaller not found. Installing...
    pip install pyinstaller
)

REM Clean previous builds
echo 🧹 Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist wan2p2-gui.build rmdir /s /q wan2p2-gui.build

REM Build the executable
echo 🏗️  Building executable...
pyinstaller --clean --noconfirm wan2p2_gui.spec

REM Check if build was successful
if exist "dist\wan2p2-gui" (
    echo.
    echo ✅ Build successful!
    echo.
    echo 📦 Output location: dist\wan2p2-gui\
    echo.
    echo To run the application:
    echo   dist\wan2p2-gui\wan2p2-gui.exe
    echo.
    echo To create a distributable package:
    echo   - Use 7-Zip or WinRAR to compress dist\wan2p2-gui\
    echo   - Or use: tar -a -c -f wan2p2-gui-windows.zip dist\wan2p2-gui\
) else (
    echo.
    echo ❌ Build failed. Check the output above for errors.
    exit /b 1
)

endlocal
