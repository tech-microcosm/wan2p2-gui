#!/bin/bash
# Test script for Wan2.2 Video Generator Desktop App

echo "🧪 Testing Wan2.2 Video Generator Desktop App"
echo "=============================================="
echo ""

# Check if AppImage exists
APPIMAGE="./src-tauri/target/release/bundle/appimage/Wan2.2 Video Generator_0.1.0_amd64.AppImage"

if [ ! -f "$APPIMAGE" ]; then
    echo "❌ AppImage not found at: $APPIMAGE"
    exit 1
fi

echo "✅ AppImage found"
echo "📦 Size: $(du -h "$APPIMAGE" | cut -f1)"
echo ""

# Make executable
chmod +x "$APPIMAGE"

echo "🚀 Launching Wan2.2 Video Generator..."
echo ""
echo "Expected behavior:"
echo "  1. Tauri window opens"
echo "  2. Loading screen shows 'Launching backend...'"
echo "  3. Python backend starts (may take 10-30 seconds)"
echo "  4. Window redirects to Gradio UI"
echo ""
echo "Note: This will fail in WSL without X11/display server."
echo "      For WSL testing, you need WSLg or X11 forwarding."
echo ""
echo "Press Ctrl+C to cancel, or Enter to continue..."
read

# Try to launch
"$APPIMAGE"
