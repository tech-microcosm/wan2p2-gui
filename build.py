#!/usr/bin/env python3
"""
PyInstaller Build Script for Wan2.2 Video Generator

This script packages the application into a single executable for Windows, macOS, and Linux.
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path


def get_platform():
    """Get the current platform."""
    if sys.platform == 'win32':
        return 'windows'
    elif sys.platform == 'darwin':
        return 'macos'
    else:
        return 'linux'


def clean_build():
    """Clean previous build artifacts."""
    dirs_to_clean = ['build', 'dist', '__pycache__']
    files_to_clean = ['*.spec']
    
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"Removing {dir_name}/")
            shutil.rmtree(dir_name)
    
    for pattern in files_to_clean:
        import glob
        for f in glob.glob(pattern):
            print(f"Removing {f}")
            os.remove(f)


def build_executable():
    """Build the executable using PyInstaller."""
    platform = get_platform()
    print(f"Building for platform: {platform}")
    
    # Base PyInstaller arguments
    args = [
        'src/main.py',
        '--name=Wan2VideoGenerator',
        '--onefile',
        '--windowed',
        '--noconfirm',
        '--clean',
        # Hidden imports needed by Gradio and Paramiko
        '--hidden-import=gradio',
        '--hidden-import=paramiko',
        '--hidden-import=scp',
        '--hidden-import=cryptography',
        '--hidden-import=bcrypt',
        '--hidden-import=nacl',
        '--hidden-import=cffi',
        # Collect all Gradio data files
        '--collect-all=gradio',
        '--collect-all=gradio_client',
        # Additional imports
        '--hidden-import=PIL',
        '--hidden-import=PIL._tkinter_finder',
    ]
    
    # Add assets if they exist
    if os.path.exists('assets'):
        if platform == 'windows':
            args.append('--add-data=assets;assets')
        else:
            args.append('--add-data=assets:assets')
    
    # Add scripts if they exist
    if os.path.exists('scripts'):
        if platform == 'windows':
            args.append('--add-data=scripts;scripts')
        else:
            args.append('--add-data=scripts:scripts')
    
    # Platform-specific icon
    if platform == 'windows' and os.path.exists('assets/icon.ico'):
        args.append('--icon=assets/icon.ico')
    elif platform == 'macos' and os.path.exists('assets/icon.icns'):
        args.append('--icon=assets/icon.icns')
    elif os.path.exists('assets/icon.png'):
        args.append(f'--icon=assets/icon.png')
    
    # Run PyInstaller
    print("Running PyInstaller...")
    print(f"Arguments: {' '.join(args)}")
    
    import PyInstaller.__main__
    PyInstaller.__main__.run(args)
    
    # Check if build succeeded
    if platform == 'windows':
        exe_path = 'dist/Wan2VideoGenerator.exe'
    else:
        exe_path = 'dist/Wan2VideoGenerator'
    
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n✅ Build successful!")
        print(f"   Executable: {exe_path}")
        print(f"   Size: {size_mb:.1f} MB")
        return True
    else:
        print(f"\n❌ Build failed - executable not found at {exe_path}")
        return False


def create_distribution():
    """Create a distribution package with README and license."""
    platform = get_platform()
    dist_dir = Path('dist')
    
    # Copy README if exists
    if os.path.exists('README.md'):
        shutil.copy('README.md', dist_dir / 'README.md')
        print("Copied README.md to dist/")
    
    # Create a simple run script for Linux/macOS
    if platform != 'windows':
        run_script = dist_dir / 'run.sh'
        with open(run_script, 'w') as f:
            f.write('#!/bin/bash\n')
            f.write('cd "$(dirname "$0")"\n')
            f.write('./Wan2VideoGenerator\n')
        os.chmod(run_script, 0o755)
        print("Created run.sh")
    
    print(f"\n📦 Distribution package ready in: {dist_dir.absolute()}")


def main():
    """Main build process."""
    print("=" * 60)
    print("Wan2.2 Video Generator - Build Script")
    print("=" * 60)
    
    # Check we're in the right directory
    if not os.path.exists('src/main.py'):
        print("❌ Error: Must run from project root directory")
        print("   Expected to find: src/main.py")
        sys.exit(1)
    
    # Check PyInstaller is installed
    try:
        import PyInstaller
        print(f"✅ PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("❌ PyInstaller not installed. Run: pip install pyinstaller")
        sys.exit(1)
    
    # Parse arguments
    if '--clean' in sys.argv:
        clean_build()
        if len(sys.argv) == 2:
            print("Clean complete.")
            return
    
    # Build
    print("\n📦 Building executable...")
    if build_executable():
        create_distribution()
        print("\n✅ Build complete!")
    else:
        print("\n❌ Build failed!")
        sys.exit(1)


if __name__ == '__main__':
    main()
