#!/usr/bin/env python3
"""
Test SSH connection to RunPod GPU pod with diagnostics
"""
import sys
import os
sys.path.insert(0, '/home/chinmay/projects/wan2p2-gui')

from src.ssh_manager import SSHManager
from src.ssh_key_manager import SSHKeyManager

# Pod details
POD_IP = "213.173.107.22"
POD_PORT = 22
SSH_KEY = "~/.ssh/id_ed25519"

print("=" * 70)
print("SSH Connection Diagnostic Test")
print("=" * 70)

# Check available keys
print("\n1. Checking available SSH keys...")
available_keys = SSHKeyManager.find_available_keys()
if available_keys:
    print(f"   ✅ Found {len(available_keys)} SSH key(s):")
    for key in available_keys:
        print(f"      - {key['name']} ({key['type']})")
        print(f"        Path: {key['path']}")
        
        # Check permissions
        mode = os.stat(key['path']).st_mode
        perms = oct(mode)[-3:]
        if perms == "600":
            print(f"        Permissions: {perms} ✅")
        else:
            print(f"        Permissions: {perms} ⚠️ (should be 600)")
else:
    print("   ❌ No SSH keys found in ~/.ssh")

# Get default key
default_key = SSHKeyManager.get_default_key_path()
print(f"\n   Default key: {default_key}")

# Test connection
print(f"\n2. Testing SSH connection to {POD_IP}:{POD_PORT}...")
print(f"   Using key: {SSH_KEY}")
print(f"   Username: root")

try:
    ssh = SSHManager(host=POD_IP, port=POD_PORT, key_path=SSH_KEY)
    
    print("   Attempting connection...")
    if ssh.connect():
        print("   ✅ SSH connection successful!")
        
        # Try a simple command
        print("\n3. Testing remote command execution...")
        exit_code, stdout, stderr = ssh.execute_command("nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits")
        
        if exit_code == 0:
            vram_mb = int(stdout.strip().split('\n')[0])
            vram_gb = vram_mb // 1024
            print(f"   ✅ GPU VRAM detected: {vram_gb}GB")
        else:
            print(f"   ⚠️ Could not detect GPU: {stderr}")
        
        ssh.close()
    else:
        print("   ❌ SSH connection failed")
        print("\n   TROUBLESHOOTING:")
        print("   - Check if your SSH key is authorized on the pod")
        print("   - See SSH_SETUP_GUIDE.md for solutions")
        print("   - Try using RunPod's web terminal to authorize your key")
        
except Exception as e:
    print(f"   ❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
