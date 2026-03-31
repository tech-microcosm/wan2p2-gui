"""Version checking and auto-update functionality."""

import sys
import requests
from packaging import version
from typing import Optional, Tuple

# Current app version - update this with each release
CURRENT_VERSION = "1.1.0"

def check_for_updates() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check if a new version is available on GitHub.
    
    Returns:
        Tuple of (update_available, latest_version, download_url)
    """
    # Skip version check when running from source (not frozen)
    if not getattr(sys, 'frozen', False):
        return False, None, None
    
    try:
        # Check GitHub releases API
        api_url = "https://api.github.com/repos/tech-microcosm/wan2p2-gui/releases/latest"
        response = requests.get(api_url, timeout=5)
        
        if response.status_code != 200:
            return False, None, None
        
        data = response.json()
        latest_version = data.get("tag_name", "").lstrip("v")
        
        if not latest_version:
            return False, None, None
        
        # Compare versions
        if version.parse(latest_version) > version.parse(CURRENT_VERSION):
            # Find the MSI installer asset
            download_url = None
            for asset in data.get("assets", []):
                if asset["name"].endswith(".msi"):
                    download_url = asset["browser_download_url"]
                    break
            
            return True, latest_version, download_url
        
        return False, None, None
        
    except Exception as e:
        # Silent fail - don't interrupt app startup
        print(f"Version check failed: {e}")
        return False, None, None


def get_current_version() -> str:
    """Get the current app version."""
    return CURRENT_VERSION
