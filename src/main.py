#!/usr/bin/env python3
"""
Wan2.2 Video Generator - Main Application Entry Point

A desktop GUI application for generating high-quality AI videos using Wan2.2 models
on RunPod GPU pods.
"""
import os
import sys
import time
import glob
import shutil
import threading
import tempfile
from typing import Optional, Tuple, Generator, List
from datetime import datetime, timedelta
from pathlib import Path

import gradio as gr

# Local outputs directory - use user's Documents folder to avoid permission issues in Program Files
if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle - use user's Documents folder
    OUTPUTS_DIR = Path.home() / "Documents" / "Wan2.2 Video Generator" / "outputs"
else:
    # Running in development mode - use project directory
    OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

from .ssh_manager import SSHManager
from .ssh_key_manager import SSHKeyManager
from .config_manager import ConfigManager
from .gpu_manager import GPUManager
from .model_manager import ModelManager
from .version_checker import check_for_updates, get_current_version
from .setup_manager import SetupManager
from .video_generator import VideoGenerator
from .runpod_manager import RunPodManager
from .utils import (
    validate_prompt, 
    validate_ssh_key_path, 
    validate_ip_address, 
    validate_port,
    expand_path,
    get_model_display_name,
    estimate_generation_time
)


# Global state
class AppState:
    """Global application state."""
    def __init__(self):
        self.ssh_manager: Optional[SSHManager] = None
        self.config_manager = ConfigManager()
        self.gpu_manager: Optional[GPUManager] = None
        self.model_manager: Optional[ModelManager] = None
        self.setup_manager: Optional[SetupManager] = None
        self.video_generator: Optional[VideoGenerator] = None
        self.runpod_manager: Optional[RunPodManager] = None
        self.current_pod_id: Optional[str] = None
        self.vram_gb: Optional[int] = None
        self.gpu_name: Optional[str] = None
        self.connected: bool = False
        self.setup_complete: bool = False
        self.app_start_time: datetime = datetime.now()
    
    def get_app_runtime(self) -> str:
        """Get formatted app runtime."""
        elapsed = datetime.now() - self.app_start_time
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

app_state = AppState()


# ===== LOCAL OUTPUTS MANAGEMENT =====

def get_local_outputs() -> List[dict]:
    """Get list of all local output files (videos and images)."""
    outputs = []
    
    # Get videos
    for ext in ['*.mp4', '*.webm', '*.avi']:
        for f in OUTPUTS_DIR.glob(ext):
            stat = f.stat()
            outputs.append({
                'name': f.name,
                'path': str(f),
                'type': 'video',
                'size_mb': stat.st_size / (1024 * 1024),
                'modified': datetime.fromtimestamp(stat.st_mtime)
            })
    
    # Get images
    for ext in ['*.png', '*.jpg', '*.jpeg', '*.webp']:
        for f in OUTPUTS_DIR.glob(ext):
            stat = f.stat()
            outputs.append({
                'name': f.name,
                'path': str(f),
                'type': 'image',
                'size_mb': stat.st_size / (1024 * 1024),
                'modified': datetime.fromtimestamp(stat.st_mtime)
            })
    
    # Sort by modification time (newest first)
    outputs.sort(key=lambda x: x['modified'], reverse=True)
    return outputs


def refresh_outputs_gallery() -> Tuple[List[str], List[str], str]:
    """Refresh the outputs gallery, returning videos, images, and status."""
    outputs = get_local_outputs()
    
    videos = [o['path'] for o in outputs if o['type'] == 'video']
    images = [o['path'] for o in outputs if o['type'] == 'image']
    
    video_count = len(videos)
    image_count = len(images)
    total_size = sum(o['size_mb'] for o in outputs)
    
    status = f"📁 **{video_count}** videos, **{image_count}** images ({total_size:.1f} MB total)"
    
    return videos, images, status


def save_video_to_outputs(video_path: str, save_last_frame: bool = False) -> Tuple[str, Optional[str]]:
    """
    Save a video to the outputs directory and optionally extract the last frame.
    
    Returns:
        Tuple of (saved_video_path, saved_frame_path or None)
    """
    if not video_path or not os.path.exists(video_path):
        return video_path, None
    
    # Generate unique filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_name = f"video_{timestamp}.mp4"
    output_video = OUTPUTS_DIR / video_name
    
    # Copy video to outputs
    shutil.copy2(video_path, output_video)
    
    frame_path = None
    if save_last_frame:
        try:
            import subprocess
            frame_name = f"frame_{timestamp}.png"
            frame_path = str(OUTPUTS_DIR / frame_name)
            
            # Use ffmpeg to extract last frame
            cmd = [
                'ffmpeg', '-sseof', '-0.1', '-i', str(output_video),
                '-update', '1', '-q:v', '2', '-frames:v', '1', frame_path, '-y'
            ]
            subprocess.run(cmd, capture_output=True, timeout=30)
            
            if not os.path.exists(frame_path):
                frame_path = None
        except Exception:
            frame_path = None
    
    return str(output_video), frame_path


def delete_output_file(file_path: str) -> str:
    """Delete a file from outputs directory."""
    try:
        path = Path(file_path)
        if path.exists() and OUTPUTS_DIR in path.parents or path.parent == OUTPUTS_DIR:
            path.unlink()
            return f"✅ Deleted: {path.name}"
        return "❌ File not found or not in outputs directory"
    except Exception as e:
        return f"❌ Error deleting file: {str(e)}"


def load_saved_config():
    """Load saved SSH configuration."""
    ssh_config = app_state.config_manager.load_ssh_config()
    gpu_info = app_state.config_manager.get_gpu_info()
    
    return (
        ssh_config.get('ip', ''),
        ssh_config.get('port', 22),
        ssh_config.get('key_path', '~/.ssh/id_ed25519'),
        gpu_info.get('vram_gb'),
        gpu_info.get('name')
    )


def fetch_available_gpus(api_key: str) -> Tuple[str, gr.Dropdown]:
    """Fetch available GPUs from RunPod API."""
    global app_state
    
    if not api_key or not api_key.strip():
        return "❌ Please enter your RunPod API key", gr.Dropdown(choices=[])
    
    try:
        # Save API key for future use
        app_state.config_manager.save_runpod_api_key(api_key)
        
        app_state.runpod_manager = RunPodManager(api_key)
        gpus = app_state.runpod_manager.get_available_gpus()
        
        if not gpus:
            return "⚠️ No suitable GPUs found (need >= 24GB VRAM)", gr.Dropdown(choices=[])
        
        # Format GPU choices for dropdown
        gpu_choices = []
        for gpu in gpus:
            name = gpu.get('displayName', 'Unknown')
            vram = gpu.get('vram_gb', 0)
            price = gpu.get('best_price', 0)
            price_type = gpu.get('best_price_type', 'N/A')
            available = gpu.get('available', False)
            
            status = "✅" if available else "❌"
            label = f"{status} {name} ({vram}GB VRAM) - ${price:.2f}/hr ({price_type})"
            
            gpu_choices.append((label, gpu.get('id')))
        
        return (
            f"✅ Found {len(gpus)} suitable GPUs\n\nSelect a GPU from the dropdown below and click 'Launch Pod & Auto-Setup'",
            gr.Dropdown(choices=gpu_choices, value=gpu_choices[0][1] if gpu_choices else None)
        )
        
    except Exception as e:
        return f"❌ Failed to fetch GPUs: {str(e)}", gr.Dropdown(choices=[])


def terminate_current_pod() -> str:
    """Terminate the current pod."""
    global app_state
    
    if not app_state.current_pod_id:
        return "⚠️ No active pod to terminate"
    
    try:
        if not app_state.runpod_manager:
            return "❌ RunPod manager not initialized"
        
        app_state.runpod_manager.terminate_pod(app_state.current_pod_id)
        pod_id = app_state.current_pod_id
        app_state.current_pod_id = None
        return f"✅ Pod {pod_id} terminated successfully"
    except Exception as e:
        return f"❌ Failed to terminate pod: {str(e)}"


