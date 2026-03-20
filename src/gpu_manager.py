"""
GPU Manager - Detect GPU VRAM and determine viable models
"""
import re
from typing import Dict, List, Optional, Tuple, Any
from .ssh_manager import SSHManager


class GPUManager:
    """Detect GPU VRAM and determine viable models based on available resources."""
    
    MODELS: Dict[str, Dict[str, Any]] = {
        'ti2v-5b': {
            'name': 'TI2V-5B (Fast)',
            'task_name': 'ti2v-5B',
            'hf_repo': 'Wan-AI/Wan2.2-TI2V-5B',
            'vram_min': 24,
            'vram_optimal': 40,
            'file_size_gb': 32,
            'download_time_min': 15,
            'speed_2s': '~1.5 min',
            'speed_5s': '~3 min',
            'speed_10s': '~6 min',
            'quality': 'Good',
            'supports_t2v': True,
            'supports_i2v': True,
            'description': 'Fast, good quality. Best for quick iterations and testing.',
            'resolutions': {
                24: ['480P'],
                40: ['480P', '720P'],
                80: ['480P', '720P', '1080P']
            }
        },
        't2v-a14b': {
            'name': 'T2V-A14B (High Quality)',
            'task_name': 't2v-A14B',
            'hf_repo': 'Wan-AI/Wan2.2-T2V-A14B',
            'vram_min': 40,
            'vram_optimal': 80,
            'file_size_gb': 27,
            'download_time_min': 12,
            'speed_2s': '~3 min',
            'speed_5s': '~6-7 min',
            'speed_10s': '~12-14 min',
            'quality': 'Excellent',
            'supports_t2v': True,
            'supports_i2v': False,
            'description': 'High quality text-to-video. Best for final renders.',
            'resolutions': {
                40: ['480P'],
                80: ['480P', '720P', '1080P']
            }
        },
        'i2v-a14b': {
            'name': 'I2V-A14B (Image-to-Video)',
            'task_name': 'i2v-A14B',
            'hf_repo': 'Wan-AI/Wan2.2-I2V-A14B',
            'vram_min': 60,
            'vram_optimal': 96,
            'vram_actual_requirement': 60,
            'file_size_gb': 27,
            'download_time_min': 12,
            'speed_2s': '~4 min',
            'speed_5s': '~8-10 min',
            'speed_10s': '~16-20 min',
            'quality': 'Excellent',
            'supports_t2v': False,
            'supports_i2v': True,
            'requires_image': True,
            'requires_audio': False,
            'description': 'Image-to-video generation. Requires 60GB+ VRAM (tested OOM on 48GB).',
            'oom_warning': 'I2V-A14B requires 60-80GB VRAM even with full offloading. Tested to OOM on 48GB RTX6000 Ada.',
            'resolutions': {
                60: ['480P'],
                96: ['480P', '720P', '1080P']
            }
        },
        's2v-14b': {
            'name': 'S2V-14B (Speech-to-Video)',
            'task_name': 's2v-14B',
            'hf_repo': 'Wan-AI/Wan2.2-S2V-14B',
            'vram_min': 40,
            'vram_optimal': 80,
            'file_size_gb': 30,
            'download_time_min': 15,
            'speed_2s': '~5 min',
            'speed_5s': '~10-12 min',
            'speed_10s': None,  # Not supported for 10s stitching
            'quality': 'Excellent',
            'supports_t2v': False,
            'supports_i2v': False,
            'supports_s2v': True,
            'requires_image': True,
            'requires_audio': True,
            'description': 'Speech-to-video generation. Creates talking head videos from image + audio.',
            'resolutions': {
                40: ['480P'],
                80: ['480P', '720P']
            }
        }
    }
    
    # Resolution options - based on actual Wan2.2 SUPPORTED_SIZES
    # TI2V-5B supports: 704*1280, 1280*704
    # T2V/I2V-A14B support: 720*1280, 1280*720, 480*832, 832*480
    # S2V-14B supports: 1024*704, 704*1024 (same as A14B)
    RESOLUTIONS = {
        # TI2V-5B resolutions (most common model)
        '1280x704 (Landscape)': {'width': 1280, 'height': 704, 'size_str': '1280*704', 'aspect': 'landscape', 'models': ['ti2v-5b']},
        '704x1280 (Portrait)': {'width': 704, 'height': 1280, 'size_str': '704*1280', 'aspect': 'portrait', 'models': ['ti2v-5b']},
        # T2V/I2V-A14B resolutions
        '1280x720 (Landscape)': {'width': 1280, 'height': 720, 'size_str': '1280*720', 'aspect': 'landscape', 'models': ['t2v-a14b', 'i2v-a14b']},
        '720x1280 (Portrait)': {'width': 720, 'height': 1280, 'size_str': '720*1280', 'aspect': 'portrait', 'models': ['t2v-a14b', 'i2v-a14b']},
        '832x480 (Landscape)': {'width': 832, 'height': 480, 'size_str': '832*480', 'aspect': 'landscape', 'models': ['t2v-a14b', 'i2v-a14b']},
        '480x832 (Portrait)': {'width': 480, 'height': 832, 'size_str': '480*832', 'aspect': 'portrait', 'models': ['t2v-a14b', 'i2v-a14b']},
        # S2V-14B resolutions
        '1024x704 (Landscape)': {'width': 1024, 'height': 704, 'size_str': '1024*704', 'aspect': 'landscape', 'models': ['s2v-14b']},
        '704x1024 (Portrait)': {'width': 704, 'height': 1024, 'size_str': '704*1024', 'aspect': 'portrait', 'models': ['s2v-14b']},
    }
    
    # Default resolution for each model
    DEFAULT_RESOLUTIONS = {
        'ti2v-5b': '704x1280 (Portrait)',
        't2v-a14b': '480x832 (Portrait)',
        'i2v-a14b': '480x832 (Portrait)',
        's2v-14b': '704x1024 (Portrait)',
    }
    
    def __init__(self, ssh_manager: Optional[SSHManager] = None):
        """
        Initialize GPU manager.
        
        Args:
            ssh_manager: SSHManager instance for remote GPU detection
        """
        self.ssh = ssh_manager
        self._cached_vram: Optional[int] = None
        self._cached_gpu_name: Optional[str] = None
    
    def set_ssh_manager(self, ssh_manager: SSHManager):
        """Set the SSH manager for remote operations."""
        self.ssh = ssh_manager
        self._cached_vram = None
        self._cached_gpu_name = None
    
    def detect_gpu(self) -> Tuple[Optional[int], Optional[str]]:
        """
        Detect GPU VRAM and name from remote pod.
        
        Returns:
            Tuple of (vram_gb, gpu_name) or (None, None) if detection fails
        """
        if not self.ssh:
            return None, None
        
        # Get GPU memory
        exit_code, stdout, stderr = self.ssh.execute_command(
            "nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits"
        )
        
        if exit_code != 0:
            return None, None
        
        try:
            # Parse VRAM in MB, convert to GB
            vram_mb = int(stdout.strip().split('\n')[0])
            vram_gb = vram_mb // 1024
            self._cached_vram = vram_gb
        except (ValueError, IndexError):
            return None, None
        
        # Get GPU name
        exit_code, stdout, stderr = self.ssh.execute_command(
            "nvidia-smi --query-gpu=name --format=csv,noheader"
        )
        
        if exit_code == 0:
            self._cached_gpu_name = stdout.strip().split('\n')[0]
        
        return self._cached_vram, self._cached_gpu_name
    
    def get_vram(self) -> Optional[int]:
        """Get cached VRAM value or detect it."""
        if self._cached_vram is None:
            self.detect_gpu()
        return self._cached_vram
    
    def get_gpu_name(self) -> Optional[str]:
        """Get cached GPU name or detect it."""
        if self._cached_gpu_name is None:
            self.detect_gpu()
        return self._cached_gpu_name
    
    def get_viable_models(self, vram_gb: Optional[int] = None) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Get models viable for the given VRAM.
        
        Args:
            vram_gb: Available VRAM in GB. If None, uses cached value.
            
        Returns:
            List of (model_key, model_specs) tuples for viable models
        """
        if vram_gb is None:
            vram_gb = self.get_vram()
        
        if vram_gb is None:
            return []
        
        viable = []
        for model_key, specs in self.MODELS.items():
            if vram_gb >= specs['vram_min']:
                viable.append((model_key, specs))
        
        return viable
    
    def is_model_viable(self, model_key: str, vram_gb: Optional[int] = None) -> bool:
        """Check if a specific model is viable for the given VRAM."""
        if vram_gb is None:
            vram_gb = self.get_vram()
        
        if vram_gb is None or model_key not in self.MODELS:
            return False
        
        return vram_gb >= self.MODELS[model_key]['vram_min']
    
    def get_recommended_model(self, vram_gb: Optional[int] = None, duration_sec: int = 5) -> Optional[str]:
        """
        Pre-select best model based on GPU and intended duration.
        
        Args:
            vram_gb: Available VRAM in GB
            duration_sec: Intended video duration in seconds
            
        Returns:
            Recommended model key or None if no viable models
        """
        if vram_gb is None:
            vram_gb = self.get_vram()
        
        if vram_gb is None:
            return None
        
        if vram_gb >= 80:
            # H100 or better: use highest quality
            return 't2v-a14b'
        elif vram_gb >= 40:
            # RTX 6000 Ada: T2V-A14B at 480P for quality, TI2V-5B for speed
            if duration_sec <= 5:
                return 't2v-a14b'  # Can use at 480P
            else:
                return 'ti2v-5b'  # Safer for longer videos
        else:
            # 24GB: only TI2V-5B
            return 'ti2v-5b'
    
    def get_viable_resolutions(self, model_key: str, vram_gb: Optional[int] = None) -> List[str]:
        """
        Get viable resolutions for a model based on Wan2.2 SUPPORTED_SIZES.
        
        Args:
            model_key: Model identifier
            vram_gb: Available VRAM in GB
            
        Returns:
            List of viable resolution strings for the model
        """
        # Filter resolutions by model compatibility
        viable = []
        for res_name, res_info in self.RESOLUTIONS.items():
            if model_key in res_info.get('models', []):
                viable.append(res_name)
        
        # If no model-specific resolutions, return all (fallback)
        if not viable:
            viable = list(self.RESOLUTIONS.keys())
        
        return viable
    
    def get_recommended_resolution(self, model_key: str, vram_gb: Optional[int] = None) -> Optional[str]:
        """
        Get recommended resolution for model.
        
        Args:
            model_key: Model identifier
            vram_gb: Available VRAM in GB (not used, kept for compatibility)
            
        Returns:
            Recommended resolution string for the model
        """
        # Use model-specific default resolution
        return self.DEFAULT_RESOLUTIONS.get(model_key, '1280x704 (Landscape)')
    
    def get_resolution_size(self, resolution: str) -> str:
        """
        Convert resolution name to size string for generate.py.
        
        Args:
            resolution: Resolution name (e.g., '1280x704 (Landscape)')
            
        Returns:
            Size string (e.g., '1280*704')
        """
        # Handle new format
        if resolution in self.RESOLUTIONS:
            return self.RESOLUTIONS[resolution]['size_str']
        
        # Handle legacy format for backwards compatibility
        legacy_map = {
            '480P': '832*480',
            '720P': '1280*720',
            '1080P': '1920*1080'
        }
        if resolution in legacy_map:
            return legacy_map[resolution]
        
        # Default fallback
        return '1280*704'
    
    def get_model_info(self, model_key: str) -> Optional[Dict[str, Any]]:
        """Get full model specifications."""
        return self.MODELS.get(model_key)
    
    def get_model_display_info(self, model_key: str, vram_gb: Optional[int] = None) -> str:
        """
        Get formatted model information for display.
        
        Args:
            model_key: Model identifier
            vram_gb: Available VRAM for resolution recommendations
            
        Returns:
            Formatted string with model details
        """
        if model_key not in self.MODELS:
            return "Unknown model"
        
        specs = self.MODELS[model_key]
        recommended_res = self.get_recommended_resolution(model_key, vram_gb)
        viable_res = self.get_viable_resolutions(model_key, vram_gb)
        
        info = f"""**{specs['name']}**

