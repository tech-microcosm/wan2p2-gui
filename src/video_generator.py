"""
Video Generator - Handles video generation pipeline with Wan2.2
"""
import os
import re
import time
import tempfile
from typing import Callable, Dict, Optional, Tuple
from .ssh_manager import SSHManager
from .model_manager import ModelManager
from .gpu_manager import GPUManager


class VideoGenerator:
    """Generate videos using Wan2.2 with RIFE interpolation."""
    
    # Frame calculations for different durations
    # 2s: 48 frames direct, no RIFE interpolation
    # 5s: Base frames depend on RIFE multiplier to avoid GPU OOM
    #     - 2x RIFE: 61 base frames → 121 final frames
    #     - 4x RIFE: 31 base frames → 121 final frames (safer for 48GB GPU)
    # 10s: 2 segments of 5s each, stitched together
    DURATION_CONFIG = {
        2: {'frame_num': 48, 'output_frames': 48, 'rife_multi': None, 'segments': 1, 'use_rife': False},
        5: {'frame_num': 61, 'output_frames': 121, 'rife_multi': 2, 'segments': 1, 'use_rife': True},
        10: {'frame_num': 61, 'output_frames': 242, 'rife_multi': 2, 'segments': 2, 'use_rife': True}
    }
    
    # Time estimates per model (in minutes) - based on official benchmarks
    TIME_ESTIMATES = {
        'ti2v-5b': {2: '~2 min', 5: '~4 min', 10: '~8 min'},
        't2v-a14b': {2: '~8 min', 5: '~15 min', 10: '~30 min'},  # A14B is slower due to MoE
        'i2v-a14b': {2: '~8 min', 5: '~15 min', 10: '~30 min'},
    }
    
    def __init__(
        self, 
        ssh_manager: SSHManager, 
        model_manager: ModelManager,
        gpu_manager: Optional[GPUManager] = None
    ):
        """
        Initialize video generator.
        
        Args:
            ssh_manager: SSHManager for remote operations
            model_manager: ModelManager for model downloads
            gpu_manager: GPUManager for resolution handling
        """
        self.ssh = ssh_manager
        self.model_manager = model_manager
        self.gpu_manager = gpu_manager or GPUManager(ssh_manager)
    
    def generate_video(
        self,
        prompt: str,
        duration: int,
        model: str,
        resolution: str,
        seed: int = 42,
        progress_callback: Optional[Callable[[str], None]] = None,
        enhance_prompt: bool = True,
        rife_multiplier: int = 2,
        sample_steps: int = 20,
        disable_offloading: bool = False,
        enable_tiling: bool = False,
        input_image: Optional[str] = None,
        input_audio: Optional[str] = None,
        tts_text: Optional[str] = None
    ) -> Tuple[Optional[str], str]:
        """
        Generate a video with the specified parameters.
        
        Args:
            prompt: Text prompt describing the video
            duration: Video duration in seconds (2, 5, or 10)
            model: Model key (e.g., 'ti2v-5b')
            resolution: Resolution (e.g., '720P')
            seed: Random seed for reproducibility
            progress_callback: Callback for progress updates
            enhance_prompt: If True, use LLM to enhance prompt
            rife_multiplier: RIFE interpolation multiplier (2 or 4)
            sample_steps: Number of diffusion steps (8, 12, 16, or 20)
            disable_offloading: Disable model offloading (keeps model in VRAM, needs 40-45GB)
            enable_tiling: Enable tiling for memory optimization
            input_image: Path to input image (for I2V/S2V models)
            input_audio: Path to input audio (for S2V model)
            
        Returns:
            Tuple of (local_video_path, status_message)
        """
        try:
            if progress_callback:
                progress_callback(f"🎬 Starting video generation...")
                progress_callback(f"   Model: {model}")
                progress_callback(f"   Duration: {duration}s")
                progress_callback(f"   Resolution: {resolution}")
                progress_callback(f"   Seed: {seed}")
                progress_callback(f"   Steps: {sample_steps}")
                if enable_tiling:
                    progress_callback(f"   Tiling: Enabled")
            
            # Early VRAM check and warnings
            vram_check_result = self._check_vram_requirements(model, duration, resolution, progress_callback)
            if vram_check_result:
                return None, vram_check_result
            
            # Validate duration
            if duration not in self.DURATION_CONFIG:
                return None, f"❌ Invalid duration: {duration}. Must be 2, 5, or 10 seconds."
            
            # Ensure model is downloaded
            if progress_callback:
                progress_callback("\n📦 Checking model availability...")
            
            if not self.model_manager.ensure_model_downloaded(model, progress_callback):
                return None, f"❌ Failed to download model: {model}"
            
            # Enhance prompt if requested (use LLM on pod)
            if enhance_prompt:
                if progress_callback:
                    progress_callback("\n🤖 Enhancing prompt with LLM...")
                prompt = self._enhance_prompt_llm(prompt, model, input_image)
                if progress_callback:
                    progress_callback(f"📝 Enhanced prompt:\n   {prompt}")
            
            # Always show the final prompt being used
            if progress_callback:
                progress_callback(f"\n📋 Final prompt: {prompt}")
            
            # Upload input files to pod if needed
            remote_image_path = None
            remote_audio_path = None
            
            if input_image:
                if progress_callback:
                    progress_callback("\n📤 Uploading input image...")
                remote_image_path = self._upload_file(input_image, "input_image.png")
            
            if input_audio:
                if progress_callback:
                    progress_callback("\n📤 Uploading audio file...")
                remote_audio_path = self._upload_file(input_audio, "input_audio.wav")
            
            # Generate based on duration and model type
            if duration == 10:
                return self._generate_10s_video(prompt, model, resolution, seed, progress_callback, rife_multiplier, sample_steps, disable_offloading, enable_tiling)
            elif model == 's2v-14b':
                return self._generate_s2v_video(prompt, duration, resolution, seed, progress_callback, sample_steps, disable_offloading, remote_image_path, remote_audio_path, tts_text)
            elif model in ['i2v-a14b'] and remote_image_path:
                return self._generate_i2v_video(prompt, duration, resolution, seed, progress_callback, rife_multiplier, sample_steps, disable_offloading, remote_image_path)
            else:
                return self._generate_single_segment(prompt, duration, model, resolution, seed, progress_callback, rife_multiplier, sample_steps, disable_offloading, enable_tiling)
            
        except Exception as e:
            error_msg = f"❌ Generation failed: {str(e)}"
            if progress_callback:
                progress_callback(error_msg)
            return None, error_msg
    
    def _check_vram_requirements(
        self, 
        model: str, 
        duration: int, 
        resolution: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Optional[str]:
        """
        Check if GPU has sufficient VRAM for the requested generation.
        Returns error message if insufficient, None if OK.
        """
        from .gpu_manager import GPUManager
        
        model_info = GPUManager.MODELS.get(model, {})
        current_vram = self.gpu_manager.get_vram() if self.gpu_manager else 48
        
        # If VRAM detection failed, default to 48GB and skip checks
        if current_vram is None:
            current_vram = 48
        
        # Check for specific OOM warnings
        oom_warning = model_info.get('oom_warning')
        vram_required = model_info.get('vram_actual_requirement') or model_info.get('vram_min', 40)
        
        if progress_callback:
            progress_callback(f"\n🔍 VRAM Check: {current_vram}GB available, {vram_required}GB required")
        
        # Special case: 10s T2V-A14B requires I2V-A14B for second segment
        if duration == 10 and model == 't2v-a14b':
            i2v_vram = GPUManager.MODELS.get('i2v-a14b', {}).get('vram_actual_requirement', 60)
            if current_vram < i2v_vram:
                error_msg = f"""❌ VRAM WARNING: 10-second T2V-A14B generation requires I2V-A14B model for the second 5s segment.

⚠️ I2V-A14B needs {i2v_vram}GB+ VRAM, but you have {current_vram}GB.

💡 Recommendations:
   • Use 5-second duration instead (works on {current_vram}GB)
   • Use TI2V-5B model for 10s videos (works on 24GB+)
   • Upgrade to 96GB+ GPU (e.g., RTX PRO 6000 Blackwell)

The generation will likely fail with OOM during the second segment stitching."""
                
                if progress_callback:
                    progress_callback(error_msg)
                return error_msg
        
        # Check model-specific VRAM requirements
        if current_vram < vram_required:
            error_msg = f"""❌ VRAM INSUFFICIENT: {model_info.get('name', model)} requires {vram_required}GB+ VRAM.

Your GPU: {current_vram}GB
Required: {vram_required}GB
Shortfall: {vram_required - current_vram}GB

"""
            if oom_warning:
                error_msg += f"⚠️ {oom_warning}\n\n"
            
            error_msg += """💡 Recommendations:
   • Use a smaller model (TI2V-5B works on 24GB+)
   • Upgrade GPU to 96GB+ (RTX PRO 6000 Blackwell recommended)
   • Use cloud GPU with sufficient VRAM"""
            
            if progress_callback:
                progress_callback(error_msg)
            return error_msg
        
        # Warning for models close to VRAM limit
        if current_vram < vram_required + 8:
            warning = f"⚠️ VRAM Warning: Running close to limit ({current_vram}GB available, {vram_required}GB required). OOM possible."
            if progress_callback:
                progress_callback(warning)
        
        return None
    
    def _enhance_prompt(self, prompt: str) -> str:
        """Add quality keywords to the prompt (fallback method)."""
        quality_suffix = ", high quality, 4K, professional cinematography, sharp focus, smooth motion"
        
        # Don't add if already has quality keywords
        if any(kw in prompt.lower() for kw in ['high quality', '4k', 'professional', 'cinematic']):
            return prompt
        
        return prompt.rstrip('.') + quality_suffix
    
    def _enhance_prompt_llm(self, prompt: str, model: str, input_image: Optional[str] = None) -> str:
        """
        Enhance prompt using Qwen LLM with optimizations for speed.
        Uses smaller 1.5B model with caching for faster subsequent calls.
        """
        try:
            escaped_prompt = prompt.replace("'", "'\\''").replace('"', '\\"')
            
            # Optimized LLM enhancement with smaller model and caching
            extend_cmd = f"""cd /root/Wan2.2 && python -c "
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
import sys

try:
    # Use smaller 1.5B model instead of 3B for faster loading
    model_name = 'Qwen/Qwen2.5-1.5B-Instruct'
    cache_dir = '/root/.cache/huggingface'
    
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16,
        device_map='auto',
        cache_dir=cache_dir,
        trust_remote_code=True,
        low_cpu_mem_usage=True
    )
    tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir, trust_remote_code=True)
    
    system_prompt = '''You are a professional video prompt engineer. Enhance the prompt with rich visual details.
Include: camera angles, lighting, motion, atmosphere, and quality keywords.
Keep it concise (2-3 sentences max). Output ONLY the enhanced prompt.'''
    
    messages = [
        {{'role': 'system', 'content': system_prompt}},
        {{'role': 'user', 'content': 'Enhance: {escaped_prompt}'}}
    ]
    
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer([text], return_tensors='pt').to(model.device)
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=120,
            temperature=0.7,
            top_p=0.9,
            do_sample=True,
            num_beams=1,
            pad_token_id=tokenizer.eos_token_id
        )
    
    response = tokenizer.decode(outputs[0][len(inputs.input_ids[0]):], skip_special_tokens=True)
    print(response.strip())
    
except Exception as e:
    print('{escaped_prompt}', end='')
    sys.exit(0)
"
"""
            exit_code, stdout, stderr = self.ssh.execute_command(extend_cmd, timeout=180)
            
            if exit_code == 0 and stdout.strip():
                enhanced = stdout.strip()
                # If response is too similar to input or too long, use fallback
                if len(enhanced) > 500 or enhanced == prompt:
                    return self._enhance_prompt(prompt)
                return enhanced
            else:
                return self._enhance_prompt(prompt)
                
        except Exception as e:
            return self._enhance_prompt(prompt)
    
    def _upload_file(self, local_path: str, remote_filename: str) -> str:
        """Upload a file to the pod and return the remote path."""
        remote_path = f"/root/Wan2.2/{remote_filename}"
        
        try:
            # Use SFTP to upload the file
            self.ssh.upload_file(local_path, remote_path)
            return remote_path
        except Exception as e:
            raise Exception(f"Failed to upload file: {str(e)}")
    
    def _generate_i2v_video(
        self,
        prompt: str,
        duration: int,
        resolution: str,
        seed: int,
        progress_callback: Optional[Callable[[str], None]] = None,
        rife_multiplier: int = 2,
        sample_steps: int = 20,
        disable_offloading: bool = False,
        image_path: str = None
    ) -> Tuple[Optional[str], str]:
        """Generate video from image using I2V-A14B model."""
        config = self.DURATION_CONFIG[duration]
        
        if duration == 5 and rife_multiplier == 4:
            frame_num = 31
        else:
            frame_num = config['frame_num']
        
        ckpt_dir = self.model_manager.get_ckpt_dir('i2v-a14b')
        size = self._get_size_string(resolution)
        escaped_prompt = prompt.replace("'", "'\\''")
        
        # Get target dimensions from resolution
        res_info = self.gpu_manager.RESOLUTIONS.get(resolution, {})
        target_width = res_info.get('width', 480)
        target_height = res_info.get('height', 832)
        
        # Preprocess image: resize to match target resolution
        if progress_callback:
            progress_callback(f"\n🖼️ Preprocessing image to {target_width}x{target_height}...")
        
        processed_image_path = "/root/Wan2.2/input_processed.png"
        resize_cmd = f"""python -c "
from PIL import Image
img = Image.open('{image_path}')
original_size = img.size
print(f'Original image: {{original_size[0]}}x{{original_size[1]}}')
img_resized = img.resize(({target_width}, {target_height}), Image.Resampling.LANCZOS)
img_resized.save('{processed_image_path}')
# Verify the saved image
img_verify = Image.open('{processed_image_path}')
print(f'Saved image: {{img_verify.size[0]}}x{{img_verify.size[1]}}')
"
"""
        exit_code, stdout, stderr = self.ssh.execute_command(resize_cmd)
        if exit_code != 0:
            return None, f"❌ Image preprocessing failed: {stderr[:300]}"
        
        if progress_callback:
            progress_callback(f"   {stdout.strip()}")
            progress_callback(f"   ✅ Image resized to {target_width}x{target_height}")
            progress_callback(f"   📐 Size parameter: {size}")
        
        # Double-check the processed image before generation
        verify_cmd = f"""python -c "from PIL import Image; img = Image.open('{processed_image_path}'); print(f'Final check: {{img.size[0]}}x{{img.size[1]}}, Mode: {{img.mode}}') " """
        exit_code, verify_out, _ = self.ssh.execute_command(verify_cmd)
        if progress_callback and exit_code == 0:
            progress_callback(f"   {verify_out.strip()}")
            
        if progress_callback:
            progress_callback(f"\n🎥 Generating I2V video with {frame_num} frames...")
        
        # I2V-A14B needs offloading even for 96GB GPUs for optimal memory usage
        opt_flags = "--offload_model True --t5_cpu --convert_model_dtype"
        
        gen_cmd = f"""cd /root/Wan2.2 && python generate.py \\
    --task i2v-A14B \\
    --size {size} \\
    --frame_num {frame_num} \\
    --sample_steps {sample_steps} \\
    {opt_flags} \\
    --ckpt_dir {ckpt_dir} \\
    --base_seed {seed} \\
    --image {processed_image_path} \\
    --prompt '{escaped_prompt}' \\
    --save_file output_raw.mp4
"""
        
        exit_code, stdout, stderr = self.ssh.execute_command(
            gen_cmd,
            progress_callback=lambda line: self._parse_generation_progress(line, progress_callback)
        )
        
        # Check for OOM errors
        if self._check_oom_error(stderr, progress_callback):
            return None, "❌ I2V generation failed: CUDA Out of Memory (OOM). GPU ran out of VRAM."
        
        if exit_code != 0:
            return None, f"❌ I2V generation failed: {stderr[:500]}"
        
        # Apply RIFE if needed
        if duration >= 5 and rife_multiplier > 1:
            if progress_callback:
                progress_callback(f"\n🔄 Applying {rife_multiplier}x RIFE interpolation...")
            
            rife_cmd = f"cd /root && python rife_interpolate.py --input /root/Wan2.2/output_raw.mp4 --output /root/Wan2.2/output_final.mp4 --multi {rife_multiplier}"
            exit_code, stdout, stderr = self.ssh.execute_command(rife_cmd)
            
            if exit_code != 0:
                return None, f"❌ RIFE interpolation failed: {stderr[:500]}"
            
            remote_path = "/root/Wan2.2/output_final.mp4"
        else:
            remote_path = "/root/Wan2.2/output_raw.mp4"
        
        # Download result
        if progress_callback:
            progress_callback("\n📥 Downloading video...")
        
        import tempfile
        local_path = tempfile.mktemp(suffix="_i2v.mp4", dir="outputs")
        if not self.ssh.download_file(remote_path, local_path):
            return None, "❌ Failed to download I2V video"
        
        return local_path, "✅ I2V video generated successfully!"
    
    def _generate_s2v_video(
        self,
        prompt: str,
        duration: int,
        resolution: str,
        seed: int,
        progress_callback: Optional[Callable[[str], None]] = None,
        sample_steps: int = 20,
        disable_offloading: bool = False,
        image_path: str = None,
        audio_path: str = None,
        tts_text: str = None
    ) -> Tuple[Optional[str], str]:
        """Generate speech-to-video using S2V-14B model with audio file."""
        if not image_path:
            return None, "❌ S2V model requires a reference image"
        
        if not audio_path:
            return None, "❌ S2V model requires an audio file"
        
        ckpt_dir = self.model_manager.get_ckpt_dir('s2v-14b')
        size = self._get_size_string(resolution)
        escaped_prompt = prompt.replace("'", "'\\''")
        
        # Get target dimensions from resolution
        res_info = self.gpu_manager.RESOLUTIONS.get(resolution, {})
        target_width = res_info.get('width', 480)
        target_height = res_info.get('height', 832)
        
        # Preprocess image: resize to match target resolution
        if progress_callback:
            progress_callback(f"\n🖼️ Preprocessing image to {target_width}x{target_height}...")
        
        processed_image_path = "/root/Wan2.2/input_s2v_processed.png"
        resize_cmd = f"""python -c "
from PIL import Image
img = Image.open('{image_path}')
original_size = img.size
print(f'Original image: {{original_size[0]}}x{{original_size[1]}}')
img_resized = img.resize(({target_width}, {target_height}), Image.Resampling.LANCZOS)
img_resized.save('{processed_image_path}')
img_verify = Image.open('{processed_image_path}')
print(f'Saved image: {{img_verify.size[0]}}x{{img_verify.size[1]}}')
"
"""
        exit_code, stdout, stderr = self.ssh.execute_command(resize_cmd)
        if exit_code != 0:
            return None, f"❌ Image preprocessing failed: {stderr[:300]}"
        
        if progress_callback:
            progress_callback(f"   {stdout.strip()}")
            progress_callback(f"   ✅ Image resized to {target_width}x{target_height}")
        
        if progress_callback:
            progress_callback(f"\n Generating S2V video (audio-synced)...")
        
        # S2V-14B always needs offloading for 48GB GPUs
        opt_flags = "--offload_model True --t5_cpu --convert_model_dtype"
        
        gen_cmd = f"""cd /root/Wan2.2 && PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True python generate.py \\
    --task s2v-14B \\
    --size {size} \\
    --sample_steps {sample_steps} \\
    {opt_flags} \\
    --ckpt_dir {ckpt_dir} \\
    --base_seed {seed} \\
    --image {processed_image_path} \\
    --audio {audio_path} \\
    --prompt '{escaped_prompt}' \\
    --save_file output_s2v.mp4
"""
        
        exit_code, stdout, stderr = self.ssh.execute_command(
            gen_cmd,
            progress_callback=lambda line: self._parse_generation_progress(line, progress_callback),
            timeout=1800  # 30 minutes for S2V model loading + generation
        )
        
        # Check for OOM errors
        if self._check_oom_error(stderr, progress_callback):
            return None, "❌ S2V generation failed: CUDA Out of Memory (OOM). GPU ran out of VRAM."
        
        if exit_code != 0:
            error_msg = stderr if stderr else stdout
            return None, f"❌ S2V generation failed: {error_msg[-1000:]}"
        
        # Download result
        if progress_callback:
            progress_callback("\n📥 Downloading video...")
        
        import tempfile
        local_path = tempfile.mktemp(suffix="_s2v.mp4", dir="outputs")
        if not self.ssh.download_file("/root/Wan2.2/output_s2v.mp4", local_path):
            return None, "❌ Failed to download S2V video"
        
        return local_path, "✅ S2V video generated successfully!"
    
    def _get_size_string(self, resolution: str) -> str:
        """Convert resolution to size string for generate.py."""
        return self.gpu_manager.get_resolution_size(resolution)
    
    def _generate_single_segment(
        self,
        prompt: str,
        duration: int,
        model: str,
        resolution: str,
        seed: int,
        progress_callback: Optional[Callable[[str], None]] = None,
        rife_multiplier: int = 2,
        sample_steps: int = 20,
        disable_offloading: bool = False,
        enable_tiling: bool = False
    ) -> Tuple[Optional[str], str]:
        """Generate a 2s or 5s video (single segment)."""
        config = self.DURATION_CONFIG[duration]
        
        # Adjust frame count based on RIFE multiplier to avoid GPU OOM
        # For 5s videos: 2x RIFE uses 61 frames, 4x RIFE uses 31 frames
        # Both result in ~121 final frames, keeping GPU memory manageable
        if duration == 5 and rife_multiplier == 4:
            frame_num = 31  # 31 base + 4x RIFE = 121 frames
        else:
            frame_num = config['frame_num']
        
        task_name = self.model_manager.get_model_task_name(model)
        ckpt_dir = self.model_manager.get_ckpt_dir(model)
        size = self._get_size_string(resolution)
        
        # Escape prompt for shell
        escaped_prompt = prompt.replace("'", "'\\''")
        
        # Get time estimate for this model (adjust for steps)
        base_time = self.TIME_ESTIMATES.get(model, {}).get(duration, '~5 min')
        step_factor = sample_steps / 20.0
        time_est = f"{base_time} (scaled for {sample_steps} steps)"
        
        if progress_callback:
            progress_callback(f"\n🎥 Generating {frame_num} frames with {sample_steps} steps...")
            progress_callback(f"   Estimated time: {time_est}")
            if disable_offloading:
                progress_callback(f"   ⚡ Offloading disabled - using full VRAM mode (faster)")
        
        # Check memory status before generation
        mem_error = self._check_memory_status(progress_callback)
        if mem_error:
            return None, mem_error
        
        # Build optimization flags based on offloading setting and model type
        # T2V-A14B works best on 48GB with minimal offloading (just dtype conversion)
        # Aggressive offloading (--offload_model True --t5_cpu) causes OOM on 48GB
        is_14b_model = '14b' in model.lower() or 'a14b' in model.lower()
        
        if disable_offloading and not is_14b_model:
            # High VRAM mode for smaller models (5B): only dtype conversion
            # Requires ~24-30GB VRAM but faster
            opt_flags = "--convert_model_dtype"
        elif is_14b_model and model == 't2v-a14b':
            # T2V-A14B on 48GB: use minimal offloading (just dtype conversion)
            # Full offloading causes OOM due to memory fragmentation
            opt_flags = "--convert_model_dtype"
            if progress_callback:
                progress_callback("   ⚡ Using optimized settings for T2V-A14B on 48GB VRAM")
        else:
            # For I2V-A14B or when offloading is explicitly enabled:
            # Use T5 CPU offloading to save ~11GB VRAM
            opt_flags = "--offload_model True --t5_cpu --convert_model_dtype"
        
        # Note: --use_tiling is not available in standard Wan2.2
        # The enable_tiling parameter is kept for future compatibility but not used
        
        # Generate raw video
        gen_cmd = f"""cd /root/Wan2.2 && python generate.py \\
    --task {task_name} \\
    --size {size} \\
    --frame_num {frame_num} \\
    --sample_steps {sample_steps} \\
    {opt_flags} \\
    --ckpt_dir {ckpt_dir} \\
    --base_seed {seed} \\
    --prompt '{escaped_prompt}' \\
    --save_file output_raw.mp4
"""
        
        exit_code, stdout, stderr = self.ssh.execute_command(
            gen_cmd,
            progress_callback=lambda line: self._parse_generation_progress(line, progress_callback)
        )
        
        # Check for OOM errors
        if self._check_oom_error(stderr, progress_callback):
            return None, "❌ Generation failed: CUDA Out of Memory (OOM). GPU ran out of VRAM. Try reducing resolution or using a smaller model."
        
        if exit_code != 0:
            return None, f"❌ Generation failed: {stderr[:500]}"
        
        # Verify raw video exists
        if not self.ssh.file_exists("/root/Wan2.2/output_raw.mp4"):
            return None, "❌ Generation completed but output file not found"
        
        # Clear GPU and RAM memory before RIFE interpolation to avoid OOM
        if config.get('use_rife', False):
            self._cleanup_memory(progress_callback)
        
        # Run RIFE interpolation only if configured for this duration
        output_file = f"/root/Wan2.2/output_{duration}s.mp4"
        
        if config.get('use_rife', False):
            if progress_callback:
                progress_callback(f"\n🔄 Interpolating frames with RIFE ({rife_multiplier}x)...")
            
            rife_cmd = f"cd /root && python3 rife_interpolate.py --input /root/Wan2.2/output_raw.mp4 --output {output_file} --multi {rife_multiplier}"
            
            exit_code, stdout, stderr = self.ssh.execute_command(
                rife_cmd,
                progress_callback=lambda line: progress_callback(f"   {line}") if progress_callback else None
            )
            
            if exit_code != 0:
                return None, f"❌ RIFE interpolation failed: {stderr[:500]}"
        else:
            # No RIFE - just rename the raw file
            if progress_callback:
                progress_callback(f"\n📦 Finalizing video (no interpolation for {duration}s)...")
            
            mv_cmd = f"mv /root/Wan2.2/output_raw.mp4 {output_file}"
            self.ssh.execute_command(mv_cmd)
        
        # Download video
        if progress_callback:
            progress_callback(f"\n⬇️ Downloading video...")
        
        local_path = os.path.join(tempfile.gettempdir(), f"wan2_video_{duration}s_{seed}.mp4")
        
        def download_progress(filename, received, total):
            if progress_callback and total > 0:
                pct = (received / total) * 100
                progress_callback(f"   Download: {pct:.1f}% ({received // 1024 // 1024}MB / {total // 1024 // 1024}MB)")
        
        if not self.ssh.download_file(f"/root/Wan2.2/output_{duration}s.mp4", local_path, download_progress):
            return None, "❌ Failed to download video"
        
        if progress_callback:
            progress_callback(f"\n✅ Video generated successfully!")
            progress_callback(f"   Saved to: {local_path}")
        
        return local_path, "✅ Video generated successfully!"
    
    def _generate_10s_video(
        self,
        prompt: str,
        model: str,
        resolution: str,
        seed: int,
        progress_callback: Optional[Callable[[str], None]] = None,
        rife_multiplier: int = 2,
        sample_steps: int = 20,
        disable_offloading: bool = False,
        enable_tiling: bool = False
    ) -> Tuple[Optional[str], str]:
        """Generate a 10s video using T2V + I2V continuation."""
        config = self.DURATION_CONFIG[10]
        
        # Adjust frame count for 4x interpolation to avoid GPU OOM
        if rife_multiplier == 4:
            frame_num = 31  # 31 base + 4x RIFE = 121 frames per segment
        else:
            frame_num = config['frame_num']
        
        task_name = self.model_manager.get_model_task_name(model)
        ckpt_dir = self.model_manager.get_ckpt_dir(model)
        size = self._get_size_string(resolution)
        
        escaped_prompt = prompt.replace("'", "'\\''")
        
        # === SEGMENT 1: T2V Generation ===
        if progress_callback:
            progress_callback(f"\n🎥 Segment 1/2: Generating first 5 seconds with {sample_steps} steps...")
        
        # Build optimization flags - same as single segment generation
        is_14b_model = '14b' in model.lower() or 'a14b' in model.lower()
        
        if disable_offloading and not is_14b_model:
            opt_flags = "--convert_model_dtype"
        elif is_14b_model and model == 't2v-a14b':
            # T2V-A14B on 48GB: use minimal offloading (just dtype conversion)
            opt_flags = "--convert_model_dtype"
            if progress_callback:
                progress_callback("   ⚡ Using optimized settings for T2V-A14B on 48GB VRAM")
        else:
            # For I2V-A14B or when offloading is explicitly enabled
            opt_flags = "--offload_model True --t5_cpu --convert_model_dtype"
        
        # Note: --use_tiling is not available in standard Wan2.2
        
        seg1_cmd = f"""cd /root/Wan2.2 && python generate.py \\
    --task {task_name} \\
    --size {size} \\
    --frame_num {frame_num} \\
    --sample_steps {sample_steps} \\
    {opt_flags} \\
    --ckpt_dir {ckpt_dir} \\
    --base_seed {seed} \\
    --prompt '{escaped_prompt}' \\
    --save_file segment1_raw.mp4
"""
        
        exit_code, stdout, stderr = self.ssh.execute_command(
            seg1_cmd,
            progress_callback=lambda line: self._parse_generation_progress(line, progress_callback)
        )
        
        # Check for OOM errors
        if self._check_oom_error(stderr, progress_callback):
            return None, "❌ Segment 1 failed: CUDA Out of Memory (OOM). GPU ran out of VRAM."
        
        if exit_code != 0:
            return None, f"❌ Segment 1 generation failed: {stderr[:500]}"
        
        # Clear GPU and RAM memory before RIFE
        self._cleanup_memory(progress_callback)
        
        # Interpolate segment 1
        if progress_callback:
            progress_callback(f"\n🔄 Interpolating segment 1...")
        
        rife1_cmd = f"cd /root && python3 rife_interpolate.py --input /root/Wan2.2/segment1_raw.mp4 --output /root/Wan2.2/segment1_interp.mp4 --multi {rife_multiplier}"
        
        exit_code, _, stderr = self.ssh.execute_command(
            rife1_cmd,
            progress_callback=lambda line: progress_callback(f"   {line}") if progress_callback else None
        )
        
        if exit_code != 0:
            return None, f"❌ Segment 1 interpolation failed: {stderr[:500]}"
        
        # Extract last frame for I2V
        if progress_callback:
            progress_callback(f"\n📸 Extracting last frame for continuation...")
        
        # Get frame count first
        frame_count_cmd = "cd /root/Wan2.2 && ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 segment1_interp.mp4"
        exit_code, stdout, _ = self.ssh.execute_command(frame_count_cmd)
        
        try:
            total_frames = int(stdout.strip()) - 1  # 0-indexed, so last frame is count-1
        except ValueError:
            total_frames = 120  # Fallback
        
        extract_cmd = f"cd /root/Wan2.2 && ffmpeg -y -i segment1_interp.mp4 -vf 'select=eq(n\\,{total_frames})' -vsync 0 -frames:v 1 last_frame.png"
        
        exit_code, _, stderr = self.ssh.execute_command(extract_cmd)
        
        if exit_code != 0:
            return None, f"❌ Failed to extract last frame: {stderr[:500]}"
        
        # === SEGMENT 2: I2V Continuation ===
        if progress_callback:
            progress_callback(f"\n🎥 Segment 2/2: Generating continuation...")
        
        # Get I2V model for continuation
        i2v_model = self.model_manager.get_i2v_model_for_continuation(model)
        
        # Ensure I2V model is downloaded if different from T2V model
        if i2v_model != model:
            if progress_callback:
                progress_callback(f"   Checking I2V model ({i2v_model}) for continuation...")
            if not self.model_manager.ensure_model_downloaded(i2v_model, progress_callback):
                return None, f"❌ Failed to download I2V model: {i2v_model}"
        
        i2v_task = self.model_manager.get_model_task_name(i2v_model)
        i2v_ckpt = self.model_manager.get_ckpt_dir(i2v_model)
        
        # For I2V, we need to use the image input
        seg2_cmd = f"""cd /root/Wan2.2 && python generate.py \\
    --task {i2v_task} \\
    --size {size} \\
    --frame_num {frame_num} \\
    --sample_steps {sample_steps} \\
    {opt_flags} \\
    --ckpt_dir {i2v_ckpt} \\
    --base_seed {seed + 1} \\
    --prompt '{escaped_prompt}' \\
    --image last_frame.png \\
    --save_file segment2_raw.mp4
"""
        
        exit_code, stdout, stderr = self.ssh.execute_command(
            seg2_cmd,
            progress_callback=lambda line: self._parse_generation_progress(line, progress_callback)
        )
        
        # Check for OOM errors
        if self._check_oom_error(stderr, progress_callback):
            return None, "❌ Segment 2 failed: CUDA Out of Memory (OOM). GPU ran out of VRAM."
        
        if exit_code != 0:
            return None, f"❌ Segment 2 generation failed: {stderr[:500]}"
        
        # Clear GPU and RAM memory before RIFE
        self._cleanup_memory(progress_callback)
        
        # Interpolate segment 2
        if progress_callback:
            progress_callback(f"\n🔄 Interpolating segment 2...")
        
        rife2_cmd = f"cd /root && python3 rife_interpolate.py --input /root/Wan2.2/segment2_raw.mp4 --output /root/Wan2.2/segment2_interp.mp4 --multi {rife_multiplier}"
        
        exit_code, _, stderr = self.ssh.execute_command(
            rife2_cmd,
            progress_callback=lambda line: progress_callback(f"   {line}") if progress_callback else None
        )
        
        if exit_code != 0:
            return None, f"❌ Segment 2 interpolation failed: {stderr[:500]}"
        
        # Stitch videos together
        if progress_callback:
            progress_callback(f"\n🔗 Stitching segments together...")
        
        stitch_cmd = """cd /root/Wan2.2 && cat > filelist.txt << 'EOF'
file 'segment1_interp.mp4'
file 'segment2_interp.mp4'
EOF
ffmpeg -y -f concat -safe 0 -i filelist.txt -c copy video_10s.mp4"""
        
        exit_code, _, stderr = self.ssh.execute_command(stitch_cmd)
        
        if exit_code != 0:
            return None, f"❌ Video stitching failed: {stderr[:500]}"
        
        # Download final video
        if progress_callback:
            progress_callback(f"\n⬇️ Downloading video...")
        
        local_path = os.path.join(tempfile.gettempdir(), f"wan2_video_10s_{seed}.mp4")
        
        def download_progress(filename, received, total):
            if progress_callback and total > 0:
                pct = (received / total) * 100
                progress_callback(f"   Download: {pct:.1f}%")
        
        if not self.ssh.download_file("/root/Wan2.2/video_10s.mp4", local_path, download_progress):
            return None, "❌ Failed to download video"
        
        if progress_callback:
            progress_callback(f"\n✅ 10-second video generated successfully!")
            progress_callback(f"   Saved to: {local_path}")
        
        return local_path, "✅ 10-second video generated successfully!"
    
    def _check_memory_status(self, progress_callback: Optional[Callable[[str], None]] = None) -> Optional[str]:
        """Check RAM and VRAM status. Returns error message if critical, None if OK."""
        # Check RAM usage
        ram_cmd = "free -g | awk '/^Mem:/ {printf \"%d %d %.0f\", $2, $3, ($3/$2)*100}'"
        exit_code, stdout, _ = self.ssh.execute_command(ram_cmd)
        
        if exit_code == 0 and stdout.strip():
            try:
                total_ram, used_ram, ram_pct = stdout.strip().split()
                total_ram, used_ram, ram_pct = int(total_ram), int(used_ram), float(ram_pct)
                
                if progress_callback:
                    progress_callback(f"   💾 RAM: {used_ram}GB / {total_ram}GB ({ram_pct:.0f}%)")
                
                # Warning if RAM usage > 85%
                if ram_pct > 85:
                    warning = f"⚠️ RAM WARNING: {ram_pct:.0f}% used ({used_ram}/{total_ram}GB). Risk of OOM!"
                    if progress_callback:
                        progress_callback(f"\n{warning}")
                    
                    # If critically high, abort
                    if ram_pct > 95:
                        return f"❌ RAM CRITICAL: {ram_pct:.0f}% used. Aborting to prevent system OOM."
            except (ValueError, IndexError):
                pass
        
        # Check VRAM usage
        vram_cmd = "nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits | awk '{printf \"%d %d %.0f\", $1/1024, $3/1024, ($3/$1)*100}'"
        exit_code, stdout, _ = self.ssh.execute_command(vram_cmd)
        
        if exit_code == 0 and stdout.strip():
            try:
                total_vram, used_vram, vram_pct = stdout.strip().split()
                total_vram, used_vram, vram_pct = int(total_vram), int(used_vram), float(vram_pct)
                
                if progress_callback:
                    progress_callback(f"   🎮 VRAM: {used_vram}GB / {total_vram}GB ({vram_pct:.0f}%)")
            except (ValueError, IndexError):
                pass
        
        return None
    
    def _cleanup_memory(self, progress_callback: Optional[Callable[[str], None]] = None):
        """Aggressively clean up system and GPU memory."""
        if progress_callback:
            progress_callback("\n🧹 Cleaning up memory...")
        
        cleanup_cmds = [
            # Kill any lingering Python processes
            "pkill -9 -f 'python.*generate.py' || true",
            "sleep 1",
            # Clear GPU memory
            "python3 -c 'import torch; torch.cuda.empty_cache(); import gc; gc.collect()' || true",
            # Clear system cache (requires sudo, may fail but worth trying)
            "sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true",
            "sleep 1"
        ]
        
        for cmd in cleanup_cmds:
            self.ssh.execute_command(cmd)
    
    def _check_oom_error(self, stderr: str, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Check if stderr contains CUDA OOM or RAM OOM error and terminate if found."""
        oom_indicators = [
            'CUDA out of memory',
            'OutOfMemoryError',
            'RuntimeError: CUDA error: out of memory',
            'torch.cuda.OutOfMemoryError',
            'MemoryError',
            'Killed',  # Linux OOM killer
            'Cannot allocate memory'
        ]
        
        for indicator in oom_indicators:
            if indicator in stderr:
                if progress_callback:
                    progress_callback(f"\n❌ DETECTED: {indicator}")
                    progress_callback("\n🛑 Auto-terminating generation due to OOM...")
                
                # Aggressive cleanup
                self._cleanup_memory(progress_callback)
                
                return True
        
        return False
    
    def _parse_generation_progress(self, line: str, progress_callback: Optional[Callable[[str], None]] = None):
        """Parse and format generation progress output."""
        if not progress_callback:
            return
        
        # Look for step progress (e.g., "step 5/20" or percentage)
        step_match = re.search(r'(\d+)/(\d+)', line)
        pct_match = re.search(r'(\d+)%', line)
        
        if 'step' in line.lower() and step_match:
            current, total = step_match.groups()
            pct = (int(current) / int(total)) * 100
            progress_callback(f"   Generation: Step {current}/{total} ({pct:.0f}%)")
        elif pct_match:
            progress_callback(f"   Progress: {pct_match.group(1)}%")
        elif 'loading' in line.lower():
            progress_callback(f"   {line}")
        elif 'error' in line.lower() or 'failed' in line.lower():
            progress_callback(f"   ⚠️ {line}")
        elif 'saving' in line.lower() or 'complete' in line.lower():
            progress_callback(f"   ✅ {line}")
    
    def cleanup_remote_files(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Clean up temporary files on remote pod."""
        if progress_callback:
            progress_callback("🧹 Cleaning up temporary files...")
        
        cleanup_cmd = """cd /root/Wan2.2 && rm -f \\
    output_raw.mp4 \\
    output_2s.mp4 output_5s.mp4 \\
    segment1_raw.mp4 segment1_interp.mp4 \\
    segment2_raw.mp4 segment2_interp.mp4 \\
    last_frame.png \\
    video_10s.mp4 \\
    filelist.txt
"""
        
        exit_code, _, _ = self.ssh.execute_command(cleanup_cmd)
        
        if progress_callback:
            if exit_code == 0:
                progress_callback("✅ Cleanup complete")
            else:
                progress_callback("⚠️ Some files could not be cleaned up")
        
        return exit_code == 0
    
    def get_estimated_time(self, duration: int, model: str) -> str:
        """Get estimated generation time for display."""
        model_info = self.gpu_manager.MODELS.get(model, {})
        
        if duration == 2:
            return model_info.get('speed_2s', '~2 minutes')
        elif duration == 5:
            return model_info.get('speed_5s', '~5 minutes')
        elif duration == 10:
            return model_info.get('speed_10s', '~10 minutes')
        
        return '~5 minutes'