def launch_pod_and_setup(
    api_key: str,
    gpu_type_id: str
) -> Generator[str, None, None]:
    """Launch RunPod pod and run automated setup."""
    global app_state
    
    if not api_key or not api_key.strip():
        yield "❌ Please enter your RunPod API key"
        return
    
    if not gpu_type_id:
        yield "❌ Please select a GPU type"
        return
    
    # Use default SSH key path
    ssh_key_path = SSHKeyManager.get_default_key_path() or "~/.ssh/id_ed25519"
    
    # Validate SSH key
    key_valid, key_error = validate_ssh_key_path(ssh_key_path)
    if not key_valid:
        yield f"❌ {key_error}"
        yield "\n⚠️ Make sure your SSH public key is added to RunPod settings:"
        yield "   1. Go to https://runpod.io/console/user/settings"
        yield "   2. Click 'SSH Public Keys' and add your public key"
        yield "   3. Your public key is typically at:"
        yield "      - Windows: C:\\Users\\YourName\\.ssh\\id_ed25519.pub"
        yield "      - macOS/Linux: ~/.ssh/id_ed25519.pub"
        return
    
    try:
        # Initialize RunPod manager
        if not app_state.runpod_manager:
            app_state.runpod_manager = RunPodManager(api_key)
        
        yield "🚀 Creating GPU pod on RunPod..."
        
        # Create pod
        pod_name = f"wan2-gui-{int(time.time())}"
        try:
            pod_id, pod_info = app_state.runpod_manager.create_pod(
                name=pod_name,
                gpu_type_id=gpu_type_id,
                gpu_count=1,
                container_disk_gb=150,
                volume_disk_gb=0
            )
        except Exception as create_error:
            error_str = str(create_error)
            if "SUPPLY_CONSTRAINT" in error_str or "no longer any instances available" in error_str:
                yield "❌ Selected GPU is currently out of stock"
                yield "\n💡 Try one of these options:"
                yield "   1. Click 'Fetch Available GPUs' again to refresh availability"
                yield "   2. Select a different GPU from the dropdown"
                yield "   3. Wait a few minutes and try again"
                return
            else:
                raise
        
        app_state.current_pod_id = pod_id
        yield f"✅ Pod created! ID: {pod_id}"
        
        # Wait for pod to be ready with progress updates
        yield "⏳ Waiting for pod to start (this may take 2-3 minutes)..."
        yield "   Checking pod status every 10 seconds..."
        
        start_time = time.time()
        timeout = 300  # 5 minutes
        check_interval = 10
        last_status = None
        
        while time.time() - start_time < timeout:
            try:
                pod_info = app_state.runpod_manager.get_pod(pod_id)
                current_status = pod_info.get("desiredStatus", "UNKNOWN")
                
                if current_status != last_status:
                    yield f"   Pod status: {current_status}"
                    last_status = current_status
                
                if current_status == "RUNNING":
                    # Pod is running, now check for SSH
                    ssh_ip, ssh_port = app_state.runpod_manager.get_ssh_connection_info(pod_id)
                    if ssh_ip and ssh_port:
                        yield f"✅ Pod is ready! SSH: {ssh_ip}:{ssh_port}"
                        break
                
                time.sleep(check_interval)
            except Exception as e:
                yield f"   Status check: {str(e)}"
                time.sleep(check_interval)
        else:
            # Timeout reached
            yield "❌ Pod startup timeout (5 minutes)"
            yield "\n💡 The pod is taking longer than expected. Options:"
            yield "   1. Check RunPod dashboard for pod status"
            yield "   2. Click 'Terminate Pod' and try a different GPU"
            yield "   3. Use Manual Setup tab if pod is running"
            return
        
        ssh_ip, ssh_port = app_state.runpod_manager.get_ssh_connection_info(pod_id)
        
        if not ssh_ip or not ssh_port:
            yield "❌ Failed to get SSH connection info"
            return
        
        yield f"✅ Pod is running!"
        yield f"   IP: {ssh_ip}"
        yield f"   SSH Port: {ssh_port}"
        
        # Connect via SSH
        yield "\n🔌 Connecting via SSH..."
        
        app_state.ssh_manager = SSHManager(
            host=ssh_ip,
            port=ssh_port,
            key_path=expand_path(ssh_key_path)
        )
        
        if not app_state.ssh_manager.connect():
            yield "❌ Failed to connect via SSH"
            yield "   Check that your SSH public key is added to RunPod settings"
            return
        
        yield "✅ SSH connection established!"
        
        # Detect GPU
        yield "\n🔍 Detecting GPU..."
        exit_code, stdout, stderr = app_state.ssh_manager.execute_command(
            "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"
        )
        
        if exit_code == 0 and stdout:
            gpu_info = stdout.strip().split(',')
            app_state.gpu_name = gpu_info[0].strip()
            vram_mb = int(gpu_info[1].strip().split()[0])
            app_state.vram_gb = vram_mb // 1024
            
            yield f"✅ GPU Detected: {app_state.gpu_name} ({app_state.vram_gb}GB VRAM)"
        else:
            yield "⚠️ Could not detect GPU, but continuing..."
        
        # Save connection info
        app_state.config_manager.save_ssh_config(ssh_ip, ssh_port, ssh_key_path)
        if app_state.gpu_name and app_state.vram_gb:
            app_state.config_manager.save_gpu_info(app_state.vram_gb, app_state.gpu_name)
        
        # Initialize managers
        app_state.gpu_manager = GPUManager(app_state.ssh_manager)
        app_state.model_manager = ModelManager(app_state.ssh_manager)
        app_state.setup_manager = SetupManager(app_state.ssh_manager)
        app_state.video_generator = VideoGenerator(
            app_state.ssh_manager,
            app_state.model_manager,
            app_state.gpu_manager,
            outputs_dir=str(OUTPUTS_DIR)
        )
        
        app_state.connected = True
        
        # Run automated setup
        yield "\n🔧 Running automated Wan2.2 setup..."
        yield "   This will take 10-15 minutes..."
        
        for progress_msg in run_setup(ssh_ip, ssh_port, ssh_key_path, ssh_key_path):
            yield progress_msg
        
        yield "\n🎉 ========================================== 🎉"
        yield "   ✅ POD LAUNCHED AND SETUP COMPLETE!"
        yield "   🎬 Go to 'Generate Video' tab to start creating!"
        yield "🎉 ========================================== 🎉"
        
    except Exception as e:
        yield f"\n❌ Error: {str(e)}"
        if app_state.current_pod_id:
            yield f"\n⚠️ Pod ID {app_state.current_pod_id} may still be running"
            yield "   Check RunPod dashboard to terminate if needed"


