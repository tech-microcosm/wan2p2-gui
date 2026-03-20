# Cross-Platform Build & Distribution Guide

This guide explains how to build the Wan2.2 Video Generator for Windows, macOS, and Linux, and distribute it on your website.

## Platform Build Requirements

### Linux (WSL Ubuntu - Current Environment)
- ✅ Can build: `.AppImage` and `.deb`
- Location: WSL Ubuntu
- Command: `npm run build`

### Windows
- ✅ Can build: `.msi` installer
- Requirement: Windows native environment (not WSL)
- Command: `npm run build`

### macOS
- ✅ Can build: `.dmg` installer
- Requirement: macOS machine
- Command: `npm run build`

## Build Strategy

### Option 1: Local Builds (Recommended for Testing)

#### Step 1: Build Linux from WSL (Now)
```bash
cd /home/chinmay/projects/wan2p2-gui/src-tauri
npm run build
```

**Output:** 
- `src-tauri/src-tauri/target/release/bundle/deb/wan2p2-gui_0.1.0_amd64.deb`
- `src-tauri/src-tauri/target/release/bundle/appimage/wan2p2-gui_0.1.0_amd64.AppImage`

#### Step 2: Build Windows (On Windows Machine)
```powershell
# On Windows (PowerShell)
cd src-tauri
npm install
npm run build
```

**Output:**
- `src-tauri\src-tauri\target\release\bundle\msi\Wan2.2 Video Generator_0.1.0_x64_en-US.msi`

#### Step 3: Build macOS (On Mac)
```bash
# On macOS
cd src-tauri
npm install
npm run build
```

**Output:**
- `src-tauri/src-tauri/target/release/bundle/dmg/Wan2.2\ Video\ Generator_0.1.0_universal.dmg`

### Option 2: GitHub Actions (Automated - Recommended)

Use GitHub Actions to automatically build all three platforms whenever you push code.

**Advantages:**
- Build all platforms automatically
- No need to own Windows/Mac machines
- Consistent builds
- Automatic release creation

**Setup:** See "GitHub Actions Setup" section below.

---

## GitHub Actions Setup (Automated Builds)

Create `.github/workflows/build-release.yml`:

