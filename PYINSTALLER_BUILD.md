# PyInstaller Build Guide - Wan2.2 Video Generator GUI

This document explains how to build standalone executables for the Wan2.2 Video Generator GUI using PyInstaller.

## Overview

PyInstaller bundles your Python application and all its dependencies into a single executable that can run on machines without Python installed.

**Phase 1 Output:** Standalone executable with Python backend bundled
**Phase 2 (Next):** Desktop wrapper with Electron/Tauri for native window management

## Prerequisites

- Python 3.10+
- All dependencies from `requirements.txt` installed
- PyInstaller: `pip install pyinstaller`

## Build Instructions

### Linux/macOS

```bash
# Make the build script executable
chmod +x build_executable.sh

# Run the build
./build_executable.sh
```

### Windows

```bash
# Run the batch script
build_executable.bat
```

## What Gets Bundled

The PyInstaller spec file (`wan2p2_gui.spec`) includes:

### Core Dependencies
- **Gradio**: Web UI framework
- **Paramiko & SCP**: SSH/SFTP for pod connections
- **Cryptography**: SSH key handling
- **Transformers & PyTorch**: LLM prompt enhancement
- **Requests & aiohttp**: HTTP/async networking

### Data Files
- Gradio templates and assets
- Transformers model configs
- Hugging Face Hub data
- Certifi SSL certificates

### Excluded (to reduce size)
- Jupyter, IPython, Notebook
- Matplotlib, SciPy, Scikit-learn
- Testing frameworks (pytest, sphinx)
- Development tools (setuptools, pip, wheel)

## Output Structure

```
dist/wan2p2-gui/
├── wan2p2-gui          (Linux/macOS executable)
├── wan2p2-gui.exe      (Windows executable)
├── _internal/          (Python runtime and libraries)
├── base_library.zip    (Python standard library)
└── [other dependencies]
```

## Running the Executable

### Linux/macOS
```bash
./dist/wan2p2-gui/wan2p2-gui
```

### Windows
```bash
dist\wan2p2-gui\wan2p2-gui.exe
```

The application will:
1. Start the Python backend (Gradio server)
2. Open your default browser to `http://localhost:7860`
3. Display the Wan2.2 Video Generator GUI

## Creating Distribution Packages

### Linux (tar.gz)
```bash
cd dist
tar -czf wan2p2-gui-linux-x86_64.tar.gz wan2p2-gui/
```

### macOS (zip)
```bash
cd dist
zip -r wan2p2-gui-macos-universal.zip wan2p2-gui/
```

### Windows (zip)
```bash
cd dist
tar -a -c -f wan2p2-gui-windows-x86_64.zip wan2p2-gui/
# Or use 7-Zip/WinRAR GUI
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'X'"

**Solution:** Add the module to `hidden_imports` in `wan2p2_gui.spec`:

```python
hidden_imports = [
    'your_module_name',
    # ... other imports
]
```

Then rebuild:
```bash
pyinstaller --clean --noconfirm wan2p2_gui.spec
```

### Executable is too large (>500MB)

**Solution:** The bundle includes all dependencies. This is normal for Gradio + ML apps.

To reduce size:
1. Remove unused packages from `requirements.txt`
2. Add more packages to `excludes` in the spec file
3. Use `--onefile` mode (slower startup, single file)

### Application hangs on startup

**Solution:** Check the console output for errors. Common issues:
- Missing SSH key file
- Network connectivity issues
- GPU driver problems (if running on pod)

### "Failed to execute script" error

**Solution:** 
1. Check that all dependencies are installed: `pip install -r requirements.txt`
2. Verify the spec file has all required hidden imports
3. Try rebuilding with `--debug=imports` flag:
   ```bash
   pyinstaller --debug=imports wan2p2_gui.spec
   ```

## Advanced Options

### Single-File Executable

To create a single `.exe`/executable file instead of a folder:

Edit `wan2p2_gui.spec` and change the EXE section:
```python
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='wan2p2-gui',
    onefile=True,  # Add this line
    # ... rest of options
)
```

**Note:** Single-file mode is slower to start (unpacks to temp directory each time).

### Code Signing (macOS)

To sign the application for distribution:

```bash
codesign --deep --force --verify --verbose --sign "Developer ID Application" dist/wan2p2-gui/wan2p2-gui
```

### Custom Icon

Add an icon to the executable:

1. Create a `.ico` file (Windows) or `.icns` file (macOS)
2. Edit `wan2p2_gui.spec`:
   ```python
   exe = EXE(
       # ...
       icon='path/to/icon.ico',  # Add this line
   )
   ```
3. Rebuild

## Next Steps: Phase 2 - Desktop Wrapper

After Phase 1 (PyInstaller bundling), Phase 2 will wrap this executable with:

- **Electron** or **Tauri** for native window management
- Auto-launch of Python backend
- Professional desktop app appearance
- System tray integration
- Auto-updates capability

This will create a true desktop application that users can install like any other app.

## Support

For PyInstaller issues, see: https://pyinstaller.org/en/stable/

For Gradio-specific issues, see: https://gradio.app/

For project issues, see: https://github.com/tech-microcosm/wan2p2-gui/issues