def test_connection(ssh_ip: str, ssh_port: int, ssh_key_path: str) -> Generator[str, None, None]:
    """Test SSH connection and detect GPU."""
    global app_state
    
    yield "🔄 Testing connection..."
    
    # Validate inputs
    if not ssh_ip or not ssh_ip.strip():
        yield "❌ Please enter a pod IP address"
        return
    
    if not validate_ip_address(ssh_ip):
        yield "❌ Invalid IP address format"
        return
    
    if not validate_port(int(ssh_port)):
        yield "❌ Invalid port number (must be 1-65535)"
        return
    
    key_valid, key_error = validate_ssh_key_path(ssh_key_path)
    if not key_valid:
        yield f"❌ {key_error}"
        return
    
    yield "🔄 Connecting to pod..."
    
    try:
        # Create SSH manager
        app_state.ssh_manager = SSHManager(
            host=ssh_ip.strip(),
            port=int(ssh_port),
            key_path=expand_path(ssh_key_path)
        )
        
        # Test connection
        if not app_state.ssh_manager.connect():
            yield "❌ Connection failed. Check IP, port, and SSH key."
            app_state.connected = False
            return
        
        yield "✅ SSH connection successful!"
        yield "🔄 Detecting GPU..."
        
        # Initialize managers
        app_state.gpu_manager = GPUManager(app_state.ssh_manager)
        
        # Detect GPU
        vram, gpu_name = app_state.gpu_manager.detect_gpu()
        
        if vram is None:
            yield "⚠️ Could not detect GPU VRAM. Is nvidia-smi available?"
            yield "❌ GPU detection failed"
            return
        
        app_state.vram_gb = vram
        app_state.gpu_name = gpu_name
        app_state.connected = True
        
        # Initialize other managers
        app_state.model_manager = ModelManager(app_state.ssh_manager, app_state.gpu_manager)
        app_state.setup_manager = SetupManager(app_state.ssh_manager)
        app_state.video_generator = VideoGenerator(
            app_state.ssh_manager, 
            app_state.model_manager, 
            app_state.gpu_manager,
            outputs_dir=str(OUTPUTS_DIR)
        )
        
        # Save configuration
        app_state.config_manager.save_ssh_config(
            ssh_ip=ssh_ip.strip(),
            ssh_port=int(ssh_port),
            ssh_key_path=ssh_key_path,
            vram_gb=vram,
            gpu_name=gpu_name
        )
        
        yield f"✅ Connected successfully!"
        yield f""
        yield f"**GPU Detected:**"
        yield f"- Name: {gpu_name or 'Unknown'}"
        yield f"- VRAM: {vram}GB"
        yield f""
        
        # Get viable models
        viable_models = app_state.gpu_manager.get_viable_models(vram)
        if viable_models:
            yield f"**Available Models:**"
            for model_key, specs in viable_models:
                yield f"- {specs['name']}"
        else:
            yield "⚠️ No viable models for this GPU VRAM"
        
        # Check setup status
        yield ""
        yield "🔄 Checking Wan2.2 setup status..."
        
        if app_state.setup_manager.check_if_setup_complete():
            app_state.setup_complete = True
            yield "✅ Wan2.2 is already set up on this pod!"
            yield "   You can proceed to generate videos."
        else:
            yield "⚠️ Wan2.2 setup is not complete."
            yield "   Click 'Setup Wan2.2' to install dependencies."
        
    except Exception as e:
        yield f"❌ Error: {str(e)}"
        app_state.connected = False


def run_setup(ip: str, port: int, key_path: str) -> Generator[str, None, None]:
    """Run the Wan2.2 setup process step by step."""
    if not app_state.connected:
        yield "❌ Not connected to GPU pod. Please connect first."
        return
    
    # Accumulate all messages to display them together
    messages = []
    
    def add_msg(msg):
        messages.append(msg)
        return '\n'.join(messages)
    
    try:
        # Run setup step by step, yielding progress
        for step in app_state.setup_manager.SETUP_STEPS:
            yield add_msg(f"\n📦 {step['name']}")
            yield add_msg(f"   {step['description']}")
            
            # Check if already complete
            if app_state.setup_manager.check_step_complete(step['id']):
                yield add_msg(f"   ✅ Already complete (skipping)")
                continue
            
            # Execute the step
            cmd = step.get('command', '')
            if step['id'] == 'rife_script':
                # Special handling for RIFE script
                success = app_state.setup_manager._deploy_rife_script(lambda msg: None)
            elif cmd:
                yield add_msg(f"   🔄 Running...")
                exit_code, stdout, stderr = app_state.ssh_manager.execute_command(
                    cmd,
                    timeout=step.get('timeout')
                )
                success = (exit_code == 0)
                
                # Show some output for long-running commands
                if stdout and len(stdout) > 100:
                    lines = [l for l in stdout.split('\n') if l.strip()]
                    if len(lines) > 3:
                        messages[-1] = f"   📝 {lines[-1][:80]}"  # Replace "Running..." message
                        yield '\n'.join(messages)
                
                if not success:
                    yield add_msg(f"   ❌ Failed (exit code: {exit_code})")
                    if stderr:
                        # Show full error output
                        for line in stderr.split('\n')[:20]:  # Limit to 20 lines
                            if line.strip():
                                yield add_msg(f"   ERROR: {line[:100]}")
                    if stdout:
                        # Show last few lines of output
                        lines = stdout.split('\n')
                        for line in lines[-10:]:
                            if line.strip():
                                yield add_msg(f"   OUTPUT: {line[:100]}")
            else:
                yield add_msg(f"   ⚠️ No command for this step")
                success = False
            
            if success:
                yield add_msg(f"   ✅ Complete")
            else:
                yield add_msg(f"\n❌ Setup failed at step: {step['name']}")
                return
        
        app_state.setup_complete = True
        app_state.config_manager.save_setup_status(True)
        
        # Final success banner
        yield add_msg("\n\n" + "="*80)
        yield add_msg("🎉 " + "="*70 + " 🎉")
        yield add_msg("                    ✅ WAN2.2 SETUP COMPLETE! ✅")
        yield add_msg("🎉 " + "="*70 + " 🎉")
        yield add_msg("="*80)
        yield add_msg("")
        yield add_msg("📦 Models will be downloaded on-demand when you select them.")
        yield add_msg("🎬 **Proceed to the 'Generate Video' tab to create your first video!**")
        yield add_msg("")
        yield add_msg("="*80)
        
    except Exception as e:
        yield add_msg(f"\n❌ Setup error: {str(e)}")


def get_model_choices(vram_gb: Optional[int] = None) -> list:
    """Get model choices based on VRAM."""
    if vram_gb is None:
        vram_gb = app_state.vram_gb
    
    if vram_gb is None:
        # Return all models with VRAM requirements
        return [
            ('TI2V-5B (Fast) - 24GB+', 'ti2v-5b'),
            ('T2V-A14B (High Quality) - 40GB+', 't2v-a14b'),
            ('I2V-A14B (Image-to-Video) - 40GB+', 'i2v-a14b'),
            ('S2V-14B (Speech-to-Video) - 40GB+', 's2v-14b'),
        ]
    
    choices = []
    if app_state.gpu_manager:
        viable = app_state.gpu_manager.get_viable_models(vram_gb)
        for model_key, specs in viable:
            downloaded = ""
            if app_state.model_manager and app_state.model_manager.check_model_exists(model_key):
                downloaded = " ✅"
            choices.append((f"{specs['name']}{downloaded}", model_key))
    
    return choices if choices else [('TI2V-5B (Fast)', 'ti2v-5b')]


def get_resolution_choices(model_key: str = 'ti2v-5b') -> list:
    """Get resolution choices based on model compatibility."""
    if app_state.gpu_manager:
        viable = app_state.gpu_manager.get_viable_resolutions(model_key)
        return viable if viable else ['1280x704 (Landscape)', '704x1280 (Portrait)']
    return ['1280x704 (Landscape)', '704x1280 (Portrait)']


def update_model_info(model_key: str) -> Tuple[str, str, list]:
    """Update model info display and resolution options."""
    if not app_state.gpu_manager:
        return "Please connect to a GPU pod first.", '1280x704 (Landscape)', ['1280x704 (Landscape)', '704x1280 (Portrait)']
    
    info = app_state.gpu_manager.get_model_display_info(model_key, app_state.vram_gb)
    recommended_res = app_state.gpu_manager.get_recommended_resolution(model_key)
    viable_res = app_state.gpu_manager.get_viable_resolutions(model_key)
    
    return info, recommended_res or '1280x704 (Landscape)', viable_res if viable_res else ['1280x704 (Landscape)', '704x1280 (Portrait)']


