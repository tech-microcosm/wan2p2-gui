"""
Model Manager - Handles lazy model downloading and availability
"""
import re
from typing import Callable, Dict, List, Optional, Any
from .ssh_manager import SSHManager
from .gpu_manager import GPUManager


class ModelManager:
    """Manage model downloads and availability with lazy loading."""
    
    MODEL_PATHS = {
        'ti2v-5b': '/root/Wan2.2-TI2V-5B',
        't2v-a14b': '/root/Wan2.2-T2V-A14B',
        'i2v-a14b': '/root/Wan2.2-I2V-A14B',
        's2v-14b': '/root/Wan2.2-S2V-14B'
    }
    
    HF_REPOS = {
        'ti2v-5b': 'Wan-AI/Wan2.2-TI2V-5B',
        't2v-a14b': 'Wan-AI/Wan2.2-T2V-A14B',
        'i2v-a14b': 'Wan-AI/Wan2.2-I2V-A14B',
        's2v-14b': 'Wan-AI/Wan2.2-S2V-14B'
    }
    
    def __init__(self, ssh_manager: SSHManager, gpu_manager: Optional[GPUManager] = None):
        """
        Initialize model manager.
        
        Args:
            ssh_manager: SSHManager instance for remote operations
            gpu_manager: GPUManager instance (created if not provided)
        """
        self.ssh = ssh_manager
        self.gpu_manager = gpu_manager or GPUManager(ssh_manager)
    
    def check_model_exists(self, model_key: str) -> bool:
        """
        Check if model weights exist and are complete on remote pod.
        Validates actual model files, not just directory existence.
        
        Args:
            model_key: Model identifier (e.g., 'ti2v-5b')
            
        Returns:
            True if model is fully downloaded and complete
        """
        if model_key not in self.MODEL_PATHS:
            return False
        
        model_path = self.MODEL_PATHS[model_key]
        
        # Check if directory exists
        if not self.ssh.dir_exists(model_path):
            return False
        
        # Wan2.2 models have a specific structure with these key files/directories:
        # - diffusion_pytorch_model*.safetensors (in subdirectories)
        # - Wan2.1_VAE.pth (VAE weights)
        # - models_t5_umt5-xxl-enc-bf16.pth (T5 encoder)
        # - high_noise_model/ and low_noise_model/ directories
        
        # Check for key indicators of a complete Wan2.2 model download
        validation_checks = [
            # Check for VAE file (common across all models)
            f"test -f {model_path}/Wan2.1_VAE.pth",
            # Check for T5 encoder
            f"test -f {model_path}/models_t5_umt5-xxl-enc-bf16.pth",
            # Check for model directories with actual weights
            f"test -d {model_path}/high_noise_model || test -d {model_path}/t2v_14B",
        ]
        
        try:
            # Run all checks
            for check_cmd in validation_checks:
                exit_code, stdout, stderr = self.ssh.execute_command(check_cmd, timeout=5)
                if exit_code != 0:
                    return False
            
            # Additional check: verify at least one large safetensors file exists (>100MB)
            find_cmd = f"find {model_path} -name '*.safetensors' -size +100M 2>/dev/null | head -1"
            exit_code, stdout, stderr = self.ssh.execute_command(find_cmd, timeout=10)
            if exit_code == 0 and stdout.strip():
                return True
            
            # Alternative: check for .pth files > 100MB (some models use .pth)
            find_pth_cmd = f"find {model_path} -name '*.pth' -size +100M 2>/dev/null | head -1"
            exit_code, stdout, stderr = self.ssh.execute_command(find_pth_cmd, timeout=10)
            if exit_code == 0 and stdout.strip():
                return True
                
            return False
            
        except Exception:
            return False
    
    def get_downloaded_models(self) -> List[str]:
        """
        Get list of models that are already downloaded.
        
        Returns:
            List of model keys that are downloaded
        """
        downloaded = []
        for model_key in self.MODEL_PATHS:
            if self.check_model_exists(model_key):
                downloaded.append(model_key)
        return downloaded
    
    def get_available_models(self, vram_gb: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get models user can select based on VRAM, with download status.
        
        Args:
            vram_gb: Available VRAM in GB
            
        Returns:
            List of model info dicts with 'downloaded' status
        """
        viable = self.gpu_manager.get_viable_models(vram_gb)
        
        result = []
        for model_key, specs in viable:
            info = specs.copy()
            info['key'] = model_key
            info['downloaded'] = self.check_model_exists(model_key)
            info['path'] = self.MODEL_PATHS.get(model_key)
            result.append(info)
        
        return result
    
    def cleanup_incomplete_model(self, model_key: str, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Remove incomplete/corrupted model directory to allow fresh download.
        Called when model check fails or download is interrupted.
        
        Args:
            model_key: Model identifier
            progress_callback: Callback for progress updates
            
        Returns:
            True if cleanup successful
        """
        if model_key not in self.MODEL_PATHS:
            return False
        
        model_path = self.MODEL_PATHS[model_key]
        
        try:
            if progress_callback:
                progress_callback(f"🧹 Cleaning up incomplete {model_key} model...")
            
            # Remove the incomplete directory
            exit_code, stdout, stderr = self.ssh.execute_command(
                f"rm -rf {model_path}",
                timeout=30
            )
            
            if exit_code == 0:
                if progress_callback:
                    progress_callback(f"✅ Cleaned up incomplete model directory")
                return True
            else:
                if progress_callback:
                    progress_callback(f"⚠️ Could not fully clean model directory: {stderr}")
                return False
                
        except Exception as e:
            if progress_callback:
                progress_callback(f"⚠️ Cleanup error: {str(e)}")
            return False
    
    def download_model(
        self, 
        model_key: str, 
        progress_callback: Optional[Callable[[str], None]] = None,
        force_redownload: bool = False
    ) -> bool:
        """
        Download model from HuggingFace.
        
        Args:
            model_key: Model identifier
            progress_callback: Callback for progress updates
            force_redownload: If True, remove incomplete model and re-download
            
        Returns:
            True if download successful
        """
        if model_key not in self.HF_REPOS:
            if progress_callback:
                progress_callback(f"❌ Unknown model: {model_key}")
            return False
        
        # Check if model already exists and is complete
        if self.check_model_exists(model_key) and not force_redownload:
            if progress_callback:
                progress_callback(f"✅ Model {model_key} already downloaded")
            return True
        
        # If model directory exists but is incomplete, clean it up first
        if self.ssh.dir_exists(self.MODEL_PATHS[model_key]):
            if progress_callback:
                progress_callback(f"⚠️ Found incomplete {model_key} model, cleaning up...")
            self.cleanup_incomplete_model(model_key, progress_callback)
        
        repo = self.HF_REPOS[model_key]
        model_path = self.MODEL_PATHS[model_key]
        model_specs = self.gpu_manager.MODELS.get(model_key, {})
        
        if progress_callback:
            progress_callback(f"📥 Downloading {model_specs.get('name', model_key)}...")
            progress_callback(f"   Size: ~{model_specs.get('file_size_gb', 'Unknown')}GB")
            progress_callback(f"   Estimated time: ~{model_specs.get('download_time_min', 'Unknown')} minutes")
            progress_callback(f"   Source: huggingface.co/{repo}")
        
        # Use huggingface_hub to download (as in diffusion-lab guide)
        cmd = f"""
cd /root && \\
pip install -q --break-system-packages huggingface_hub && \\
python3 << 'EOF'
from huggingface_hub import snapshot_download
import os
print('Starting download from HuggingFace...')
snapshot_download('{repo}', local_dir='{model_path}')
print('Download complete!')
# List downloaded files for debugging
if os.path.exists('{model_path}'):
    files = os.listdir('{model_path}')
    print(f'Files in {model_path}: {{len(files)}} items')
    for f in sorted(files)[:10]:
        print(f'  - {{f}}')
EOF
"""
        
        def parse_progress(line: str):
            if progress_callback:
                # Filter and format progress messages
                if 'Downloading' in line or '%' in line or 'complete' in line.lower() or 'Files in' in line or '  -' in line:
                    progress_callback(f"   {line}")
                elif 'error' in line.lower() or 'failed' in line.lower():
                    progress_callback(f"   ⚠️ {line}")
        
        exit_code, stdout, stderr = self.ssh.execute_command(cmd, progress_callback=parse_progress)
        
        if exit_code != 0:
            if progress_callback:
                progress_callback(f"❌ Download failed: {stderr}")
            return False
        
        # Verify download - first check what files exist
        if progress_callback:
            progress_callback(f"\n🔍 Verifying downloaded files...")
        
        # List actual files in the directory
        list_cmd = f"ls -lh {model_path} 2>/dev/null | head -20"
        exit_code, stdout, stderr = self.ssh.execute_command(list_cmd)
        if exit_code == 0 and progress_callback:
            progress_callback(f"   Directory contents:\n{stdout}")
        
        # Check if model is valid
        if self.check_model_exists(model_key):
            if progress_callback:
                progress_callback(f"✅ Model {model_key} downloaded successfully!")
            return True
        else:
            if progress_callback:
                progress_callback(f"❌ Download completed but model validation failed at {model_path}")
                progress_callback(f"   This may mean the model files are in a subdirectory or have different names")
                progress_callback(f"   Attempting to find and reorganize model files...")
            
            # Try to find model files in subdirectories
            return self._reorganize_model_files(model_key, model_path, progress_callback)
    
    def _reorganize_model_files(self, model_key: str, model_path: str, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Diagnose and attempt to fix model file structure issues.
        For Wan2.2 models, the structure should be:
        - Wan2.1_VAE.pth (485MB)
        - models_t5_umt5-xxl-enc-bf16.pth (11GB)
        - high_noise_model/ or low_noise_model/ (with .safetensors files inside)
        
        Args:
            model_key: Model identifier
            model_path: Expected model path
            progress_callback: Callback for progress updates
            
        Returns:
            True if model is valid after any fixes
        """
        try:
            if progress_callback:
                progress_callback(f"   Diagnosing Wan2.2 model structure...")
            
            # Check what files exist
            has_vae = False
            has_t5 = False
            has_safetensors = False
            
            # Check VAE
            vae_cmd = f"test -f {model_path}/Wan2.1_VAE.pth && stat -c%s {model_path}/Wan2.1_VAE.pth"
            exit_code, stdout, _ = self.ssh.execute_command(vae_cmd, timeout=5)
            if exit_code == 0 and stdout.strip():
                vae_size = int(stdout.strip())
                has_vae = vae_size > 400000000  # > 400MB
                if progress_callback:
                    progress_callback(f"   VAE: {'✓' if has_vae else '✗'} ({vae_size // 1000000}MB)")
            
            # Check T5
            t5_cmd = f"test -f {model_path}/models_t5_umt5-xxl-enc-bf16.pth && stat -c%s {model_path}/models_t5_umt5-xxl-enc-bf16.pth"
            exit_code, stdout, _ = self.ssh.execute_command(t5_cmd, timeout=5)
            if exit_code == 0 and stdout.strip():
                t5_size = int(stdout.strip())
                has_t5 = t5_size > 10000000000  # > 10GB
                if progress_callback:
                    progress_callback(f"   T5:  {'✓' if has_t5 else '✗'} ({t5_size // 1000000000}GB)")
            
            # Check for safetensors files
            safetensors_cmd = f"find {model_path} -name '*.safetensors' -size +10M 2>/dev/null | wc -l"
            exit_code, stdout, _ = self.ssh.execute_command(safetensors_cmd, timeout=15)
            if exit_code == 0 and stdout.strip():
                safetensors_count = int(stdout.strip())
                has_safetensors = safetensors_count > 0
                if progress_callback:
                    progress_callback(f"   Safetensors: {'✓' if has_safetensors else '✗'} ({safetensors_count} files)")
            
            # Determine if model is complete
            if has_vae and has_t5 and has_safetensors:
                if progress_callback:
                    progress_callback(f"✅ Model {model_key} structure is complete!")
                return True
            
            # Model is incomplete - explain what's missing
            if progress_callback:
                missing = []
                if not has_vae:
                    missing.append("VAE weights")
                if not has_t5:
                    missing.append("T5 encoder")
                if not has_safetensors:
                    missing.append("diffusion model weights (safetensors)")
                
                progress_callback(f"   ⚠️ Model incomplete. Missing: {', '.join(missing)}")
                progress_callback(f"   The download may have been interrupted.")
                progress_callback(f"   Cleaning up and will re-download on next attempt...")
            
            # Clean up incomplete model
            self.cleanup_incomplete_model(model_key, progress_callback)
            
            return False
            
        except Exception as e:
            if progress_callback:
                progress_callback(f"⚠️ Validation error: {str(e)}")
            return False
    
    def ensure_model_downloaded(
        self, 
        model_key: str, 
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Ensure model is downloaded, downloading if necessary.
        Automatically detects and recovers from interrupted downloads.
        
        Args:
            model_key: Model identifier
            progress_callback: Callback for progress updates
            
        Returns:
            True if model is available
        """
        # First check if model is complete and ready
        if self.check_model_exists(model_key):
            if progress_callback:
                progress_callback(f"✅ Model {model_key} is ready")
            return True
        
        # Model doesn't exist or is incomplete
        # If directory exists but model check failed, it's incomplete - clean it up
        if self.ssh.dir_exists(self.MODEL_PATHS[model_key]):
            if progress_callback:
                progress_callback(f"⚠️ Found incomplete {model_key} model from previous attempt")
                progress_callback(f"   Cleaning up and re-downloading...")
            self.cleanup_incomplete_model(model_key, progress_callback)
        
        # Download the model
        return self.download_model(model_key, progress_callback)
    
    def get_model_path(self, model_key: str) -> Optional[str]:
        """Get the path where model is stored."""
        return self.MODEL_PATHS.get(model_key)
    
    def get_model_task_name(self, model_key: str) -> Optional[str]:
        """
        Get task name for generate.py command.
        
        Args:
            model_key: Model identifier (e.g., 'ti2v-5b')
            
        Returns:
            Task name (e.g., 'ti2v-5B')
        """
        model_info = self.gpu_manager.MODELS.get(model_key)
        if model_info:
            return model_info.get('task_name')
        return None
    
    def get_ckpt_dir(self, model_key: str) -> str:
        """
        Get checkpoint directory path for generate.py.
        
        Args:
            model_key: Model identifier
            
        Returns:
            Relative path to checkpoint directory
        """
        # Map model keys to directory names
        dir_names = {
            'ti2v-5b': 'Wan2.2-TI2V-5B',
            't2v-a14b': 'Wan2.2-T2V-A14B',
            'i2v-a14b': 'Wan2.2-I2V-A14B',
            's2v-14b': 'Wan2.2-S2V-14B'
        }
        return f"/root/{dir_names.get(model_key, model_key)}"
    
    def get_i2v_model_for_continuation(self, t2v_model: str) -> str:
        """
        Get the I2V model to use for video continuation.
        
        For T2V-A14B, use I2V-A14B for continuation.
        For TI2V-5B, it supports both T2V and I2V, so use itself.
        
        Args:
            t2v_model: The T2V model being used
            
        Returns:
            Model key for I2V continuation
        """
        if t2v_model == 't2v-a14b':
            return 'i2v-a14b'
        elif t2v_model == 'ti2v-5b':
            return 'ti2v-5b'  # TI2V supports I2V mode
        else:
            return 'i2v-a14b'  # Default fallback
    
    def get_model_sizes(self) -> Dict[str, str]:
        """Get model download sizes for display."""
        return {
            'ti2v-5b': '~32GB',
            't2v-a14b': '~27GB',
            'i2v-a14b': '~27GB'
        }
    
    def delete_model(
        self, 
        model_key: str, 
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Delete a downloaded model to free space.
        
        Args:
            model_key: Model identifier
            progress_callback: Callback for progress updates
            
        Returns:
            True if deletion successful
        """
        if model_key not in self.MODEL_PATHS:
            if progress_callback:
                progress_callback(f"❌ Unknown model: {model_key}")
            return False
        
        model_path = self.MODEL_PATHS[model_key]
        
        if not self.check_model_exists(model_key):
            if progress_callback:
                progress_callback(f"⚠️ Model {model_key} not found")
            return True
        
        if progress_callback:
            progress_callback(f"🗑️ Deleting model {model_key}...")
        
        exit_code, _, stderr = self.ssh.execute_command(f"rm -rf {model_path}")
        
        if exit_code == 0:
            if progress_callback:
                progress_callback(f"✅ Model {model_key} deleted")
            return True
        else:
            if progress_callback:
                progress_callback(f"❌ Failed to delete: {stderr}")
            return False