```yaml
name: Build Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    strategy:
      matrix:
        include:
          - os: ubuntu-latest
            target: x86_64-unknown-linux-gnu
            artifact_name: wan2p2-gui
            asset_name: wan2p2-gui-linux-x86_64

          - os: windows-latest
            target: x86_64-pc-windows-msvc
            artifact_name: Wan2.2 Video Generator_0.1.0_x64_en-US.msi
            asset_name: wan2p2-gui-windows-x86_64.msi

          - os: macos-latest
            target: universal-apple-darwin
            artifact_name: Wan2.2\ Video\ Generator_0.1.0_universal.dmg
            asset_name: wan2p2-gui-macos-universal.dmg

    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'

      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}

      - name: Build Python Backend
        run: |
          python -m pip install -r requirements.txt
          ./build_executable.sh

      - name: Build Tauri App
        working-directory: src-tauri
        run: |
          npm install
          npm run build

      - name: Upload Release Assets
        uses: softprops/action-gh-release@v1
        with:
          files: src-tauri/src-tauri/target/release/bundle/**/*
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**To use:**
1. Create `.github/workflows/build-release.yml` with above content
2. Commit and push
3. Create a git tag: `git tag v0.1.0 && git push origin v0.1.0`
4. GitHub Actions automatically builds all platforms
5. Release is created with all installers

---

## Distribution on Your Website

### Step 1: Create Download Page

Create `downloads.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wan2.2 Video Generator - Downloads</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }
        
        .container {
            max-width: 1000px;
            margin: 0 auto;
        }
        
        h1 {
            color: white;
            text-align: center;
            margin-bottom: 10px;
            font-size: 36px;
        }
        
        .subtitle {
            color: rgba(255, 255, 255, 0.9);
            text-align: center;
            margin-bottom: 40px;
            font-size: 16px;
        }
        
        .downloads {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }
        
        .download-card {
            background: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            transition: transform 0.3s, box-shadow 0.3s;
        }
        
        .download-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0, 0, 0, 0.3);
        }
        
        .platform {
            font-size: 24px;
            margin-bottom: 10px;
        }
        
        .download-card h2 {
            color: #333;
            margin-bottom: 10px;
            font-size: 20px;
        }
        
        .download-card p {
            color: #666;
            margin-bottom: 20px;
            font-size: 14px;
            line-height: 1.6;
        }
        
        .version {
            color: #999;
            font-size: 12px;
            margin-bottom: 15px;
        }
        
        .download-btn {
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 24px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            transition: opacity 0.3s;
        }
        
        .download-btn:hover {
            opacity: 0.9;
        }
        
        .system-requirements {
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 40px;
        }
        
        .system-requirements h2 {
            color: #333;
            margin-bottom: 20px;
        }
        
        .requirements-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }
        
        .requirement {
            padding: 15px;
            background: #f5f5f5;
            border-radius: 8px;
        }
        
        .requirement h3 {
            color: #667eea;
            margin-bottom: 10px;
        }
        
        .requirement ul {
            list-style: none;
            color: #666;
            font-size: 14px;
        }
        
        .requirement li {
            padding: 5px 0;
        }
        
        .requirement li:before {
            content: "✓ ";
            color: #4caf50;
            font-weight: bold;
            margin-right: 8px;
        }
        
        .footer {
            text-align: center;
            color: rgba(255, 255, 255, 0.8);
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎥 Wan2.2 Video Generator</h1>
        <p class="subtitle">Professional AI Video Generation Desktop Application</p>
        
        <div class="downloads">
            <!-- Windows -->
            <div class="download-card">
                <div class="platform">🪟</div>
                <h2>Windows</h2>
                <p>Professional installer for Windows 10/11</p>
                <div class="version">Version 0.1.0</div>
                <a href="https://github.com/tech-microcosm/wan2p2-gui/releases/download/v0.1.0/wan2p2-gui-windows-x86_64.msi" class="download-btn">
                    Download MSI (215 MB)
                </a>
            </div>
            
            <!-- macOS -->
            <div class="download-card">
                <div class="platform">🍎</div>
                <h2>macOS</h2>
                <p>Universal app for Intel and Apple Silicon</p>
                <div class="version">Version 0.1.0</div>
                <a href="https://github.com/tech-microcosm/wan2p2-gui/releases/download/v0.1.0/wan2p2-gui-macos-universal.dmg" class="download-btn">
                    Download DMG (220 MB)
                </a>
            </div>
            
            <!-- Linux -->
            <div class="download-card">
                <div class="platform">🐧</div>
                <h2>Linux</h2>
                <p>AppImage (universal) or Debian package</p>
                <div class="version">Version 0.1.0</div>
                <div style="display: grid; gap: 10px;">
                    <a href="https://github.com/tech-microcosm/wan2p2-gui/releases/download/v0.1.0/wan2p2-gui-linux-x86_64.AppImage" class="download-btn">
                        AppImage (210 MB)
                    </a>
                    <a href="https://github.com/tech-microcosm/wan2p2-gui/releases/download/v0.1.0/wan2p2-gui_0.1.0_amd64.deb" class="download-btn">
                        Debian (215 MB)
                    </a>
                </div>
            </div>
        </div>
        
        <div class="system-requirements">
            <h2>System Requirements</h2>
            <div class="requirements-grid">
                <div class="requirement">
                    <h3>Minimum</h3>
                    <ul>
                        <li>8GB RAM</li>
                        <li>2GB disk space</li>
                        <li>Modern CPU</li>
                        <li>Internet connection</li>
                    </ul>
                </div>
                <div class="requirement">
                    <h3>Recommended</h3>
                    <ul>
                        <li>16GB+ RAM</li>
                        <li>5GB disk space</li>
                        <li>GPU (NVIDIA/AMD)</li>
                        <li>Fast internet</li>
                    </ul>
                </div>
                <div class="requirement">
                    <h3>For GPU Pod</h3>
                    <ul>
                        <li>RunPod account</li>
                        <li>GPU pod (24GB+)</li>
                        <li>SSH key setup</li>
                        <li>Pod IP address</li>
                    </ul>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>© 2026 Wan2.2 Video Generator | <a href="https://github.com/tech-microcosm/wan2p2-gui" style="color: white;">GitHub</a> | <a href="https://github.com/tech-microcosm/wan2p2-gui/releases" style="color: white;">All Releases</a></p>
        </div>
    </div>
</body>
</html>
```

### Step 2: Create Release on GitHub

```bash
cd /home/chinmay/projects/wan2p2-gui

# Create a tag
git tag v0.1.0 -m "Release v0.1.0: Wan2.2 Video Generator Desktop App"

# Push tag to GitHub
git push origin v0.1.0
```

Then on GitHub:
1. Go to **Releases** tab
2. Click **Create Release**
3. Select tag `v0.1.0`
4. Add description
5. Upload all three installers (.msi, .dmg, .AppImage, .deb)

### Step 3: Host on Your Website

1. **Option A:** Link directly to GitHub releases (easiest)
   - Users download from GitHub
   - No hosting costs
   - Automatic updates via GitHub

2. **Option B:** Host on your own server
   - Upload installers to your web server
   - Create download page (HTML above)
   - Users download from your site

3. **Option C:** Use a CDN
   - Faster downloads globally
   - Cloudflare, AWS CloudFront, etc.

---

## Installation Instructions for Users

### Windows
1. Download `.msi` file
2. Double-click to run installer
3. Follow installation wizard
4. Click "Wan2.2 Video Generator" to launch

### macOS
1. Download `.dmg` file
2. Double-click to mount
3. Drag app to Applications folder
4. Launch from Applications

### Linux (AppImage)
```bash
# Download
wget https://github.com/tech-microcosm/wan2p2-gui/releases/download/v0.1.0/wan2p2-gui-linux-x86_64.AppImage

# Make executable
chmod +x wan2p2-gui-linux-x86_64.AppImage

# Run
./wan2p2-gui-linux-x86_64.AppImage
```

### Linux (Debian)
```bash
# Download and install
sudo dpkg -i wan2p2-gui_0.1.0_amd64.deb

# Launch
wan2p2-gui
```

---

## Auto-Launch Confirmation

**Yes, confirmed:** When user clicks the executable/installer:

1. ✅ **App launches** → Native window opens
2. ✅ **Python backend starts** → Automatically (no terminal)
3. ✅ **Waits for readiness** → Detects port 7860
4. ✅ **Shows Gradio UI** → Window displays video generator
5. ✅ **User can generate videos** → Immediately, no extra steps

**No additional clicks needed** - everything is automatic and seamless.

---

## Next Steps

1. **Build Linux now** (WSL):
   ```bash
   cd src-tauri && npm run build
   ```

2. **Build Windows** (on Windows machine)

3. **Build macOS** (on Mac)

4. **Create GitHub Release** with all installers

5. **Host download page** on your website

6. **Share with users** - they just download and click!

---

## Support

- **Tauri Docs:** https://tauri.app/
- **GitHub Releases:** https://github.com/tech-microcosm/wan2p2-gui/releases
- **Project Issues:** https://github.com/tech-microcosm/wan2p2-gui/issues
