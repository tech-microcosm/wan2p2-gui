"""
Utility functions for Wan2.2 Video Generator
"""
import os
import re
import sys
import tempfile
from datetime import datetime
from typing import Optional


def get_temp_dir() -> str:
    """Get temporary directory for downloads."""
    temp_dir = os.path.join(tempfile.gettempdir(), "wan2_gui")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def get_output_filename(duration: int, seed: int, extension: str = "mp4") -> str:
    """Generate a unique output filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"wan2_video_{duration}s_{seed}_{timestamp}.{extension}"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


def format_bytes(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def validate_prompt(prompt: str) -> tuple[bool, str]:
    """
    Validate a video generation prompt.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not prompt or not prompt.strip():
        return False, "Prompt cannot be empty"
    
    if len(prompt) < 10:
        return False, "Prompt is too short. Please provide more detail."
    
    if len(prompt) > 2000:
        return False, "Prompt is too long. Please keep it under 2000 characters."
    
    # Check for potentially problematic characters
    if any(char in prompt for char in ['`', '$(', '${', '\x00']):
        return False, "Prompt contains invalid characters"
    
    return True, ""


def expand_path(path: str) -> str:
    """Expand user home directory and environment variables in path."""
    return os.path.expandvars(os.path.expanduser(path))


def validate_ssh_key_path(path: str) -> tuple[bool, str]:
    """
    Validate SSH key path.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    expanded_path = expand_path(path)
    
    if not os.path.exists(expanded_path):
        return False, f"SSH key file not found: {expanded_path}"
    
    if not os.path.isfile(expanded_path):
        return False, f"Path is not a file: {expanded_path}"
    
    # Check file permissions (should not be world-readable)
    if sys.platform != 'win32':
        mode = os.stat(expanded_path).st_mode
        if mode & 0o077:
            return False, f"SSH key file has insecure permissions. Run: chmod 600 {expanded_path}"
    
    return True, ""


def validate_ip_address(ip: str) -> bool:
    """Validate IPv4 address format."""
    if not ip:
        return False
    
    # Simple IPv4 validation
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        return False
    
    # Check each octet
    octets = ip.split('.')
    for octet in octets:
        if int(octet) > 255:
            return False
    
    return True


def validate_port(port: int) -> bool:
    """Validate port number."""
    return 1 <= port <= 65535


def sanitize_filename(filename: str) -> str:
    """Sanitize a string for use as a filename."""
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove leading/trailing whitespace and dots
    filename = filename.strip('. ')
    
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    
    return filename or "untitled"


def get_model_display_name(model_key: str) -> str:
    """Get display name for a model key."""
    names = {
        'ti2v-5b': 'TI2V-5B (Fast)',
        't2v-a14b': 'T2V-A14B (High Quality)',
        'i2v-a14b': 'I2V-A14B (Continuation)'
    }
    return names.get(model_key, model_key)


def get_resolution_display(resolution: str) -> str:
    """Get display string for resolution."""
    info = {
        '480P': '480P (640×360) - Fast',
        '720P': '720P (1280×720) - Balanced',
        '1080P': '1080P (1920×1080) - High Quality'
    }
    return info.get(resolution, resolution)


def estimate_generation_time(model: str, duration: int, resolution: str) -> str:
    """Estimate generation time based on parameters."""
    # Base times for 5s 720P video
    base_times = {
        'ti2v-5b': 3,
        't2v-a14b': 7,
        'i2v-a14b': 10
    }
    
    base = base_times.get(model, 5)
    
    # Duration multiplier
    duration_mult = {2: 0.5, 5: 1.0, 10: 2.0}.get(duration, 1.0)
    
    # Resolution multiplier
    res_mult = {'480P': 0.6, '720P': 1.0, '1080P': 2.0}.get(resolution, 1.0)
    
    estimated = base * duration_mult * res_mult
    
    if estimated < 1:
        return "< 1 minute"
    elif estimated < 2:
        return "1-2 minutes"
    else:
        return f"~{int(estimated)} minutes"


def parse_progress_percentage(text: str) -> Optional[float]:
    """Extract progress percentage from text."""
    # Look for patterns like "50%", "50.5%", "step 10/20"
    
    # Percentage pattern
    pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
    if pct_match:
        return float(pct_match.group(1))
    
    # Step pattern (e.g., "step 10/20")
    step_match = re.search(r'(\d+)\s*/\s*(\d+)', text)
    if step_match:
        current, total = int(step_match.group(1)), int(step_match.group(2))
        if total > 0:
            return (current / total) * 100
    
    return None


def is_video_file(path: str) -> bool:
    """Check if a file is a video based on extension."""
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}
    _, ext = os.path.splitext(path.lower())
    return ext in video_extensions


def get_video_info_text(duration: int, model: str, resolution: str, seed: int) -> str:
    """Generate info text for a generated video."""
    return f"""**Video Details:**
- Duration: {duration} seconds
- Model: {get_model_display_name(model)}
- Resolution: {resolution}
- Seed: {seed}
"""
