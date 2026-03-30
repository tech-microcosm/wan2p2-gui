"""
Setup Manager - Handles remote Wan2.2 setup on RunPod pods
"""
import time
from typing import Callable, Dict, Optional, List
from .ssh_manager import SSHManager


class SetupManager:
    """Manages automated Wan2.2 setup on fresh RunPod pods."""
    
    SETUP_STEPS = [
        {
            'id': 'system_deps',
            'name': 'System Dependencies',
            'description': 'Installing git, wget, ffmpeg...',
            'command': 'apt update && apt install -y git wget ffmpeg',
            'timeout': 300,  # 5 minutes
            'check': 'which ffmpeg'
        },
        {
            'id': 'clone_wan22',
            'name': 'Clone Wan2.2',
            'description': 'Cloning Wan2.2 repository...',
            'command': '''
                if [ -d "/root/Wan2.2" ]; then
                    echo "Wan2.2 already exists"
                else
                    cd /root && git clone https://github.com/Wan-Video/Wan2.2.git
                fi
            ''',
            'timeout': 300,
            'check': 'test -d /root/Wan2.2'
        },
        {
            'id': 'pip_torch',
            'name': 'Install PyTorch',
            'description': 'Installing PyTorch with CUDA support...',
            'command': 'pip3 install --break-system-packages torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121',
            'timeout': 1200,  # 20 minutes
            'check': 'python3 -c "import torch; print(torch.cuda.is_available())"'
        },
        {
            'id': 'pip_wan22_deps',
            'name': 'Install Wan2.2 Dependencies',
            'description': 'Installing all Wan2.2 required packages...',
            'command': 'pip3 install --break-system-packages opencv-python diffusers transformers tokenizers accelerate tqdm imageio[ffmpeg] easydict ftfy dashscope imageio-ffmpeg "numpy>=1.23.5,<2" decord librosa soundfile peft',
            'timeout': 600,
            'check': 'python3 -c "import easydict; import diffusers"'
        },
        {
            'id': 'flash_attn',
            'name': 'Install Flash Attention',
            'description': 'Installing Flash Attention 2 (this may take a few minutes)...',
            'command': 'pip3 install --break-system-packages flash-attn --no-build-isolation',
            'timeout': 900,  # 15 minutes - flash-attn takes a while
            'check': 'python3 -c "import flash_attn"'
        },
        {
            'id': 'clone_rife',
            'name': 'Clone RIFE',
            'description': 'Cloning Practical-RIFE for frame interpolation...',
            'command': '''
                if [ -d "/root/Practical-RIFE" ]; then
                    echo "RIFE already exists"
                else
                    cd /root && git clone https://github.com/hzwer/Practical-RIFE.git
                fi
            ''',
            'timeout': 120,
            'check': 'test -d /root/Practical-RIFE'
        },
        {
            'id': 'rife_requirements',
            'name': 'Install RIFE Requirements',
            'description': 'Installing RIFE dependencies...',
            'command': 'pip3 install --break-system-packages opencv-python pillow numpy',
            'timeout': 300,
            'check': 'python3 -c "import cv2"'
        },
        {
            'id': 'rife_model',
            'name': 'Download RIFE Model',
            'description': 'Downloading RIFE model from Google Drive...',
            'command': '''
                mkdir -p /root/Practical-RIFE/train_log
                cd /root/Practical-RIFE/train_log
                if [ -f "RIFE_HDv3.py" ]; then
                    echo "RIFE model already downloaded"
                else
                    apt-get update && apt-get install -y unzip
                    pip install --break-system-packages gdown
                    gdown 'https://drive.google.com/uc?id=1APIzVeI-4ZZCEuIRE1m6WYfSCaOsi_7_' -O v3.8.zip
                    unzip -o v3.8.zip
                    mv train_log/* . 2>/dev/null || true
                    rm -rf train_log __MACOSX v3.8.zip
                fi
            ''',
            'timeout': 300,
            'check': 'test -f /root/Practical-RIFE/train_log/RIFE_HDv3.py'
        },
        {
            'id': 'rife_script',
            'name': 'Deploy RIFE Script',
            'description': 'Deploying RIFE interpolation script...',
            'command': None,  # Handled specially - uploads a file
            'timeout': 60,
            'check': 'test -f /root/rife_interpolate.py'
        }
    ]
    
    def __init__(self, ssh_manager: SSHManager):
        """
        Initialize setup manager.
        
        Args:
            ssh_manager: SSHManager instance for remote operations
        """
        self.ssh = ssh_manager
        self._step_status: Dict[str, bool] = {}
    
    def check_step_complete(self, step_id: str) -> bool:
        """
        Check if a setup step is already complete.
        
        Args:
            step_id: Step identifier
            
        Returns:
            True if step is complete
        """
        for step in self.SETUP_STEPS:
            if step['id'] == step_id and step.get('check'):
                exit_code, _, _ = self.ssh.execute_command(step['check'])
                return exit_code == 0
        return False
    
    def check_if_setup_complete(self) -> bool:
        """
        Check if full Wan2.2 setup is complete.
        
        Returns:
            True if all setup steps are complete
        """
        # Quick checks for essential components
        checks = [
            ('Wan2.2 repo', 'test -d /root/Wan2.2'),
            ('RIFE', 'test -f /root/Practical-RIFE/train_log/flownet.pkl'),
            ('RIFE script', 'test -f /root/rife_interpolate.py'),
            ('PyTorch', 'python3 -c "import torch; assert torch.cuda.is_available()"'),
        ]
        
        for name, cmd in checks:
            exit_code, _, _ = self.ssh.execute_command(cmd)
            if exit_code != 0:
                return False
        
        return True
    
    def get_setup_status(self) -> Dict[str, bool]:
        """
        Get status of each setup step.
        
        Returns:
            Dict mapping step_id to completion status
        """
        status = {}
        for step in self.SETUP_STEPS:
            status[step['id']] = self.check_step_complete(step['id'])
        return status
    
    def run_step(
        self, 
        step_id: str, 
        progress_callback: Optional[Callable[[str], None]] = None,
        force: bool = False
    ) -> bool:
        """
        Run a single setup step.
        
        Args:
            step_id: Step identifier
            progress_callback: Callback for progress updates
            force: If True, run even if step appears complete
            
        Returns:
            True if step completed successfully
        """
        step = None
        for s in self.SETUP_STEPS:
            if s['id'] == step_id:
                step = s
                break
        
        if not step:
            if progress_callback:
                progress_callback(f"❌ Unknown step: {step_id}")
            return False
        
        # Check if already complete
        if not force and self.check_step_complete(step_id):
            if progress_callback:
                progress_callback(f"✅ {step['name']} - already complete")
            return True
        
        if progress_callback:
            progress_callback(f"🔄 {step['name']}")
            progress_callback(f"   {step['description']}")
        
        # Special handling for RIFE script deployment
        if step_id == 'rife_script':
            return self._deploy_rife_script(progress_callback)
        
        # Execute command
        cmd = step.get('command', '')
        if not cmd:
            if progress_callback:
                progress_callback(f"⚠️ No command for step {step_id}")
            return False
        
        exit_code, stdout, stderr = self.ssh.execute_command(
            cmd, 
            progress_callback=lambda line: progress_callback(f"   {line}") if progress_callback else None,
            timeout=step.get('timeout')
        )
        
        if exit_code != 0:
            if progress_callback:
                progress_callback(f"❌ {step['name']} failed")
                if stderr:
                    progress_callback(f"   Error: {stderr[:200]}")
            return False
        
        # Verify step completed
        if step.get('check'):
            verify_code, _, _ = self.ssh.execute_command(step['check'])
            if verify_code != 0:
                if progress_callback:
                    progress_callback(f"⚠️ {step['name']} - verification failed")
                return False
        
        if progress_callback:
            progress_callback(f"✅ {step['name']} - complete")
        
        return True
    
    def _deploy_rife_script(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Deploy the RIFE interpolation script to the pod."""
        rife_script = self._get_rife_script_content()
        
        # Create the script on remote
        cmd = f'''cat > /root/rife_interpolate.py << 'RIFE_SCRIPT_EOF'
{rife_script}
RIFE_SCRIPT_EOF
chmod +x /root/rife_interpolate.py
'''
        
        exit_code, _, stderr = self.ssh.execute_command(cmd)
        
        if exit_code != 0:
            if progress_callback:
                progress_callback(f"❌ Failed to deploy RIFE script: {stderr}")
            return False
        
        if progress_callback:
            progress_callback("✅ RIFE interpolation script deployed")
        
        return True
    
    def _get_rife_script_content(self) -> str:
        """Get the content of the RIFE interpolation script."""
        return '''#!/usr/bin/env python3
"""RIFE Frame Interpolation Script for Wan2.2"""
import cv2
import torch
import numpy as np
import argparse
import sys
import os

sys.path.append('/root/Practical-RIFE')
from train_log.RIFE_HDv3 import Model

def load_video_frames(video_path):
    """Load all frames from a video file."""
    cap = cv2.VideoCapture(video_path)
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()
    return frames

def save_video(frames, output_path, fps=24):
    """Save frames to a video file."""
    if len(frames) == 0:
        print("No frames to save!")
        return
    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))
    for frame in frames:
        out.write(frame)
    out.release()

def interpolate_frames(model, img0, img1, device, scale=1.0):
    """Interpolate a single frame between two images."""
    img0_t = torch.from_numpy(img0.transpose(2, 0, 1)).float().unsqueeze(0).to(device) / 255.0
    img1_t = torch.from_numpy(img1.transpose(2, 0, 1)).float().unsqueeze(0).to(device) / 255.0
    
    with torch.no_grad():
        mid = model.inference(img0_t, img1_t, scale=scale)
    
    mid_np = (mid[0].cpu().numpy().transpose(1, 2, 0) * 255).astype(np.uint8)
    return mid_np

def interpolate_video(input_path, output_path, multi=2, scale=1.0):
    """
    Interpolate video frames using RIFE.
    
    Args:
        input_path: Path to input video
        output_path: Path to output video
        multi: Interpolation multiplier (2 = double frames, 4 = quadruple)
        scale: Scale factor for RIFE (1.0 = full resolution)
    """
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'Using device: {device}')
    
    # Load RIFE model
    model = Model()
    model.load_model('/root/Practical-RIFE/train_log', -1)
    model.eval()
    model.device()
    print('RIFE model loaded')
    
    # Load input video
    frames = load_video_frames(input_path)
    print(f'Loaded {len(frames)} frames from {input_path}')
    
    if len(frames) < 2:
        print("Need at least 2 frames to interpolate!")
        return
    
    # Get original FPS
    cap = cv2.VideoCapture(input_path)
    orig_fps = cap.get(cv2.CAP_PROP_FPS)
    if orig_fps <= 0:
        orig_fps = 24  # Default fallback
    cap.release()
    
    # Interpolate frames
    output_frames = []
    total_pairs = len(frames) - 1
    
    for i in range(total_pairs):
        output_frames.append(frames[i])
        
        if multi == 2:
            # Insert 1 interpolated frame
            mid = interpolate_frames(model, frames[i], frames[i+1], device, scale)
            output_frames.append(mid)
        elif multi == 4:
            # Insert 3 interpolated frames
            mid = interpolate_frames(model, frames[i], frames[i+1], device, scale)
            mid1 = interpolate_frames(model, frames[i], mid, device, scale)
            mid2 = interpolate_frames(model, mid, frames[i+1], device, scale)
            output_frames.extend([mid1, mid, mid2])
        
        if (i + 1) % 10 == 0 or i == total_pairs - 1:
            print(f'Processed {i+1}/{total_pairs} frame pairs')
    
    # Add last frame
    output_frames.append(frames[-1])
    print(f'Total output frames: {len(output_frames)}')
    
    # Save output video - KEEP ORIGINAL FPS for correct duration
    save_video(output_frames, output_path, fps=orig_fps)
    
    duration = len(output_frames) / orig_fps
    print(f'Saved to {output_path}')
    print(f'Output: {len(output_frames)} frames at {orig_fps} fps = {duration:.1f}s duration')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RIFE Frame Interpolation')
    parser.add_argument('--input', required=True, help='Input video path')
    parser.add_argument('--output', required=True, help='Output video path')
    parser.add_argument('--multi', type=int, default=2, choices=[2, 4],
                        help='Interpolation multiplier (2 or 4)')
    parser.add_argument('--scale', type=float, default=1.0,
                        help='Scale factor for RIFE')
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    interpolate_video(args.input, args.output, args.multi, args.scale)
'''
    
    def run_full_setup(
        self, 
        progress_callback: Optional[Callable[[str], None]] = None,
        skip_completed: bool = True
    ) -> bool:
        """
        Run all setup steps.
        
        Args:
            progress_callback: Callback for progress updates
            skip_completed: If True, skip steps that are already complete
            
        Returns:
            True if all steps completed successfully
        """
        if progress_callback:
            progress_callback("🚀 Starting Wan2.2 setup...")
            progress_callback("   This will take approximately 10-15 minutes")
            progress_callback("")
        
        total_steps = len(self.SETUP_STEPS)
        completed = 0
        
        for i, step in enumerate(self.SETUP_STEPS):
            if progress_callback:
                progress_callback(f"\n📦 Step {i+1}/{total_steps}: {step['name']}")
            
            success = self.run_step(
                step['id'],
                progress_callback=progress_callback,
                force=not skip_completed
            )
            
            if not success:
                if progress_callback:
                    progress_callback(f"\n❌ Setup failed at step: {step['name']}")
                return False
            
            completed += 1
        
        if progress_callback:
            progress_callback("\n" + "="*50)
            progress_callback("✅ Wan2.2 setup complete!")
            progress_callback("   Models will be downloaded on-demand when you select them.")
            progress_callback("="*50)
        
        return True
    
    def get_incomplete_steps(self) -> List[Dict]:
        """Get list of steps that are not complete."""
        incomplete = []
        for step in self.SETUP_STEPS:
            if not self.check_step_complete(step['id']):
                incomplete.append(step)
        return incomplete
