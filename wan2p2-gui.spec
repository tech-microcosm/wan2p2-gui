# -*- mode: python ; coding: utf-8 -*-


import os
from pathlib import Path

# Collect data files from packages
def get_package_data_files():
    datas = [('src', 'src')]
    
    # List of packages that may have version.txt or other data files
    packages_with_data = [
        'safehttpx',
        'groovy',
        'gradio',
        'gradio_client',
        'httpx',
        'fastapi',
        'starlette',
    ]
    
    # Collect version.txt files from packages
    for package_name in packages_with_data:
        try:
            package = __import__(package_name)
            package_path = Path(package.__file__).parent
            
            # Look for version.txt
            version_file = package_path / 'version.txt'
            if version_file.exists():
                datas.append((str(version_file), package_name))
                print(f"Added version.txt for {package_name}")
            
            # For gradio, include all source files and data directories
            if package_name == 'gradio':
                # Include entire gradio package as data (it needs runtime access to many files)
                datas.append((str(package_path), 'gradio'))
                print(f"Added entire gradio package as data files")
        except (ImportError, AttributeError):
            pass
    
    return datas

a = Analysis(
    ['src/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=get_package_data_files(),
    hiddenimports=[
        'gradio',
        'gradio.blocks',
        'gradio.components',
        'gradio.routes',
        'gradio_client',
        'paramiko',
        'scp',
        'cryptography',
        'requests',
        'tqdm',
        'runpod',
        'fastapi',
        'uvicorn',
        'starlette',
        'pydantic',
        'typing_extensions',
        'numpy',
        'pandas',
        'Pillow',
        'jinja2',
        'httpx',
        'websockets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='wan2p2-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='wan2p2-gui',
)