def update_time_estimate(model_key: str, duration: int, resolution: str) -> str:
    """Update estimated generation time."""
    estimate = estimate_generation_time(model_key, duration, resolution)
    return f"⏱️ Estimated time: {estimate}"


def stop_generation() -> str:
    """Stop current video generation and clear GPU memory."""
    global app_state
    
    if not app_state.connected or not app_state.ssh_manager:
        return "⚠️ Not connected to pod"
    
    try:
        # Force kill all Python processes (aggressive)
        kill_cmds = [
            "pkill -9 -f 'python.*generate.py'",
            "pkill -9 -f 'python.*rife_interpolate.py'",
            "pkill -9 -f 'python3.*generate.py'",
            "pkill -9 python3",
            "sleep 2"
        ]
        
        for cmd in kill_cmds:
            app_state.ssh_manager.execute_command(cmd, timeout=5)
        
        # Clear GPU memory and system cache
        clear_cmd = """python3 -c "import torch, gc; torch.cuda.empty_cache(); gc.collect(); print('Cleared')" """
        exit_code, stdout, stderr = app_state.ssh_manager.execute_command(clear_cmd, timeout=10)
        
        return "✅ All processes killed and memory cleared"
    except Exception as e:
        return f"❌ Error stopping generation: {str(e)}"


def enhance_prompt_with_llm(current_prompt: str) -> str:
    """Generate an enhanced version of the prompt using Qwen LLM."""
    if not app_state.connected or not app_state.ssh_manager:
        return "❌ Not connected to GPU pod. Please connect first."
    
    if not current_prompt.strip():
        return "❌ Please enter a prompt first, then click 'Generate Enhancement'."
    
    try:
        import base64
        
        prompt_b64 = base64.b64encode(current_prompt.encode()).decode()
        
        # Optimized enhancement script with model caching
        enhance_script = f"""
import base64
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import os

prompt_b64 = "{prompt_b64}"
original_prompt = base64.b64decode(prompt_b64).decode()

# Use smaller, faster Qwen 1.5B model instead of 3B
model_name = "Qwen/Qwen2.5-1.5B-Instruct"
cache_dir = "/root/.cache/huggingface"

# Load model with optimizations
tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    model_name, 
    torch_dtype=torch.float16,  # Use FP16 for faster inference
    device_map="auto",
    cache_dir=cache_dir,
    trust_remote_code=True,
    low_cpu_mem_usage=True
)

system_prompt = \"\"\"You are a video prompt engineer. Enhance the user's prompt into a concise, vivid video generation prompt.

Rules:
- Output ONLY 2-3 sentences maximum
- Include visual details, camera style, and motion
- Add quality keywords (4K, cinematic)
- No explanations, no quotes, no prefixes
- Keep it concise and focused on visual elements\"\"\"

messages = [
    {{"role": "system", "content": system_prompt}},
    {{"role": "user", "content": f"Enhance this video prompt: {{original_prompt}}"}}
]

text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer([text], return_tensors="pt").to(model.device)

# Optimized generation parameters for speed
with torch.no_grad():
    outputs = model.generate(
        **inputs, 
        max_new_tokens=120,  # Reduced from 150
        temperature=0.7,
        top_p=0.9,
        do_sample=True,
        num_beams=1,  # Greedy decoding is faster
        pad_token_id=tokenizer.eos_token_id
    )
    
response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
print(response.strip())
"""
        
        script_b64 = base64.b64encode(enhance_script.encode()).decode()
        cmd = f'echo "{script_b64}" | base64 -d > /tmp/enhance_prompt.py && cd /root/Wan2.2 && python /tmp/enhance_prompt.py'
        
        # Increased timeout for first-time model download
        exit_code, stdout, stderr = app_state.ssh_manager.execute_command(cmd, timeout=180)
        
        if exit_code == 0 and stdout.strip():
            return stdout.strip()
        else:
            return f"❌ Enhancement failed: {stderr[:300] if stderr else 'Unknown error'}"
            
    except Exception as e:
        return f"❌ Error: {str(e)}"


def refine_prompt_with_llm(current_prompt: str, user_message: str) -> str:
    """Refine the prompt based on user feedback using Qwen LLM."""
    if not app_state.connected or not app_state.ssh_manager:
        return "❌ Not connected to GPU pod. Please connect first."
    
    if not current_prompt.strip():
        return "❌ Please enter a prompt first, then ask me to refine it."
    
    if not user_message.strip():
        return "❌ Please enter your refinement request."
    
    try:
        import base64
        
        prompt_b64 = base64.b64encode(current_prompt.encode()).decode()
        message_b64 = base64.b64encode(user_message.encode()).decode()
        
        refine_script = f"""
import base64
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

prompt_b64 = "{prompt_b64}"
message_b64 = "{message_b64}"

current_prompt = base64.b64decode(prompt_b64).decode()
user_request = base64.b64decode(message_b64).decode()

# Use smaller, faster Qwen 1.5B model
model_name = "Qwen/Qwen2.5-1.5B-Instruct"
cache_dir = "/root/.cache/huggingface"

tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float16,
    device_map="auto",
    cache_dir=cache_dir,
    trust_remote_code=True,
    low_cpu_mem_usage=True
)

system_prompt = f\"\"\"You are a video prompt refinement assistant. Refine the video generation prompt based on the user request.

Current prompt: {{current_prompt}}
User request: {{user_request}}

Output ONLY the refined prompt text directly. No explanations, no quotes, no prefixes.\"\"\"

messages = [
    {{"role": "system", "content": system_prompt}},
    {{"role": "user", "content": "Refine the prompt now."}}
]

text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer([text], return_tensors="pt").to(model.device)

with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=150,
        temperature=0.7,
        top_p=0.9,
        do_sample=True,
        num_beams=1,
        pad_token_id=tokenizer.eos_token_id
    )
    
response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
print(response.strip())
"""
        
        script_b64 = base64.b64encode(refine_script.encode()).decode()
        cmd = f'echo "{script_b64}" | base64 -d > /tmp/refine_prompt.py && cd /root/Wan2.2 && python /tmp/refine_prompt.py'
        
        exit_code, stdout, stderr = app_state.ssh_manager.execute_command(cmd, timeout=180)
        
        if exit_code == 0 and stdout.strip():
            return stdout.strip()
        else:
            return f"❌ LLM refinement failed: {stderr[:300] if stderr else 'Unknown error'}"
            
    except Exception as e:
        return f"❌ Error: {str(e)}"


