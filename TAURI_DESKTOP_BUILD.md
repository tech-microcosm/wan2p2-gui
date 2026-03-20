# Phase 2: Tauri Desktop Wrapper - Build Guide

This document explains how to build the Tauri desktop application that wraps the Python backend.

## Overview

**Phase 1:** PyInstaller bundles Python backend into standalone executable (215MB)
**Phase 2:** Tauri wraps the executable in a native desktop app (~10MB)

### Why Tauri?
- **Bundle size:** ~10MB vs Electron's ~150MB (93% smaller!)
- **Memory usage:** 58% less RAM than Electron
- **Performance:** Uses OS native webview (no bundled Chromium)
- **Security:** Better isolation by default
- **Perfect for Python:** Just launches a subprocess and opens localhost URL

## Prerequisites

- Node.js 16+ and npm
- Rust 1.70+ (required for Tauri compilation)
- Python backend executable built from Phase 1 (`dist/wan2p2-gui/`)

### Install Rust (if not already installed)

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
```

## Project Structure

```
wan2p2-gui/
├── src-tauri/                    # Tauri Rust backend
│   ├── src/
│   │   ├── main.rs              # Rust app entry point
│   │   └── index.html           # Loading screen
│   ├── Cargo.toml               # Rust dependencies
│   ├── tauri.conf.json          # Tauri configuration
│   └── build.rs                 # Build script
├── dist/wan2p2-gui/             # Python backend (from Phase 1)
└── src-tauri/package.json       # Node.js configuration
```

## Build Instructions

### 1. Install Dependencies

```bash
cd src-tauri
npm install
```

### 2. Build Python Backend First

Make sure you've completed Phase 1:

```bash
cd ..
./build_executable.sh
```

This creates `dist/wan2p2-gui/` with the Python executable.

### 3. Build Desktop App

```bash
cd src-tauri
npm run build
```

This will:
1. Compile the Rust backend
2. Bundle the Python executable
3. Create native installers for your platform

### 4. Output

The built applications will be in `src-tauri/src-tauri/target/release/bundle/`:

- **Linux:** `.AppImage` and `.deb` files
- **macOS:** `.dmg` file
- **Windows:** `.msi` installer

## How It Works

### Startup Flow

1. **User launches app** → Tauri window opens
2. **Loading screen** → Shows "Launching backend..."
3. **Tauri spawns Python process** → Runs `dist/wan2p2-gui/wan2p2-gui`
4. **Python backend starts** → Gradio server on localhost:7860
5. **Tauri detects port 7860** → Knows backend is ready
6. **Redirects to localhost:7860** → Shows Gradio UI in native window
7. **User interacts with app** → All through native window

### Shutdown Flow

1. **User closes window** → Tauri captures close event
2. **Tauri kills Python process** → Clean shutdown
3. **App exits** → No orphaned processes

## Development

### Run in Development Mode

```bash
cd src-tauri
npm run dev
```

This will:
- Start Tauri in dev mode
- Open the app window
- Enable hot-reload for frontend changes
- Show Rust compilation errors

### Debug Mode

To see console output and debug info:

```bash
RUST_LOG=debug npm run dev
```

## Customization

### Change Window Size

Edit `src-tauri/tauri.conf.json`:

```json
"windows": [
  {
    "width": 1400,
    "height": 900,
    "minWidth": 800,
    "minHeight": 600
  }
]
```

### Change App Icon

Place icon files in `src-tauri/icons/`:
- `icon.png` (512x512)
- `icon.icns` (macOS)
- `icon.ico` (Windows)

Then rebuild:
```bash
npm run build
```

### Change App Name

Edit `src-tauri/tauri.conf.json`:
```json
{
  "productName": "Your App Name",
  "identifier": "com.yourcompany.appname"
}
```

## Troubleshooting

### "Rust not found"

Install Rust:
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

### "Python backend not found"

Make sure Phase 1 is complete:
```bash
./build_executable.sh
```

Check that `dist/wan2p2-gui/wan2p2-gui` exists.

### "Port 7860 already in use"

Another instance is running. Kill it:

```bash
# Linux/macOS
lsof -ti:7860 | xargs kill -9

# Windows
netstat -ano | findstr :7860
taskkill /PID <PID> /F
```

### "Compilation takes forever"

First build is slow (Rust compilation). Subsequent builds are faster.

To speed up development, use debug builds:
```bash
npm run dev  # Much faster than npm run build
```

### App window is blank

Check browser console (F12) for errors. The loading screen should show progress.

If stuck on "Launching backend...", the Python process may have failed to start.

## Distribution

### Create Installers

```bash
cd src-tauri
npm run build
```

### Linux

**AppImage** (portable, no installation):
```bash
dist/wan2p2-gui_0.1.0_amd64.AppImage
```

**Debian package** (for Ubuntu/Debian):
```bash
sudo dpkg -i dist/wan2p2-gui_0.1.0_amd64.deb
```

### macOS

**DMG installer** (drag-and-drop):
```bash
dist/Wan2.2\ Video\ Generator_0.1.0_universal.dmg
```

### Windows

**MSI installer**:
```bash
dist/Wan2.2 Video Generator_0.1.0_x64_en-US.msi
```

## Next Steps

After Phase 2 (Tauri desktop wrapper):

1. **Test on all platforms** (Windows, macOS, Linux)
2. **Create release packages** for distribution
3. **Set up auto-updates** (optional, Tauri supports this)
4. **Publish to app stores** (optional)

## Performance Comparison

| Metric | Tauri | Electron |
|--------|-------|----------|
| Bundle Size | ~10MB | ~150MB |
| Memory (idle) | ~50MB | ~120MB |
| Startup Time | ~1-2s | ~2-3s |
| Compilation | ~2-5 min | ~30s |

## Support

- **Tauri Docs:** https://tauri.app/
- **Tauri GitHub:** https://github.com/tauri-apps/tauri
- **Project Issues:** https://github.com/tech-microcosm/wan2p2-gui/issues

## License

MIT License - See LICENSE file in project root
