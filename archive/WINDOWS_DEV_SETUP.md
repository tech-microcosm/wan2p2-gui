# Windows Development Setup for Wan2.2 Video Generator

## Quick Setup on Windows (15 minutes)

### 1. Install Rust
Open PowerShell and run:
```powershell
# Download and run rustup installer
winget install --id Rustlang.Rustup
# OR visit: https://rustup.rs/
```

### 2. Install Node.js
```powershell
winget install --id OpenJS.NodeJS.LTS
```

### 3. Install Visual Studio Build Tools
Required for Rust compilation on Windows:
```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools
```
During installation, select:
- Desktop development with C++
- Windows 10 SDK

### 4. Install WebView2
Already installed on Windows 11. For Windows 10:
```powershell
winget install --id Microsoft.EdgeWebView2Runtime
```

### 5. Clone and Build
```powershell
# Clone repo
git clone https://github.com/tech-microcosm/wan2p2-gui.git
cd wan2p2-gui

# Install Python dependencies (for backend)
pip install -r requirements.txt

# Build Python backend
.\build_executable.bat

# Build and run Tauri app in dev mode (FASTER for testing)
cd src-tauri
cargo tauri dev
```

## Faster Testing - Dev Mode

Instead of building full installer every time:
```powershell
# In src-tauri directory
cargo tauri dev
```
This opens the app immediately with hot reload!

## Build Full Installer (slower)
```powershell
# From src-tauri directory
npm run build
# Installer will be in: src-tauri/target/release/bundle/msi/
```

## Debugging Tips

### View Console Logs
Dev mode shows all Rust `println!` output in terminal.

### Check if Multiple Processes
```powershell
# Check running processes
Get-Process | Where-Object {$_.ProcessName -like "*wan2p2*"}
```

### Kill All Instances
```powershell
# If things go wrong
Get-Process | Where-Object {$_.ProcessName -like "*wan2p2*"} | Stop-Process -Force
```

## Common Issues

### Build fails with missing tools
- Make sure Visual Studio Build Tools installed
- Restart PowerShell after installing Rust

### Port 7860 already in use
- Another instance running
- Kill with: `Get-Process python | Stop-Process -Force`

### Infinite windows
- Check terminal output for clues
- Windows are created in `main.rs` setup function
- Check browser console in dev mode (F12)
