"""
Config Manager - Handles saving/loading user configuration
"""
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any


class ConfigManager:
    """Manages persistent configuration for the Wan2.2 Video Generator."""
    
    DEFAULT_CONFIG_PATH = "~/.wan2_gui_config.json"
    
    def __init__(self, config_path: str = None):
        """
        Initialize config manager.
        
        Args:
            config_path: Path to config file (default: ~/.wan2_gui_config.json)
        """
        self.config_path = os.path.expanduser(config_path or self.DEFAULT_CONFIG_PATH)
        self._config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """Load configuration from file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    self._config = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load config file: {e}")
                self._config = {}
        else:
            self._config = {}
    
    def _save_config(self):
        """Save configuration to file."""
        try:
            config_dir = os.path.dirname(self.config_path)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir)
            
            with open(self.config_path, 'w') as f:
                json.dump(self._config, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save config file: {e}")
    
    def save_ssh_config(
        self, 
        ssh_ip: str, 
        ssh_port: int, 
        ssh_key_path: str,
        vram_gb: Optional[int] = None,
        gpu_name: Optional[str] = None
    ):
        """
        Save SSH connection details.
        
        Args:
            ssh_ip: Pod IP address
            ssh_port: SSH port
            ssh_key_path: Path to SSH private key
            vram_gb: Detected GPU VRAM in GB
            gpu_name: Detected GPU name
        """
        self._config['ssh'] = {
            'ip': ssh_ip,
            'port': int(ssh_port),
            'key_path': ssh_key_path,
            'last_connected': datetime.now().isoformat()
        }
        
        if vram_gb is not None:
            self._config['gpu'] = {
                'vram_gb': vram_gb,
                'name': gpu_name,
                'detected_at': datetime.now().isoformat()
            }
        
        self._save_config()
    
    def load_ssh_config(self) -> Dict[str, Any]:
        """
        Load saved SSH configuration.
        
        Returns:
            Dict with 'ip', 'port', 'key_path' keys, or empty dict if not found
        """
        return self._config.get('ssh', {})
    
    def get_gpu_info(self) -> Dict[str, Any]:
        """
        Get saved GPU information.
        
        Returns:
            Dict with 'vram_gb', 'name' keys, or empty dict if not found
        """
        return self._config.get('gpu', {})
    
    def save_runpod_api_key(self, api_key: str):
        """
        Save RunPod API key.
        
        Args:
            api_key: RunPod API key
        """
        if 'runpod' not in self._config:
            self._config['runpod'] = {}
        
        self._config['runpod']['api_key'] = api_key
        self._save_config()
    
    def load_runpod_api_key(self) -> str:
        """
        Load saved RunPod API key.
        
        Returns:
            API key string, or empty string if not found
        """
        return self._config.get('runpod', {}).get('api_key', '')
    
    def save_generation_history(
        self,
        prompt: str,
        model: str,
        duration: int,
        resolution: str,
        seed: int,
        output_path: Optional[str] = None,
        success: bool = True
    ):
        """
        Save video generation to history.
        
        Args:
            prompt: Video prompt used
            model: Model used (e.g., 'ti2v-5b')
            duration: Video duration in seconds
            resolution: Resolution used (e.g., '720P')
            seed: Random seed used
            output_path: Path to generated video
            success: Whether generation succeeded
        """
        if 'history' not in self._config:
            self._config['history'] = []
        
        entry = {
            'prompt': prompt,
            'model': model,
            'duration': duration,
            'resolution': resolution,
            'seed': seed,
            'output_path': output_path,
            'success': success,
            'timestamp': datetime.now().isoformat()
        }
        
        # Keep only last 50 entries
        self._config['history'].insert(0, entry)
        self._config['history'] = self._config['history'][:50]
        
        self._save_config()
    
    def get_generation_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent generation history.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of generation history entries
        """
        history = self._config.get('history', [])
        return history[:limit]
    
    def save_model_status(self, model_key: str, downloaded: bool, download_path: Optional[str] = None):
        """
        Save model download status.
        
        Args:
            model_key: Model identifier (e.g., 'ti2v-5b')
            downloaded: Whether model is downloaded
            download_path: Path where model is stored
        """
        if 'models' not in self._config:
            self._config['models'] = {}
        
        self._config['models'][model_key] = {
            'downloaded': downloaded,
            'path': download_path,
            'updated_at': datetime.now().isoformat()
        }
        
        self._save_config()
    
    def get_model_status(self, model_key: str) -> Dict[str, Any]:
        """
        Get model download status.
        
        Args:
            model_key: Model identifier
            
        Returns:
            Dict with 'downloaded', 'path' keys, or empty dict if not found
        """
        return self._config.get('models', {}).get(model_key, {})
    
    def save_setup_status(self, setup_complete: bool, setup_steps: Optional[Dict[str, bool]] = None):
        """
        Save Wan2.2 setup status.
        
        Args:
            setup_complete: Whether full setup is complete
            setup_steps: Dict of individual setup steps and their status
        """
        self._config['setup'] = {
            'complete': setup_complete,
            'steps': setup_steps or {},
            'updated_at': datetime.now().isoformat()
        }
        self._save_config()
    
    def get_setup_status(self) -> Dict[str, Any]:
        """
        Get Wan2.2 setup status.
        
        Returns:
            Dict with 'complete', 'steps' keys
        """
        return self._config.get('setup', {'complete': False, 'steps': {}})
    
    def save_preference(self, key: str, value: Any):
        """Save a user preference."""
        if 'preferences' not in self._config:
            self._config['preferences'] = {}
        self._config['preferences'][key] = value
        self._save_config()
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference."""
        return self._config.get('preferences', {}).get(key, default)
    
    def clear_config(self):
        """Clear all configuration."""
        self._config = {}
        self._save_config()
    
    def get_all_config(self) -> Dict[str, Any]:
        """Get entire configuration dict."""
        return self._config.copy()
