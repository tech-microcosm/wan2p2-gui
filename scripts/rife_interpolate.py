#!/usr/bin/env python3
"""
RIFE Frame Interpolation Script for Wan2.2

This script is deployed to /root/rife_interpolate.py on the RunPod pod.
It uses Practical-RIFE to interpolate frames and create smoother videos.
"""
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
            # Insert 1 interpolated frame (2x)
            mid = interpolate_frames(model, frames[i], frames[i+1], device, scale)
            output_frames.append(mid)
        elif multi == 4:
            # Insert 3 interpolated frames (4x)
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
    # When we double frames but keep same FPS, video becomes 2x longer
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
