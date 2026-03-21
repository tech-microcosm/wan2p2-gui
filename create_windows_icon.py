#!/usr/bin/env python3
"""
Create a proper Windows ICO file from PNG images
"""
from PIL import Image
import os

def create_ico_file():
    """Create a Windows ICO file with multiple sizes"""
    
    # Icon sizes to include in the ICO file
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    
    # Load the base image
    base_image_path = 'src-tauri/icons/512x512.png'
    
    if not os.path.exists(base_image_path):
        print(f"Error: {base_image_path} not found")
        return False
    
    # Open the base image
    img = Image.open(base_image_path)
    
    # Convert to RGBA if not already
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # Create resized versions
    images = []
    for size in sizes:
        resized = img.resize(size, Image.Resampling.LANCZOS)
        images.append(resized)
    
    # Save as ICO
    output_path = 'src-tauri/icons/icon.ico'
    images[0].save(
        output_path,
        format='ICO',
        sizes=sizes,
        append_images=images[1:]
    )
    
    print(f"✅ Created Windows ICO file: {output_path}")
    print(f"   Sizes included: {', '.join([f'{s[0]}x{s[1]}' for s in sizes])}")
    
    # Verify the file
    file_size = os.path.getsize(output_path)
    print(f"   File size: {file_size} bytes")
    
    return True

if __name__ == '__main__':
    try:
        create_ico_file()
    except Exception as e:
        print(f"❌ Error creating ICO file: {e}")
        import traceback
        traceback.print_exc()
