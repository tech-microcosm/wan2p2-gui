#!/usr/bin/env python3
"""
Create valid PNG icons using proper CRC calculation
"""
import struct
import zlib
import os

def create_valid_png(width, height, output_path):
    """Create a valid PNG file with proper CRC checksums"""
    
    # PNG signature
    png_sig = b'\x89PNG\r\n\x1a\n'
    
    # IHDR chunk data
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    ihdr_chunk = b'IHDR' + ihdr_data
    ihdr_crc = zlib.crc32(ihdr_chunk) & 0xffffffff
    ihdr = struct.pack('>I', len(ihdr_data)) + ihdr_chunk + struct.pack('>I', ihdr_crc)
    
    # Create image data with gradient and camera icon
    pixels = bytearray()
    
    for y in range(height):
        for x in range(width):
            # Gradient background (purple to blue)
            r = int(102 + (x / width) * 50)
            g = int(51 + (x / width) * 100)
            b = int(153 + (x / width) * 100)
            a = 255
            
            # Draw camera icon in center
            cx = width // 2
            cy = height // 2
            dx = x - cx
            dy = y - cy
            dist = (dx*dx + dy*dy) ** 0.5
            
            # Camera body (circle)
            if dist < width * 0.35 and dist > width * 0.18:
                r, g, b = 255, 255, 255
            # Camera lens (smaller circle)
            elif dist < width * 0.18:
                r, g, b = 50, 50, 50
            # Lens highlight
            elif dist < width * 0.08 and dx < 0 and dy < 0:
                r, g, b = 200, 200, 200
            
            pixels.extend([r, g, b, a])
    
    # Create scanlines with filter byte
    scanlines = bytearray()
    for y in range(height):
        scanlines.append(0)  # No filter
        for x in range(width):
            idx = (y * width + x) * 4
            scanlines.extend(pixels[idx:idx+4])
    
    # Compress image data
    compressed = zlib.compress(bytes(scanlines), 9)
    
    # IDAT chunk
    idat_chunk = b'IDAT' + compressed
    idat_crc = zlib.crc32(idat_chunk) & 0xffffffff
    idat = struct.pack('>I', len(compressed)) + idat_chunk + struct.pack('>I', idat_crc)
    
    # IEND chunk
    iend_chunk = b'IEND'
    iend_crc = zlib.crc32(iend_chunk) & 0xffffffff
    iend = struct.pack('>I', 0) + iend_chunk + struct.pack('>I', iend_crc)
    
    # Write PNG file
    with open(output_path, 'wb') as f:
        f.write(png_sig)
        f.write(ihdr)
        f.write(idat)
        f.write(iend)
    
    print(f"✅ Created {width}x{height} icon: {output_path}")

def main():
    """Generate all required icon sizes"""
    sizes = [32, 128, 256, 512]
    
    os.makedirs('src-tauri/icons', exist_ok=True)
    
    for size in sizes:
        output = f'src-tauri/icons/{size}x{size}.png'
        create_valid_png(size, size, output)
    
    # Create 128x128@2x (same as 256x256)
    import shutil
    shutil.copy('src-tauri/icons/256x256.png', 'src-tauri/icons/128x128@2x.png')
    print("✅ Created 128x128@2x icon")
    
    print("\n✅ All icons generated successfully with valid CRC checksums!")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