**Description:** {specs['description']}

**Requirements:**
- VRAM: {specs['vram_min']}GB minimum, {specs['vram_optimal']}GB optimal
- Model Size: {specs['file_size_gb']}GB
- Download Time: ~{specs['download_time_min']} minutes

**Generation Speed:**
- 2s video: {specs['speed_2s']}
- 5s video: {specs['speed_5s']}
- 10s video: {specs['speed_10s']}

**Quality:** {specs['quality']}

**Capabilities:**
- Text-to-Video: {'✅' if specs['supports_t2v'] else '❌'}
- Image-to-Video: {'✅' if specs['supports_i2v'] else '❌'}

**Available Resolutions:** {', '.join(viable_res) if viable_res else 'N/A'}
**Recommended Resolution:** {recommended_res or 'N/A'}
"""
        return info
    
    def get_duration_info(self, duration: int) -> Dict[str, Any]:
        """
        Get frame calculation info for a duration.
        
        Args:
            duration: Video duration in seconds (2, 5, or 10)
            
        Returns:
            Dict with frame_num, output_frames, method keys
        """
        if duration == 2:
            return {
                'frame_num': 25,
                'output_frames': 49,
                'rife_multi': 2,
                'segments': 1,
                'method': 'Direct generation + 2x RIFE interpolation'
            }
        elif duration == 5:
            return {
                'frame_num': 61,
                'output_frames': 121,
                'rife_multi': 2,
                'segments': 1,
                'method': 'Direct generation + 2x RIFE interpolation'
            }
        elif duration == 10:
            return {
                'frame_num': 61,
                'output_frames': 242,
                'rife_multi': 2,
                'segments': 2,
                'method': 'T2V segment + I2V continuation + RIFE + Stitching'
            }
        else:
            # Default to 5s
            return {
                'frame_num': 61,
                'output_frames': 121,
                'rife_multi': 2,
                'segments': 1,
                'method': 'Direct generation + 2x RIFE interpolation'
            }
