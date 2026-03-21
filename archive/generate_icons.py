#!/usr/bin/env python3
"""
Generate professional app icons for Wan2.2 Video Generator
Creates PNG icons with a video camera design
"""
import struct
import os

def create_icon_png(size, output_path):
    """Create a simple PNG icon with a video camera design"""
    
    # Create a simple PNG with a gradient background and camera icon
    # Using minimal PNG structure
    
    width = size
    height = size
    
    # PNG signature
    png_sig = b'\x89PNG\r\n\x1a\n'
    
    # IHDR chunk (image header)
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    ihdr_crc = 0x90773546  # Pre-calculated CRC for standard IHDR
    ihdr_chunk = b'IHDR' + ihdr_data
    ihdr_crc_bytes = struct.pack('>I', ihdr_crc)
    ihdr = struct.pack('>I', len(ihdr_data)) + ihdr_chunk + ihdr_crc_bytes
    
    # Create image data - simple gradient with camera icon
    # This is a simplified approach using raw pixel data
    pixels = bytearray()
    
    for y in range(height):
        for x in range(width):
            # Create a gradient background (purple to blue)
            r = int(102 + (x / width) * 50)  # 102 to 152
            g = int(51 + (x / width) * 100)  # 51 to 151
            b = int(153 + (x / width) * 100)  # 153 to 253
            a = 255
            
            # Draw a simple camera icon in the center
            cx = width // 2
            cy = height // 2
            dx = x - cx
            dy = y - cy
            dist = (dx*dx + dy*dy) ** 0.5
            
            # Camera body (circle)
            if dist < width * 0.3:
                r, g, b = 255, 255, 255  # White camera body
            # Camera lens (smaller circle)
            elif dist < width * 0.15:
                r, g, b = 50, 50, 50  # Dark lens
            
            pixels.extend([r, g, b, a])
    
    # For simplicity, create a minimal valid PNG
    # Use zlib compression (minimal)
    import zlib
    
    # Create scanlines (one filter byte per line + pixel data)
    scanlines = bytearray()
    for y in range(height):
        scanlines.append(0)  # Filter type: None
        for x in range(width):
            idx = (y * width + x) * 4
            scanlines.extend(pixels[idx:idx+4])
    
    # Compress the image data
    compressed = zlib.compress(bytes(scanlines), 9)
    
    # IDAT chunk (image data)
    idat_crc = zlib.crc32(b'IDAT' + compressed) & 0xffffffff
    idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)
    
    # IEND chunk (image end)
    iend_crc = 0xae426082  # Standard IEND CRC
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
    
    # Write PNG file
    with open(output_path, 'wb') as f:
        f.write(png_sig)
        f.write(ihdr)
        f.write(idat)
        f.write(iend)
    
    print(f"✅ Created {size}x{size} icon: {output_path}")

def main():
    """Generate all required icon sizes"""
    sizes = [32, 128, 256, 512]
    
    os.makedirs('src-tauri/icons', exist_ok=True)
    
    for size in sizes:
        output = f'src-tauri/icons/{size}x{size}.png'
        create_icon_png(size, output)
    
    # Create 128x128@2x (same as 256x256)
    import shutil
    shutil.copy('src-tauri/icons/256x256.png', 'src-tauri/icons/128x128@2x.png')
    print("✅ Created 128x128@2x icon")
    
    print("\n✅ All icons generated successfully!")
    print("   Icons: 32x32, 128x128, 128x128@2x, 256x256, 512x512")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
