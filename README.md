# Wan2.2 Video Generator

A desktop GUI application for generating high-quality AI videos using Wan2.2 models on RunPod GPU pods.

![Wan2.2 Video Generator](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Features

- **GPU-Aware Model Selection**: Automatically detects GPU VRAM and shows only viable models
- **Quality-First Defaults**: Pre-selects the best quality/speed tradeoff for your GPU
- **Lazy Model Loading**: Downloads models only when you select them (not upfront)
- **Flexible Resolution**: Supports 480P, 720P, and 1080P with memory-aware recommendations
- **Seamless Video Stitching**: Supports 2s, 5s, and 10s videos with automatic I2V continuation
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Quick Start

### Prerequisites

- Python 3.10+
- A RunPod GPU pod with SSH access
- SSH key for authentication

### Installation (Development)

1. Clone this repository:
```bash
git clone https://github.com/your-username/wan2p2-gui.git
cd wan2p2-gui
```

2. Create and activate a virtual environment:
```bash
python -m venv diffusion
source diffusion/bin/activate  # Linux/macOS
# or
diffusion\Scripts\activate  # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
python -m src.main
```

### Building Executable

To create a standalone executable:

```bash
python build.py
```

The executable will be created in the `dist/` directory.

## Usage

### 1. Connect to Your GPU Pod

1. Launch the application
2. Enter your RunPod pod's SSH details:
   - **IP Address**: Found in RunPod pod details
   - **SSH Port**: Usually shown as "SSH Port" in RunPod
   - **SSH Key Path**: Path to your private SSH key (e.g., `~/.ssh/id_ed25519`)
3. Click **Test Connection**

### 2. Setup Wan2.2 (First Time Only)

If this is a fresh pod, click **Setup Wan2.2**. This will:
- Install system dependencies (git, ffmpeg)
- Clone Wan2.2 repository
- Install PyTorch and Python dependencies
- Install Flash Attention 2
- Setup RIFE for frame interpolation

This takes approximately 10-15 minutes.

### 3. Generate Videos

1. Go to the **Generate Video** tab
2. Enter a detailed prompt describing your video
3. Select:
   - **Duration**: 2s, 5s, or 10s
   - **Model**: Based on your GPU VRAM
   - **Resolution**: 480P, 720P, or 1080P
   - **Seed**: For reproducible results
4. Click **Generate Video**

## Models

| Model | Speed (5s) | Quality | Min VRAM | Best For |
|-------|------------|---------|----------|----------|
| **TI2V-5B** | ~3 min | Good | 24GB | Fast iterations, testing |
| **T2V-A14B** | ~6-7 min | Excellent | 40GB | High-quality final renders |
| **I2V-A14B** | ~8-10 min | Excellent | 40GB | Video continuation |

### Model Selection by GPU

| GPU VRAM | Available Models | Recommended |
|----------|------------------|-------------|
| 24GB | TI2V-5B only | TI2V-5B |
| 40GB | TI2V-5B, T2V-A14B (480P) | T2V-A14B |
| 80GB+ | All models, all resolutions | T2V-A14B (720P) |

## Resolution Guide

| Resolution | Size | Speed | VRAM Usage | Notes |
|------------|------|-------|------------|-------|
| **480P** | 640×360 | Fast | Low | Best for testing prompts |
| **720P** | 1280×720 | Medium | Medium | Recommended balance |
| **1080P** | 1920×1080 | Slow | High | Requires 80GB+ VRAM |

## Video Duration

- **2 seconds**: 25 frames → RIFE 2× → 49 frames (~1.5-3 min)
- **5 seconds**: 61 frames → RIFE 2× → 121 frames (~3-7 min)
- **10 seconds**: 2 segments stitched with I2V continuation (~6-14 min)

## Tips for Best Results

1. **Be specific**: Describe subjects, actions, lighting, camera angles
2. **Include style**: Mention cinematography style, mood, atmosphere
3. **Test first**: Use 480P and 2s duration to test prompts quickly
4. **Use seeds**: Same seed produces the same video for iterations
5. **Enable "Enhance prompt"**: Automatically adds quality keywords

### Example Prompts

**Nature:**
> A majestic eagle soaring over snow-capped mountains at sunset, golden light reflecting off its wings, dramatic clouds in the background

**Character:**
> A samurai warrior standing in a field of cherry blossoms, wind gently moving their robes, petals floating in the air, cinematic lighting

**Abstract:**
> Flowing liquid metal forming geometric shapes, iridescent colors reflecting light, smooth continuous motion, dark background

## Project Structure

```
wan2p2-gui/
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point, Gradio UI
│   ├── ssh_manager.py       # SSH/SCP operations
│   ├── config_manager.py    # Configuration persistence
│   ├── gpu_manager.py       # GPU detection and model selection
│   ├── model_manager.py     # Lazy model downloading
│   ├── setup_manager.py     # Remote Wan2.2 setup
│   ├── video_generator.py   # Video generation pipeline
│   └── utils.py             # Helper functions
├── scripts/
│   ├── remote_setup.sh      # Bash script for pod setup
│   └── rife_interpolate.py  # RIFE interpolation script
├── assets/
│   └── icon.png             # App icon
├── requirements.txt         # Python dependencies
├── build.py                 # PyInstaller build script
└── README.md               # This file
```

## Troubleshooting

### Connection Issues

- **"Connection failed"**: Check IP, port, and SSH key path
- **"Authentication failed"**: Ensure your SSH key matches the one in RunPod
- **"Permission denied"**: Run `chmod 600 ~/.ssh/id_ed25519`

### GPU Detection

- **"Could not detect GPU"**: Ensure nvidia-smi is available on the pod
- **"No viable models"**: Your GPU may not have enough VRAM

### Setup Issues

- **"Setup failed"**: Check pod has internet access
- **"Flash Attention failed"**: May need more time, or try re-running

### Generation Issues

- **"OOM error"**: Try lower resolution or smaller model
- **"Model not found"**: Re-run model download
- **"RIFE failed"**: Ensure RIFE setup completed successfully

## Configuration

Configuration is saved to `~/.wan2_gui_config.json` and includes:
- SSH connection details
- Last detected GPU info
- Generation history
- Model download status

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- [Wan2.2](https://github.com/wenhao728/Wan2.2) - The underlying video generation model
- [Practical-RIFE](https://github.com/hzwer/Practical-RIFE) - Frame interpolation
- [Gradio](https://gradio.app/) - Web UI framework
- [Paramiko](https://www.paramiko.org/) - SSH implementation

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
