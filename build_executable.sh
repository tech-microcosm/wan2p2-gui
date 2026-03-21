#!/bin/bash
# Build script for Wan2.2 Video Generator GUI
# Creates standalone executable using PyInstaller

set -e  # Exit on error

echo "🔨 Building Wan2.2 Video Generator GUI..."
echo "=========================================="

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "❌ PyInstaller not found. Installing..."
    pip install pyinstaller
fi

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build dist wan2p2-gui.build

# Build the executable
echo "🏗️  Building executable..."
pyinstaller --clean --noconfirm wan2p2-gui.spec

# Check if build was successful
if [ -d "dist/wan2p2-gui" ]; then
    echo "✅ Build successful!"
    echo ""
    echo "📦 Output location: dist/wan2p2-gui/"
    echo ""
    echo "To run the application:"
    echo "  ./dist/wan2p2-gui/wan2p2-gui"
    echo ""
    echo "To create a distributable package:"
    echo "  - Linux: tar -czf wan2p2-gui-linux.tar.gz dist/wan2p2-gui/"
    echo "  - macOS: zip -r wan2p2-gui-macos.zip dist/wan2p2-gui/"
    echo "  - Windows: Use 7-Zip or WinRAR to compress dist/wan2p2-gui/"
else
    echo "❌ Build failed. Check the output above for errors."
    exit 1
fi
