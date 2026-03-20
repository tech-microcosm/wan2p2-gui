"""
SSH Key Manager - Auto-detect and manage SSH keys
"""
import os
from pathlib import Path
from typing import List, Dict, Optional


class SSHKeyManager:
    """Automatically detect and manage SSH keys for the user."""
    
    # Common SSH key names in order of preference
    COMMON_KEY_NAMES = [
        'id_ed25519',      # Modern, preferred
        'id_rsa',          # RSA, widely supported
        'id_ecdsa',        # ECDSA
        'id_dsa',          # DSA (legacy)
    ]
    
    # Common SSH key locations
    COMMON_SSH_DIRS = [
        '~/.ssh',
        '~/.ssh/keys',
        '~/keys',
    ]
    
    @staticmethod
    def expand_path(path: str) -> str:
        """Expand user home and environment variables."""
        return os.path.expandvars(os.path.expanduser(path))
    
    @staticmethod
    def get_default_ssh_dir() -> str:
        """Get the default SSH directory."""
        return SSHKeyManager.expand_path('~/.ssh')
    
    @classmethod
    def find_available_keys(cls) -> List[Dict[str, str]]:
        """
        Find all available SSH keys on the system.
        
        Returns:
            List of dicts with 'name', 'path', 'type' keys, sorted by preference
        """
        available_keys = []
        ssh_dir = cls.get_default_ssh_dir()
        
        if not os.path.exists(ssh_dir):
            return available_keys
        
        # Check for common key names
        for key_name in cls.COMMON_KEY_NAMES:
            key_path = os.path.join(ssh_dir, key_name)
            if os.path.isfile(key_path):
                # Check if it's a private key (not .pub)
                try:
                    with open(key_path, 'r') as f:
                        first_line = f.readline()
                        if 'PRIVATE KEY' in first_line:
                            available_keys.append({
                                'name': key_name,
                                'path': key_path,
                                'display': f"{key_name} ({key_path})",
                                'type': cls._get_key_type(key_name)
                            })
                except (IOError, UnicodeDecodeError):
                    pass
        
        return available_keys
    
    @staticmethod
    def _get_key_type(key_name: str) -> str:
        """Get the type of SSH key from its name."""
        if 'ed25519' in key_name:
            return 'ED25519'
        elif 'rsa' in key_name:
            return 'RSA'
        elif 'ecdsa' in key_name:
            return 'ECDSA'
        elif 'dsa' in key_name:
            return 'DSA'
        return 'Unknown'
    
    @classmethod
    def get_default_key_path(cls) -> Optional[str]:
        """
        Get the path to the default/preferred SSH key.
        
        Returns:
            Path to the best available key, or None if no keys found
        """
        keys = cls.find_available_keys()
        if keys:
            return keys[0]['path']
        return None
    
    @classmethod
    def get_key_choices(cls) -> List[tuple]:
        """
        Get SSH key choices for Gradio dropdown.
        
        Returns:
            List of (display_name, path) tuples
        """
        keys = cls.find_available_keys()
        choices = [(key['display'], key['path']) for key in keys]
        
        # Add manual entry option
        choices.append(("Enter custom path...", "custom"))
        
        return choices if choices else [("Enter custom path...", "custom")]
    
    @staticmethod
    def validate_key_file(key_path: str) -> tuple[bool, str]:
        """
        Validate that a file is a valid SSH private key.
        
        Args:
            key_path: Path to the key file
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        expanded_path = SSHKeyManager.expand_path(key_path)
        
        if not os.path.exists(expanded_path):
            return False, f"Key file not found: {expanded_path}"
        
        if not os.path.isfile(expanded_path):
            return False, f"Path is not a file: {expanded_path}"
        
        try:
            with open(expanded_path, 'r') as f:
                content = f.read()
                if 'PRIVATE KEY' not in content:
                    return False, "File does not appear to be a private key"
        except (IOError, UnicodeDecodeError) as e:
            return False, f"Could not read key file: {str(e)}"
        
        # Check permissions (should not be world-readable)
        import sys
        if sys.platform != 'win32':
            mode = os.stat(expanded_path).st_mode
            if mode & 0o077:
                return False, f"SSH key has insecure permissions (should be 600). Run: chmod 600 {expanded_path}"
        
        return True, ""
    
    @staticmethod
    def get_key_info(key_path: str) -> Dict[str, str]:
        """
        Get information about an SSH key.
        
        Args:
            key_path: Path to the key file
            
        Returns:
            Dict with 'type', 'bits', 'fingerprint' info
        """
        expanded_path = SSHKeyManager.expand_path(key_path)
        info = {'path': expanded_path}
        
        try:
            with open(expanded_path, 'r') as f:
                first_line = f.readline()
                if 'ED25519' in first_line:
                    info['type'] = 'ED25519'
                elif 'RSA' in first_line:
                    info['type'] = 'RSA'
                elif 'ECDSA' in first_line:
                    info['type'] = 'ECDSA'
                else:
                    info['type'] = 'Unknown'
        except Exception:
            info['type'] = 'Unknown'
        
        return info
    
    @staticmethod
    def get_public_key_content(private_key_path: str) -> Optional[str]:
        """
        Read the public key content for a given private key path.
        Looks for the .pub file alongside the private key.
        
        Returns:
            Public key content string, or None if not found
        """
        expanded_path = SSHKeyManager.expand_path(private_key_path)
        pub_path = expanded_path + '.pub'
        
        if os.path.isfile(pub_path):
            try:
                with open(pub_path, 'r') as f:
                    return f.read().strip()
            except (IOError, UnicodeDecodeError):
                return None
        return None
    
    @classmethod
    def get_system_default_key(cls) -> Optional[Dict[str, str]]:
        """
        Get the system's default SSH key (auto-detected).
        
        Returns:
            Dict with key info, or None if no keys found
        """
        keys = cls.find_available_keys()
        if keys:
            key = keys[0]
            pub_content = cls.get_public_key_content(key['path'])
            key['public_key'] = pub_content
            return key
        return None
