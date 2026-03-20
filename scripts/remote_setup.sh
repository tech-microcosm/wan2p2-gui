#!/bin/bash
# Wan2.2 Remote Setup Script
# This script sets up Wan2.2 and dependencies on a RunPod GPU pod

set -e

echo "========================================"
echo "Wan2.2 Setup Script"
echo "========================================"

# System dependencies
echo "[1/8] Installing system dependencies..."
apt update && apt install -y git wget ffmpeg
echo "✓ System dependencies installed"

# Clone Wan2.2
echo "[2/8] Cloning Wan2.2 repository..."
if [ -d "/root/Wan2.2" ]; then
    echo "  Wan2.2 already exists, pulling latest..."
    cd /root/Wan2.2 && git pull
else
    git clone https://github.com/wenhao728/Wan2.2.git /root/Wan2.2
fi
echo "✓ Wan2.2 repository ready"

# Install PyTorch
echo "[3/8] Installing PyTorch..."
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
echo "✓ PyTorch installed"

# Install Wan2.2 requirements
echo "[4/8] Installing Wan2.2 requirements..."
cd /root/Wan2.2
pip3 install -r requirements.txt
echo "✓ Wan2.2 requirements installed"

# Install Flash Attention
echo "[5/8] Installing Flash Attention 2..."
pip3 install flash-attn --no-build-isolation
echo "✓ Flash Attention installed"

# Clone RIFE
echo "[6/8] Setting up RIFE for frame interpolation..."
if [ -d "/root/Practical-RIFE" ]; then
    echo "  RIFE already exists"
else
    git clone https://github.com/hzwer/Practical-RIFE.git /root/Practical-RIFE
fi
echo "✓ RIFE repository ready"

# Install RIFE requirements
echo "[7/8] Installing RIFE requirements..."
cd /root/Practical-RIFE
pip3 install -r requirements.txt
echo "✓ RIFE requirements installed"

# Download RIFE model
echo "[8/8] Downloading RIFE model..."
mkdir -p /root/Practical-RIFE/train_log
if [ -f "/root/Practical-RIFE/train_log/flownet.pkl" ]; then
    echo "  RIFE model already exists"
else
    wget -q https://github.com/hzwer/Practical-RIFE/releases/download/4.0/flownet.pkl -O /root/Practical-RIFE/train_log/flownet.pkl
fi
echo "✓ RIFE model ready"

echo ""
echo "========================================"
echo "✓ Setup complete!"
echo "========================================"
echo ""
echo "Models will be downloaded on-demand when you generate your first video."
echo "Available models:"
echo "  - TI2V-5B (32GB) - Fast, good quality"
echo "  - T2V-A14B (27GB) - High quality"
echo "  - I2V-A14B (27GB) - Image-to-video continuation"
