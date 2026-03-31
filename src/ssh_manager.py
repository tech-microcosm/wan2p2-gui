"""
SSH Manager - Handles SSH/SCP operations using Paramiko
"""
import os
import re
import paramiko
from scp import SCPClient
from typing import Callable, Optional, Tuple
import threading
import time


class SSHManager:
    """Manages SSH connections and remote command execution on RunPod GPU pods."""
    
    def __init__(self, host: str, port: int, key_path: str, username: str = "root"):
        """
        Initialize SSH client with connection parameters.
        
        Args:
            host: Remote host IP address
            port: SSH port number
            key_path: Path to SSH private key file
            username: SSH username (default: root for RunPod)
        """
        self.host = host
        self.port = int(port)
        self.key_path = os.path.expanduser(key_path)
        self.username = username
        self.client: Optional[paramiko.SSHClient] = None
        self._connected = False
        self._lock = threading.Lock()
    
    def connect(self) -> bool:
        """
        Connect to remote pod.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self._lock:
                if self._connected and self.client:
                    return True
                
                self.client = paramiko.SSHClient()
                self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # Load private key
                if not os.path.exists(self.key_path):
                    raise FileNotFoundError(f"SSH key not found: {self.key_path}")
                
                # Try different key types
                pkey = None
                key_errors = []
                
                for key_class in [paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey]:
                    try:
                        pkey = key_class.from_private_key_file(self.key_path)
                        break
                    except Exception as e:
                        key_errors.append(f"{key_class.__name__}: {e}")
                
                if pkey is None:
                    raise ValueError(f"Could not load SSH key. Tried: {'; '.join(key_errors)}")
                
                self.client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    pkey=pkey,
                    timeout=30,
                    allow_agent=False,
                    look_for_keys=False,
                    banner_timeout=30
                )
                
                self._connected = True
                return True
                
        except paramiko.AuthenticationException as e:
            error_msg = f"Authentication failed: {e}\n\nThis usually means:\n- The SSH key is not authorized on the pod\n- The username 'root' is incorrect\n- The key has wrong permissions (should be 600)"
            print(error_msg)
            return False
        except paramiko.SSHException as e:
            error_msg = f"SSH error: {e}\n\nThis could mean:\n- Wrong port number\n- SSH service not running on pod\n- Network connectivity issue"
            print(error_msg)
            return False
        except Exception as e:
            error_msg = f"Connection error: {e}\n\nPlease check:\n- Pod IP address is correct\n- SSH key path is correct\n- Network connectivity"
            print(error_msg)
            return False
    
    def is_connected(self) -> bool:
        """Check if SSH connection is active."""
        if not self._connected or not self.client:
            return False
        try:
            transport = self.client.get_transport()
            if transport and transport.is_active():
                return True
        except Exception:
            pass
        self._connected = False
        return False
    
    def execute_command(
        self, 
        cmd: str, 
        progress_callback: Optional[Callable[[str], None]] = None,
        timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
        """
        Execute command on remote pod with real-time output streaming.
        
        Args:
            cmd: Command to execute
            progress_callback: Optional callback for progress updates
            timeout: Command timeout in seconds (None for no timeout)
            
        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        if not self.is_connected():
            if not self.connect():
                return (-1, "", "Not connected to remote host")
        
        try:
            # Get a transport and open a channel
            transport = self.client.get_transport()
            channel = transport.open_session()
            channel.set_combine_stderr(False)
            
            if timeout:
                channel.settimeout(timeout)
            
            # Execute command
            channel.exec_command(cmd)
            
            stdout_data = []
            stderr_data = []
            
            # Read output in real-time
            while True:
                # Check for stdout
                if channel.recv_ready():
                    chunk = channel.recv(4096).decode('utf-8', errors='replace')
                    stdout_data.append(chunk)
                    if progress_callback:
                        # Parse for progress indicators
                        for line in chunk.split('\n'):
                            if line.strip():
                                progress_callback(line.strip())
                
                # Check for stderr
                if channel.recv_stderr_ready():
                    chunk = channel.recv_stderr(4096).decode('utf-8', errors='replace')
                    stderr_data.append(chunk)
                    if progress_callback:
                        for line in chunk.split('\n'):
                            if line.strip():
                                progress_callback(f"[stderr] {line.strip()}")
                
                # Check if command finished
                if channel.exit_status_ready():
                    # Drain remaining output
                    while channel.recv_ready():
                        chunk = channel.recv(4096).decode('utf-8', errors='replace')
                        stdout_data.append(chunk)
                    while channel.recv_stderr_ready():
                        chunk = channel.recv_stderr(4096).decode('utf-8', errors='replace')
                        stderr_data.append(chunk)
                    break
                
                time.sleep(0.1)
            
            exit_code = channel.recv_exit_status()
            channel.close()
            
            return (exit_code, ''.join(stdout_data), ''.join(stderr_data))
            
        except Exception as e:
            return (-1, "", str(e))
    
    def upload_file(
        self, 
        local_path: str, 
        remote_path: str, 
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> bool:
        """
        Upload file to remote pod via SCP.
        
        Args:
            local_path: Path to local file
            remote_path: Destination path on remote
            progress_callback: Optional callback (filename, bytes_sent, total_bytes)
            
        Returns:
            True if successful
        """
        if not self.is_connected():
            if not self.connect():
                return False
        
        local_path = os.path.expanduser(local_path)
        
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local file not found: {local_path}")
        
        try:
            def progress(filename, size, sent):
                if progress_callback:
                    progress_callback(filename.decode() if isinstance(filename, bytes) else filename, sent, size)
            
            with SCPClient(self.client.get_transport(), progress=progress) as scp:
                scp.put(local_path, remote_path)
            
            return True
            
        except Exception as e:
            print(f"Upload error: {e}")
            return False
    
    def download_file(
        self, 
        remote_path: str, 
        local_path: str, 
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> bool:
        """
        Download file from remote pod via SCP.
        
        Args:
            remote_path: Path to remote file
            local_path: Destination path locally
            progress_callback: Optional callback (filename, bytes_received, total_bytes)
            
        Returns:
            True if successful
        """
        if not self.is_connected():
            if not self.connect():
                return False
        
        local_path = os.path.expanduser(local_path)
        
        # Ensure local directory exists
        local_dir = os.path.dirname(local_path)
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir)
        
        try:
            def progress(filename, size, received):
                if progress_callback:
                    progress_callback(filename.decode() if isinstance(filename, bytes) else filename, received, size)
            
            with SCPClient(self.client.get_transport(), progress=progress) as scp:
                scp.get(remote_path, local_path)
            
            return True
            
        except Exception as e:
            print(f"Download error: {e}")
            return False
    
    def file_exists(self, remote_path: str) -> bool:
        """Check if a file or directory exists on remote."""
        exit_code, _, _ = self.execute_command(f"test -e {remote_path}")
        return exit_code == 0
    
    def dir_exists(self, remote_path: str) -> bool:
        """Check if a directory exists on remote."""
        exit_code, _, _ = self.execute_command(f"test -d {remote_path}")
        return exit_code == 0
    
    def get_connection_info(self) -> dict:
        """Get connection information for display."""
        return {
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'key_path': self.key_path
        }
    
    def close(self):
        """Close SSH connection."""
        with self._lock:
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None
            self._connected = False
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
