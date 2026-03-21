# Resources Directory

This directory is used to bundle the Python backend with the Tauri application.

During the build process:
- The PyInstaller-built Python backend (`dist/wan2p2-gui`) is copied here
- Tauri bundles everything in this directory into the final installer
- At runtime, the app looks for `resources/wan2p2-gui/wan2p2-gui.exe` relative to the executable

**Note:** This folder is populated during the build process by GitHub Actions or local builds.
