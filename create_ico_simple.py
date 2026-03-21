#!/usr/bin/env python3
"""
Create a simple Windows ICO file without external dependencies
Uses a basic ICO format with embedded PNG data
"""
import struct
import os

def create_simple_ico():
    """Create a Windows ICO file from PNG files"""
    
    # Read PNG files
    png_files = [
        ('src-tauri/icons/32x32.png', 32),
        ('src-tauri/icons/128x128.png', 128),
        ('src-tauri/icons/256x256.png', 256),
    ]
    
    images = []
    for png_path, size in png_files:
        if os.path.exists(png_path):
            with open(png_path, 'rb') as f:
                png_data = f.read()
                images.append((size, png_data))
    
    if not images:
        print("❌ No PNG files found")
        return False
    
    # ICO file header
    ico_header = struct.pack('<HHH', 0, 1, len(images))  # Reserved, Type (1=ICO), Count
    
    # Calculate offset for image data
    offset = 6 + (16 * len(images))  # Header + directory entries
    
    # Build directory entries and image data
    directory = b''
    image_data = b''
    
    for size, png_data in images:
        # Directory entry (16 bytes)
        width = size if size < 256 else 0  # 0 means 256
        height = size if size < 256 else 0
        colors = 0  # 0 for PNG
        reserved = 0
        planes = 1
        bpp = 32  # 32-bit color
        size_bytes = len(png_data)
        
        directory += struct.pack('<BBBBHHII',
            width, height, colors, reserved,
            planes, bpp, size_bytes, offset
        )
        
        image_data += png_data
        offset += size_bytes
    
    # Write ICO file
    output_path = 'src-tauri/icons/icon.ico'
    with open(output_path, 'wb') as f:
        f.write(ico_header)
        f.write(directory)
        f.write(image_data)
    
    print(f"✅ Created Windows ICO file: {output_path}")
    print(f"   Sizes included: {', '.join([f'{s}x{s}' for s, _ in images])}")
    print(f"   File size: {os.path.getsize(output_path)} bytes")
    
    return True

if __name__ == '__main__':
    try:
        create_simple_ico()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
