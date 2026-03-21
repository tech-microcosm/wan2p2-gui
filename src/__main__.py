#!/usr/bin/env python3
"""
Entry point for PyInstaller to run the src package as a module.
This allows relative imports to work correctly.
"""
import sys
from pathlib import Path

# Ensure the parent directory is in the path so 'src' can be imported as a package
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Import and run the main module
from src import main

if __name__ == "__main__":
    # The main module will execute when imported
    pass