def generate_video_wrapper(
    prompt: str,
    duration: int,
    model: str,
    resolution: str,
    seed: int,
    enhance_prompt: bool,
    rife_multiplier: int,
    sample_steps: int = 20,
    enable_tiling: bool = False,
    save_last_frame: bool = False,
    input_image: Optional[str] = None,
    input_audio: Optional[str] = None
) -> Generator[Tuple[Optional[str], str], None, None]:
    """Generate video with the given parameters. User downloads via Gradio's built-in download button."""
    
    # Validate connection
    if not app_state.connected or not app_state.video_generator:
        yield None, "❌ Not connected to GPU pod. Please connect first."
        return
    
    if not app_state.setup_complete:
        yield None, "❌ Wan2.2 setup not complete. Please run setup first."
        return
    
    # Validate prompt
    valid, error = validate_prompt(prompt)
    if not valid:
        yield None, f"❌ {error}"
        return
    
    # Progress messages
    progress_messages = []
    
    def progress_callback(msg):
        progress_messages.append(msg)
    
    generation_start = time.time()
    yield None, "🎬 Starting video generation...\n⏱️ Elapsed: 0s\n"
    
    try:
        # Run generation in a thread to not block UI updates
        result = [None, None]
        error_occurred = [False]
        
        def run_generation():
            try:
                video_path, status = app_state.video_generator.generate_video(
                    prompt=prompt,
                    duration=int(duration),
                    model=model,
                    resolution=resolution,
                    seed=int(seed),
                    progress_callback=progress_callback,
                    enhance_prompt=enhance_prompt,
                    rife_multiplier=int(rife_multiplier),
                    sample_steps=int(sample_steps),
                    disable_offloading=False,  # Let video_generator decide based on model type
                    enable_tiling=enable_tiling,
                    input_image=input_image,
                    input_audio=input_audio
                )
                result[0] = video_path
                result[1] = status
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                progress_callback(f"\n❌ EXCEPTION DETAILS:\n{error_details}")
                result[1] = f"❌ Error: {str(e)}\n\nSee details above for full traceback."
                error_occurred[0] = True
        
        thread = threading.Thread(target=run_generation)
        thread.start()
        
        # Yield progress updates while generation is running
        last_msg_count = 0
        last_progress_time = generation_start
        stuck_warning_shown = False
        
        while thread.is_alive():
            elapsed = int(time.time() - generation_start)
            elapsed_str = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"
            
            # Check if progress is stuck (no new messages for 2+ minutes)
            current_msg_count = len(progress_messages)
            if current_msg_count > last_msg_count:
                last_progress_time = time.time()
                stuck_warning_shown = False
            
            time_since_last_progress = time.time() - last_progress_time
            
            # Warn if stuck for 2+ minutes
            if time_since_last_progress >= 120 and not stuck_warning_shown and current_msg_count > 0:
                warning_msg = f"""
⚠️ WARNING: No progress for {int(time_since_last_progress // 60)} minutes!

Possible causes:
• RAM OOM (Out of Memory) - Pod may run out of system RAM
• VRAM OOM - GPU memory exhausted
• Model loading taking longer than expected

Recommendations:
• Wait 2-3 more minutes to see if progress resumes
• If still stuck, terminate the generation and restart
• For T2V-A14B: Use pod with 60GB+ VRAM and 70GB+ RAM
• Consider using TI2V-5B instead (works on 24GB+ VRAM, 32GB+ RAM)

You can stop this generation and try again with a smaller model or higher specs pod.
"""
                progress_callback(warning_msg)
                stuck_warning_shown = True
            
            status_text = f"⏱️ Elapsed: {elapsed_str}\n\n" + "\n".join(progress_messages)
            yield None, status_text
            last_msg_count = current_msg_count
            thread.join(timeout=1.0)
        
        # Final status with total time
        total_time = int(time.time() - generation_start)
        total_str = f"{total_time // 60}m {total_time % 60}s" if total_time >= 60 else f"{total_time}s"
        
        final_status = f"⏱️ Total generation time: {total_str}\n\n" + "\n".join(progress_messages)
        if result[1]:
            final_status += f"\n\n{result[1]}"
        
        # Return video path for display - user can download via Gradio's download button
        video_path = result[0]
        
        if video_path:
            final_status += f"\n\n✅ Video ready! Use the download button (⬇️) above to save it to your preferred location."
            
            # Extract last frame if requested (for I2V workflow)
            if save_last_frame:
                try:
                    import subprocess
                    frame_path = video_path.replace('.mp4', '_last_frame.png')
                    
                    progress_callback(f"\n📸 Extracting last frame...")
                    
                    # Use ffmpeg to extract last frame
                    cmd = [
                        'ffmpeg', '-sseof', '-0.1', '-i', video_path,
                        '-update', '1', '-q:v', '2', '-frames:v', '1', frame_path, '-y'
                    ]
                    subprocess.run(cmd, capture_output=True, timeout=30, check=False)
                    
                    if os.path.exists(frame_path):
                        final_status += f"\n📸 Last frame saved: {os.path.basename(frame_path)}"
                        progress_callback(f"   Saved to: {frame_path}")
                    else:
                        final_status += f"\n⚠️ Failed to extract last frame"
                except Exception as e:
                    final_status += f"\n⚠️ Frame extraction failed: {str(e)}"
        
        # Save to history
        try:
            app_state.config_manager.save_generation_history(
                prompt=prompt,
                model=model,
                duration=int(duration),
                resolution=resolution,
                seed=int(seed),
                output_path=video_path if video_path else "N/A",
                success=video_path is not None
            )
        except Exception as history_error:
            # Silent fail on history - not critical
            pass
        
        yield video_path, final_status
        
    except Exception as e:
        yield None, f"❌ Generation failed: {str(e)}"


def create_ui():
    """Create the Gradio UI."""
    
    # Load saved config
    saved_ip, saved_port, saved_key, saved_vram, saved_gpu = load_saved_config()
    saved_api_key = app_state.config_manager.load_runpod_api_key()
    
    with gr.Blocks(title="Wan2.2 Video Generator") as app:
        
        # Check for updates on startup
        update_available, latest_version, download_url = check_for_updates()
        
        # Update notification banner
        if update_available and download_url:
            with gr.Row():
                gr.Markdown(f"""
### 🎉 Update Available: v{latest_version}

A new version is available! [**Download v{latest_version}**]({download_url})

**Current version:** v{get_current_version()} | **Latest version:** v{latest_version}

📥 Download the new installer and run it to upgrade. Your settings and outputs will be preserved.
                """, elem_classes="update-banner")
        
        with gr.Row():
            with gr.Column(scale=4):
                gr.Markdown(f"""
# 🎬 Wan2.2 Video Generator

Generate high-quality AI videos using Wan2.2 models on RunPod GPU pods.

**Version:** v{get_current_version()}
                """)
            with gr.Column(scale=1):
                app_runtime = gr.Markdown(f"🕐 App Runtime: 0s", elem_id="app-runtime")
        
        with gr.Tabs():
            # ===== LAUNCH POD TAB (Hidden for now) =====
            with gr.Tab("🚀 Launch GPU Pod", visible=False):
                gr.Markdown("### Automated RunPod Deployment")
                gr.Markdown("""
                Launch a GPU pod on RunPod and automatically set up Wan2.2.
                
                **Requirements:**
                - RunPod API key ([Get it here](https://runpod.io/console/user/settings))
                - SSH public key added to RunPod settings
                """)
                
                with gr.Row():
                    with gr.Column(scale=3):
                        runpod_api_key = gr.Textbox(
                            label="RunPod API Key",
                            placeholder="Enter your RunPod API key...",
                            type="password",
                            value=saved_api_key,
                            info="Auto-saved after first use"
                        )
                        
                        fetch_gpus_btn = gr.Button("🔍 Fetch Available GPUs", variant="secondary")
                        
                        gpu_dropdown = gr.Dropdown(
                            label="Select GPU",
                            choices=[],
                            info="GPU options with real-time pricing",
                            interactive=True
                        )
                        
                        launch_pod_btn = gr.Button("🚀 Launch Pod & Auto-Setup", variant="primary", size="lg")
                        
                        terminate_pod_btn = gr.Button("🛑 Terminate Pod", variant="stop", size="lg")
                    
                    with gr.Column(scale=2):
                        launch_status = gr.Textbox(
                            label="Status",
                            lines=20,
                            max_lines=25,
                            value="Click 'Fetch Available GPUs' to start",
                            interactive=False,
                            elem_classes=["status-box"]
                        )
                
                # Wire up the fetch GPUs button
                fetch_gpus_btn.click(
                    fn=fetch_available_gpus,
                    inputs=[runpod_api_key],
                    outputs=[launch_status, gpu_dropdown]
                )
                
                # Wire up the launch pod button
                launch_pod_btn.click(
                    fn=launch_pod_and_setup,
                    inputs=[runpod_api_key, gpu_dropdown],
                    outputs=[launch_status]
                )
                
                # Wire up the terminate pod button
                terminate_pod_btn.click(
                    fn=terminate_current_pod,
                    outputs=[launch_status]
                )
            
            # ===== MANAGE SSH CONNECTION TAB =====
            with gr.Tab("� Manage SSH Connection"):
                gr.Markdown("### SSH Key Setup (One-Time)")
                gr.Markdown("""
This tab auto-detects your SSH key. Copy the **public key** below and paste it into your 
[RunPod SSH Settings](https://www.runpod.io/console/user/settings) under **SSH Public Keys**.
                """)
                
                # Auto-detect SSH keys
                ssh_key_choices = SSHKeyManager.get_key_choices()
                default_key = saved_key or SSHKeyManager.get_default_key_path() or "~/.ssh/id_ed25519"
                default_pub = SSHKeyManager.get_public_key_content(default_key) if default_key else None
                
                with gr.Row():
                    with gr.Column(scale=2):
                        ssh_key_dropdown = gr.Dropdown(
                            choices=ssh_key_choices,
                            value=default_key,
                            label="SSH Private Key",
                            info="Auto-detected SSH keys from ~/.ssh",
                            allow_custom_value=True
                        )
                    with gr.Column(scale=1):
                        ssh_key_status = gr.Markdown(
                            value=f"✅ Key loaded: `{os.path.basename(default_key)}`" if default_key and os.path.exists(SSHKeyManager.expand_path(default_key)) else "⚠️ No SSH key detected"
                        )
                
                with gr.Row():
                    show_key_checkbox = gr.Checkbox(
                        label="👁️ Show Public Key",
                        value=False,
                        info="Toggle to view the public key"
                    )
                
                pub_key_display = gr.Textbox(
                    label="📋 Public Key (copy this to RunPod SSH Settings)",
                    value=default_pub or "No public key found. Generate one with: ssh-keygen -t ed25519",
                    lines=3,
                    interactive=False,
                    type="password",
                    visible=True
                )
                
                def on_key_selected(key_path):
                    """Update public key display when a different key is selected."""
                    if key_path == "custom" or not key_path:
                        return "Enter a key path above", "⚠️ Select a key"
                    expanded = SSHKeyManager.expand_path(key_path)
                    if not os.path.exists(expanded):
                        return f"Key not found at: {expanded}", f"❌ Key not found"
                    pub_content = SSHKeyManager.get_public_key_content(key_path)
                    if pub_content:
                        # Save the selected key
                        app_state.config_manager.save_connection_info(
                            ssh_ip=app_state.config_manager._config.get('ssh', {}).get('ip', ''),
                            ssh_port=app_state.config_manager._config.get('ssh', {}).get('port', 22),
                            ssh_key_path=key_path
                        )
                        return pub_content, f"✅ Key loaded: `{os.path.basename(key_path)}`"
                    return f"No .pub file found for {key_path}. Generate with: ssh-keygen -t ed25519", f"⚠️ No public key"
                
                ssh_key_dropdown.change(
                    fn=on_key_selected,
                    inputs=[ssh_key_dropdown],
                    outputs=[pub_key_display, ssh_key_status]
                )
                
                def toggle_key_visibility(show):
                    """Toggle between password and text type for public key display."""
                    return gr.update(type="text" if show else "password")
                
                show_key_checkbox.change(
                    fn=toggle_key_visibility,
                    inputs=[show_key_checkbox],
                    outputs=[pub_key_display]
                )
                
                gr.Markdown("""
---
**How it works:**
1. Your SSH key is auto-detected from your system
2. Copy the public key above and add it to [RunPod SSH Settings](https://www.runpod.io/console/user/settings)
3. The selected key is saved and reused automatically for future sessions
4. To use a different key, select it from the dropdown above

**No SSH key? Generate one:**

**Windows (PowerShell):**
```powershell
ssh-keygen -t ed25519 -C "your_email@example.com"
# Key saved to: C:\\Users\\YourName\\.ssh\\id_ed25519
```

**macOS/Linux (Terminal):**
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
# Key saved to: ~/.ssh/id_ed25519
```

After generating, **restart this app** to auto-detect your new key.
                """)
            
            # ===== SETUP & CONNECTION TAB =====
            with gr.Tab("🔧 Setup & Connection"):
                gr.Markdown("### Connect to Your GPU Pod")
                gr.Markdown("""
Enter the SSH details from your RunPod pod. Find them under **"Direct TCP ports"** in your pod details.  
Example: `213.173.107.13:22324` → IP: `213.173.107.13`, Port: `22324`
                """)
                
                with gr.Row():
                    with gr.Column(scale=2):
                        ssh_ip = gr.Textbox(
                            label="Pod IP Address",
                            placeholder="e.g., 195.26.233.78",
                            value=saved_ip,
                            info="Find this in your RunPod pod details"
                        )
                    with gr.Column(scale=1):
                        ssh_port = gr.Number(
                            label="SSH Port",
                            value=saved_port or 22,
                            precision=0,
                            info="Usually shown as 'SSH Port' in RunPod"
                        )
                
                with gr.Row():
                    test_btn = gr.Button("🔍 Test Connection", variant="secondary", scale=1)
                    setup_btn = gr.Button("⚙️ Setup Wan2.2", variant="primary", scale=1)
                
                connection_status = gr.Textbox(
                    label="Status",
                    interactive=False,
                    lines=15,
                    elem_classes=["status-box"]
                )
                
                # Connection status hint
                if saved_vram:
                    gr.Markdown(f"""
                    **Last connected GPU:** {saved_gpu or 'Unknown'} ({saved_vram}GB VRAM)
                    """)
                
                def get_active_ssh_key():
                    """Get the currently selected SSH key from config or auto-detect."""
                    cfg_key = app_state.config_manager._config.get('ssh', {}).get('key_path', '')
                    if cfg_key and os.path.exists(SSHKeyManager.expand_path(cfg_key)):
                        return cfg_key
                    return SSHKeyManager.get_default_key_path() or "~/.ssh/id_ed25519"
                
                def test_connection_wrapper(ip, port):
                    key_path = get_active_ssh_key()
                    yield from test_connection(ip, port, key_path)
                
                test_btn.click(
                    fn=test_connection_wrapper,
                    inputs=[ssh_ip, ssh_port],
                    outputs=[connection_status]
                )
                
                def run_setup_wrapper(ip, port):
                    key_path = get_active_ssh_key()
                    yield from run_setup(ip, port, key_path)
                
                setup_btn.click(
                    fn=run_setup_wrapper,
                    inputs=[ssh_ip, ssh_port],
                    outputs=[connection_status]
                )
            
            # ===== GENERATE VIDEO TAB =====
            with gr.Tab("🎥 Generate Video"):
                gr.Markdown("### Create Your Video")
                
                with gr.Row():
                    # LEFT COLUMN: Inputs
                    with gr.Column(scale=1, min_width=400):
                        prompt = gr.Textbox(
                            label="Video Prompt",
                            placeholder="Describe the video you want to generate...\n\nExample: A majestic eagle soaring over snow-capped mountains at sunset",
                            lines=4,
                            info="Be detailed for better results"
                        )
                        
                        # Hidden checkbox for backwards compatibility (always False now)
                        enhance_prompt = gr.Checkbox(value=False, visible=False)
                        
                        # Combined LLM prompt enhancement (collapsed by default)
                        with gr.Accordion("✨ Enhance Prompt with LLM", open=False) as llm_accordion:
                            gr.Markdown("**Click 'Generate Enhancement' to get an AI-enhanced version.**")
                            
                            with gr.Row():
                                llm_enhance_btn = gr.Button("✨ Generate", variant="primary", size="sm")
                                llm_apply_btn = gr.Button("✅ Apply", variant="secondary", size="sm")
                            
                            llm_chat_output = gr.Textbox(
                                label="Enhanced Prompt",
                                lines=4,
                                interactive=False,
                                placeholder="Click 'Generate' to enhance..."
                            )
                            
                            llm_chat_input = gr.Textbox(
                                label="Refine Further",
                                placeholder="e.g., 'Make it more cinematic'",
                                lines=2
                            )
                            
                            llm_send_btn = gr.Button("💬 Refine", variant="secondary", size="sm")
                        
                        gr.Markdown("---")
                        gr.Markdown("**Settings**")
                        
                        # Settings in 2-column 3-row grid
                        with gr.Row():
                            model = gr.Dropdown(
                                choices=get_model_choices(),
                                value='ti2v-5b',
                                label="Model",
                                scale=1
                            )
                            duration = gr.Dropdown(
                                choices=[
                                    ('2 sec (no interpolation)', 2),
                                    ('5 sec (with RIFE interpolation)', 5),
                                    ('10 sec (2x5s stitched)', 10)
                                ],
                                value=5,
                                label="Duration",
                                scale=1
                            )
                        
                        with gr.Row():
                            resolution = gr.Dropdown(
                                choices=get_resolution_choices(),
                                value='704x1280 (Portrait)',
                                label="Resolution",
                                scale=1
                            )
                            rife_multiplier = gr.Dropdown(
                                choices=[
                                    ('2x interpolation (faster)', 2),
                                    ('4x interpolation (best)', 4)
                                ],
                                value=2,
                                label="RIFE Interpolation",
                                visible=True,
                                scale=1
                            )
                        
                        with gr.Row():
                            seed = gr.Number(
                                label="Random Seed",
                                value=42,
                                precision=0,
                                scale=1
                            )
                            sample_steps = gr.Dropdown(
                                choices=[
                                    ('8 steps (fast)', 8),
                                    ('12 steps (balanced)', 12),
                                    ('16 steps (good)', 16),
                                    ('20 steps (best)', 20)
                                ],
                                value=20,
                                label="Sample Steps",
                                scale=1
                            )
                        
                        # File inputs in 2-column layout under settings
                        with gr.Row():
                            input_image = gr.File(
                                label="📷 Reference Image",
                                file_types=["image"],
                                file_count="single",
                                scale=1
                            )
                            input_audio = gr.File(
                                label="🎵 Audio File",
                                file_types=["audio"],
                                file_count="single",
                                scale=1
                            )
                        
                        # Hidden elements for backwards compatibility
                        enable_tiling = gr.Checkbox(
                            label="Enable Tiling (Not Supported)",
                            value=False,
                            visible=False
                        )
                        time_estimate = gr.Markdown("", visible=False)
                        
                        save_last_frame_checkbox = gr.Checkbox(
                            label="📸 Save Last Frame as Image",
                            value=False,
                            info="Saves the final frame for use with I2V model (concatenate videos)"
                        )
                        
                        with gr.Row():
                            generate_btn = gr.Button(
                                "🚀 Generate",
                                variant="primary",
                                size="lg",
                                scale=2
                            )
                            clear_btn = gr.Button("🔄 Clear", variant="secondary", scale=1)
                    
                    # RIGHT COLUMN: Output
                    with gr.Column(scale=1, min_width=400):
                        gr.Markdown("**Output**")
                        
                        output_video = gr.Video(
                            label="Generated Video",
                            interactive=False,
                            elem_classes=["video-output"],
                            scale=1
                        )
                        
                        generation_status = gr.Textbox(
                            label="Status",
                            interactive=False,
                            lines=8,
                            elem_classes=["status-box"],
                            max_lines=8
                        )
                
                # Event handlers - update resolution choices when model changes
                def update_resolution_for_model(model_key):
                    recommended = app_state.gpu_manager.get_recommended_resolution(model_key) if app_state.gpu_manager else '1280x704 (Landscape)'
                    choices = app_state.gpu_manager.get_viable_resolutions(model_key) if app_state.gpu_manager else ['1280x704 (Landscape)', '704x1280 (Portrait)']
                    return gr.Dropdown(choices=choices, value=recommended)
                
                model.change(
                    fn=update_resolution_for_model,
                    inputs=[model],
                    outputs=[resolution]
                )
                
                for component in [model, duration, resolution]:
                    component.change(
                        fn=update_time_estimate,
                        inputs=[model, duration, resolution],
                        outputs=[time_estimate]
                    )
                
                # Update RIFE multiplier visibility based on duration
                def update_rife_visibility(dur):
                    return gr.Dropdown(visible=(dur in [5, 10]))
                
                duration.change(
                    fn=update_rife_visibility,
                    inputs=[duration],
                    outputs=[rife_multiplier]
                )
                
                # Update duration choices based on model (file inputs are always visible now)
                def update_model_inputs(model_key):
                    """Update duration choices based on selected model."""
                    from .gpu_manager import GPUManager
                    model_info = GPUManager.MODELS.get(model_key, {})
                    
                    supports_10s = model_info.get('speed_10s') is not None
                    
                    # Duration choices based on model
                    if supports_10s:
                        duration_choices = [
                            ('2 sec (no interpolation)', 2),
                            ('5 sec (with RIFE interpolation)', 5),
                            ('10 sec (2x5s stitched)', 10)
                        ]
                    else:
                        duration_choices = [
                            ('2 sec (no interpolation)', 2),
                            ('5 sec (with RIFE interpolation)', 5),
                        ]
                    
                    return gr.update(choices=duration_choices, value=5)
                
                model.change(
                    fn=update_model_inputs,
                    inputs=[model],
                    outputs=[duration]
                )
                
                generate_btn.click(
                    fn=generate_video_wrapper,
                    inputs=[prompt, duration, model, resolution, seed, enhance_prompt, rife_multiplier, sample_steps, enable_tiling, save_last_frame_checkbox, input_image, input_audio],
                    outputs=[output_video, generation_status]
                )
                
                # LLM Enhancement - Generate initial enhancement
                llm_enhance_btn.click(
                    fn=enhance_prompt_with_llm,
                    inputs=[prompt],
                    outputs=[llm_chat_output]
                )
                
                # LLM Refinement - Further refine based on user feedback
                llm_send_btn.click(
                    fn=refine_prompt_with_llm,
                    inputs=[llm_chat_output, llm_chat_input],  # Use enhanced prompt as base
                    outputs=[llm_chat_output]
                )
                
                # Apply enhanced/refined prompt to main prompt box
                llm_apply_btn.click(
                    fn=lambda refined: refined if not refined.startswith("❌") else gr.update(),
                    inputs=[llm_chat_output],
                    outputs=[prompt]
                )
                
                def clear_and_stop():
                    stop_msg = stop_generation()
                    return None, stop_msg, ""
                
                clear_btn.click(
                    fn=clear_and_stop,
                    outputs=[output_video, generation_status, prompt]
                )
            
            # ===== POD STORAGE TAB =====
            with gr.Tab("� Pod Storage"):
                gr.Markdown("""
### Pod Temporary Files
Browse and download generated content from your GPU pod. This includes videos, last frame images, and intermediate files.

**Note:** Files are stored temporarily on the pod. Download important files to your local machine.
                """)
                
                with gr.Row():
                    refresh_btn = gr.Button("🔄 Refresh Pod Files", variant="secondary")
                    download_instructions_btn = gr.Button("� Download Instructions", variant="secondary")
                
                outputs_status = gr.Markdown("Click 'Refresh' to load outputs")
                
                with gr.Tabs():
                    with gr.Tab("🎬 Videos"):
                        video_gallery = gr.Gallery(
                            label="Generated Videos",
                            columns=3,
                            height="auto",
                            object_fit="contain",
                            allow_preview=True
                        )
                        selected_video = gr.Video(label="Selected Video")
                    
                    with gr.Tab("🖼️ Images (Last Frames)"):
                        image_gallery = gr.Gallery(
                            label="Saved Images",
                            columns=4,
                            height="auto",
                            object_fit="contain",
                            allow_preview=True
                        )
                        gr.Markdown("*Images saved with 'Save Last Frame' option can be used as reference for I2V model*")
                
                def refresh_pod_storage():
                    """Browse files in pod temporary storage (/root/Wan2.2 and temp directories)."""
                    if not app_state.connected or not app_state.ssh_manager:
                        return [], [], "❌ Not connected to pod. Please connect first."
                    
                    try:
                        # List files in Wan2.2 directory
                        exit_code, stdout, stderr = app_state.ssh_manager.execute_command(
                            "ls -lh /root/Wan2.2/*.mp4 /root/Wan2.2/*.png 2>/dev/null | tail -20",
                            timeout=10
                        )
                        
                        if exit_code != 0:
                            return [], [], f"⚠️ No files found in pod storage"
                        
                        # Parse file list
                        videos = []
                        images = []
                        
                        for line in stdout.strip().split('\n'):
                            if not line or line.startswith('total'):
                                continue
                            
                            parts = line.split()
                            if len(parts) < 9:
                                continue
                            
                            filename = parts[-1]
                            filesize = parts[4]
                            
                            if filename.endswith('.mp4'):
                                videos.append(f"{os.path.basename(filename)} ({filesize})")
                            elif filename.endswith('.png'):
                                images.append(f"{os.path.basename(filename)} ({filesize})")
                        
                        status = f"✅ Found {len(videos)} videos and {len(images)} images in pod storage"
                        return videos, images, status
                        
                    except Exception as e:
                        return [], [], f"❌ Error browsing pod storage: {str(e)}"
                
                def download_pod_file():
                    """Instructions for downloading files from pod."""
                    if not app_state.connected:
                        return "❌ Not connected to pod"
                    
                    pod_info = app_state.ssh_manager.get_connection_info() if app_state.ssh_manager else {}
                    host = pod_info.get('host', 'unknown')
                    port = pod_info.get('port', 22)
                    
                    instructions = f"""
📥 **How to Download Files from Pod**

**Pod Connection:** `{host}:{port}`
**Pod Directory:** `/root/Wan2.2/`

**Method 1: Using SCP (Recommended)**
```bash
scp -P {port} root@{host}:/root/Wan2.2/output_*.mp4 ./
scp -P {port} root@{host}:/root/Wan2.2/*_last_frame.png ./
```

**Method 2: Using SFTP Client**
- Use FileZilla, WinSCP, or similar
- Host: {host}, Port: {port}
- Navigate to `/root/Wan2.2/`
- Download desired files

**Common Files:**
- `output_2s.mp4`, `output_5s.mp4` - Generated videos
- `*_last_frame.png` - Saved last frames for I2V
- `output_raw.mp4` - Raw video before interpolation
"""
                    return instructions
                
                refresh_btn.click(
                    fn=refresh_pod_storage,
                    outputs=[video_gallery, image_gallery, outputs_status]
                )
                
                download_instructions_btn.click(
                    fn=download_pod_file,
                    outputs=[outputs_status]
                )
                
                # Select video from gallery
                def select_video(evt: gr.SelectData):
                    if evt.value and 'video' in evt.value.get('mime_type', ''):
                        return evt.value.get('path')
                    return None
            
            # ===== HELP TAB =====
            with gr.Tab("ℹ️ Help & Guide"):
                gr.Markdown("""
## Quick Start Guide

1. **Set up SSH key** in the Manage SSH Connection tab (one-time setup)
2. **Connect to your RunPod pod** in the Setup & Connection tab
3. **Run setup** if this is a fresh pod (~10-15 minutes)
4. **Generate videos** in the Generate tab

## Model Comparison

| Model | Speed (5s) | Quality | Min VRAM | Input | Best For |
|-------|------------|---------|----------|-------|----------|
| **TI2V-5B** | ~3 min | Good | 24GB | Text/Image | Fast iterations, testing |
| **T2V-A14B** | ~6-7 min | Excellent | 40GB | Text only | High-quality text-to-video |
| **I2V-A14B** | ~8-10 min | Excellent | 60GB | Image+Text | Animate reference images |
| **S2V-14B** | ~10-12 min | Excellent | 60GB | Image+Audio | Talking head videos |

## Recommended RunPod GPU Specs

All models tested with **RunPod PyTorch 2.8.0** template, **250GB container disk**, **0GB persistent volume**.

| Model | Recommended GPU | VRAM | Est. Cost | Notes |
|-------|----------------|------|-----------|-------|
| **TI2V-5B** | RTX 4090 / RTX A5000 | 24GB+ | ~$0.40/hr | Fastest, most affordable |
| **T2V-A14B** | RTX 6000 Ada / A100 40GB | 40-48GB | ~$0.75/hr | Needs offloading on 40GB |
| **I2V-A14B** | RTX PRO 6000 / A100 80GB | 60GB+ | ~$1.50/hr | Requires 60GB+ VRAM minimum |
| **S2V-14B** | RTX PRO 6000 / A100 80GB | 60GB+ | ~$1.50/hr | Requires 60GB+ VRAM minimum |

> **Important:** Both **I2V-A14B** and **S2V-14B** require **60GB+ VRAM**. The RTX PRO 6000 (96GB) or A100 80GB are recommended. 48GB GPUs will result in out-of-memory errors.

## Video Duration

- **2 seconds:** Quick generation (~1.5-3 min) — no interpolation
- **5 seconds:** Standard length (~3-7 min) — uses RIFE interpolation
- **10 seconds:** Extended (~6-14 min) — stitches two 5s segments (T2V/I2V only)

## Tips for Best Results

1. **Be specific:** Describe subjects, actions, lighting, camera angles
2. **Use LLM enhancement:** Click "Enhance Prompt with LLM" for AI-refined prompts
3. **Test first:** Use 2s duration and 8 steps to test prompts quickly
4. **Use seeds:** Same seed = reproducible results
5. **S2V model:** Upload a clear portrait image + audio file for best talking head results

## Example Prompts

**Nature:**
> A majestic eagle soaring over snow-capped mountains at sunset, golden light reflecting off its wings, cinematic 4K

**Character:**
> A samurai warrior standing in cherry blossoms, wind moving their robes, petals floating, dramatic cinematic lighting

**Talking Head (S2V):**
> A woman speaking warmly to the camera, natural lighting, soft background blur, professional video quality

## Troubleshooting

- **Connection failed:** Check IP, port, and SSH key path
- **GPU not detected:** Ensure nvidia-smi is available on the pod
- **Setup failed:** Check pod has internet access for downloads
- **Generation OOM:** Try lower resolution, fewer steps, or a larger GPU
- **S2V OOM on 48GB:** S2V-14B requires 60GB+ VRAM — upgrade to RTX PRO 6000 or A100 80GB
                """)
        
        # Footer
        gr.Markdown("""
---
**Wan2.2 Video Generator** v1.0 | Built with Gradio | [Wan2.2 on GitHub](https://github.com/Wan-Video/Wan2.2)
        """)
        
        # Timer to update app runtime every 5 seconds
        timer = gr.Timer(5)
        timer.tick(
            fn=lambda: f"🕐 App Runtime: {app_state.get_app_runtime()}",
            outputs=[app_runtime]
        )
    
    return app


def main():
    """Main entry point."""
    app = create_ui()
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        inbrowser=False,  # Don't open browser - we have desktop window
        share=False,
        theme=gr.themes.Soft(),
        css="""
            .status-box { min-height: 200px; }
            .video-output { min-height: 400px; }
        """
    )


if __name__ == "__main__":
    main()
