#!/usr/bin/env python3
"""
RunPod Manager - Automated GPU Pod Deployment

Handles RunPod API interactions for listing GPUs and deploying pods.
"""
import requests
import time
from typing import List, Dict, Optional, Tuple


class RunPodManager:
    """Manage RunPod GPU pod deployment and lifecycle."""
    
    GRAPHQL_ENDPOINT = "https://api.runpod.io/graphql"
    PYTORCH_IMAGE = "runpod/pytorch:2.8.0-py3.11-cuda12.4.1-devel-ubuntu22.04"
    
    def __init__(self, api_key: str):
        """
        Initialize RunPod manager.
        
        Args:
            api_key: RunPod API key
        """
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    
    def get_available_gpus(self) -> List[Dict]:
        """
        Query RunPod for available GPU types with pricing.
        
        Returns:
            List of GPU dictionaries with specs and pricing
        """
        query = """
        query {
            gpuTypes {
                id
                displayName
                manufacturer
                memoryInGb
                secureCloud
                communityCloud
                communityPrice
                securePrice
                communitySpotPrice
                secureSpotPrice
                maxGpuCount
            }
        }
        """
        
        try:
            response = requests.post(
                self.GRAPHQL_ENDPOINT,
                json={"query": query},
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                raise Exception(f"GraphQL errors: {data['errors']}")
            
            gpu_types = data.get("data", {}).get("gpuTypes", [])
            
            # Filter to GPUs suitable for Wan2.2 (>= 24GB VRAM) and AVAILABLE
            # Only show On-Demand and Secure Cloud (avoid spot due to interruption risk)
            suitable_gpus = []
            for gpu in gpu_types:
                vram = gpu.get("memoryInGb", 0)
                is_available = gpu.get("maxGpuCount", 0) > 0
                
                if vram >= 24 and is_available:  # Minimum for TI2V-5B AND must be available
                    # Add derived fields for UI display
                    gpu["vram_gb"] = vram
                    gpu["available"] = True
                    
                    # Get best reliable price (prefer community on-demand, then secure)
                    # Skip spot instances - they can be interrupted mid-setup/generation
                    prices = []
                    if gpu.get("communityPrice"):
                        prices.append(("Community On-Demand", gpu["communityPrice"]))
                    if gpu.get("securePrice"):
                        prices.append(("Secure Cloud", gpu["securePrice"]))
                    
                    if prices:
                        gpu["best_price_type"], gpu["best_price"] = min(prices, key=lambda x: x[1])
                    else:
                        gpu["best_price_type"] = "N/A"
                        gpu["best_price"] = 0.0
                    
                    suitable_gpus.append(gpu)
            
            # Sort by VRAM then price
            suitable_gpus.sort(key=lambda x: (x["vram_gb"], x["best_price"]))
            
            return suitable_gpus
            
        except Exception as e:
            raise Exception(f"Failed to fetch GPU types: {str(e)}")
    
    def create_pod(
        self,
        name: str,
        gpu_type_id: str,
        gpu_count: int = 1,
        container_disk_gb: int = 150,
        volume_disk_gb: int = 0,
        docker_image: Optional[str] = None,
        env_vars: Optional[Dict[str, str]] = None,
        ports: Optional[str] = None
    ) -> Tuple[str, Dict]:
        """
        Create a new GPU pod.
        
        Args:
            name: Pod name
            gpu_type_id: GPU type ID from gpuTypes query
            gpu_count: Number of GPUs
            container_disk_gb: Container disk size in GB
            volume_disk_gb: Volume disk size in GB (0 for none)
            docker_image: Docker image (uses PyTorch 2.8.0 if None)
            env_vars: Environment variables dict
            ports: Exposed ports (e.g., "8888/http,22/tcp")
        
        Returns:
            Tuple of (pod_id, pod_info_dict)
        """
        if docker_image is None:
            docker_image = self.PYTORCH_IMAGE
        
        # Build mutation with explicit port exposure
        # ports format: "22/tcp" ensures SSH is exposed via TCP
        mutation = """
        mutation {
            podFindAndDeployOnDemand(
                input: {
                    name: "%s"
                    imageName: "%s"
                    gpuTypeId: "%s"
                    cloudType: SECURE
                    gpuCount: %d
                    containerDiskInGb: %d
                    volumeInGb: %d
                    startSsh: true
                    ports: "22/tcp"
                }
            ) {
                id
                desiredStatus
                imageName
                runtime {
                    uptimeInSeconds
                    ports {
                        ip
                        privatePort
                        publicPort
                        type
                    }
                    gpus {
                        id
                        gpuUtilPercent
                        memoryUtilPercent
                    }
                }
            }
        }
        """ % (name, docker_image, gpu_type_id, gpu_count, container_disk_gb, volume_disk_gb)
        
        try:
            response = requests.post(
                self.GRAPHQL_ENDPOINT,
                json={"query": mutation},
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                raise Exception(f"GraphQL errors: {data['errors']}")
            
            pod_data = data.get("data", {}).get("podFindAndDeployOnDemand", {})
            
            if not pod_data or not pod_data.get("id"):
                raise Exception("Failed to create pod - no pod ID returned")
            
            pod_id = pod_data["id"]
            
            return pod_id, pod_data
            
        except Exception as e:
            raise Exception(f"Failed to create pod: {str(e)}")
    
    def get_pod(self, pod_id: str) -> Dict:
        """
        Get pod information.
        
        Args:
            pod_id: Pod ID
            
        Returns:
            Pod information dictionary
        """
        query = """
        query {
            pod(input: {podId: "%s"}) {
                id
                name
                desiredStatus
                imageName
                machine {
                    gpuDisplayName
                }
                runtime {
                    uptimeInSeconds
                    ports {
                        ip
                        privatePort
                        publicPort
                        type
                    }
                    gpus {
                        id
                        gpuUtilPercent
                        memoryUtilPercent
                    }
                }
            }
        }
        """ % pod_id
        
        try:
            response = requests.post(
                self.GRAPHQL_ENDPOINT,
                json={"query": query},
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                raise Exception(f"GraphQL errors: {data['errors']}")
            
            return data.get("data", {}).get("pod", {})
            
        except Exception as e:
            raise Exception(f"Failed to get pod info: {str(e)}")
    
    def wait_for_pod_ready(self, pod_id: str, timeout: int = 300, callback=None) -> bool:
        """
        Wait for pod to be running and SSH accessible.
        
        Args:
            pod_id: Pod ID
            timeout: Maximum wait time in seconds
            callback: Optional callback function for progress updates
            
        Returns:
            True if pod is ready, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                pod_info = self.get_pod(pod_id)
                
                status = pod_info.get("desiredStatus", "UNKNOWN")
                runtime = pod_info.get("runtime")
                
                if callback:
                    callback(f"Pod status: {status}")
                
                # Check if pod is running and has runtime info
                if status == "RUNNING" and runtime:
                    ports = runtime.get("ports", [])
                    
                    # Check if SSH port (22) is exposed
                    ssh_port = None
                    for port in ports:
                        if port.get("privatePort") == 22 and port.get("type") == "tcp":
                            ssh_port = port.get("publicPort")
                            break
                    
                    if ssh_port:
                        if callback:
                            callback(f"✅ Pod ready! SSH port: {ssh_port}")
                        return True
                
                time.sleep(5)
                
            except Exception as e:
                if callback:
                    callback(f"⚠️ Error checking pod: {str(e)}")
                time.sleep(5)
        
        return False
    
    def get_ssh_connection_info(self, pod_id: str) -> Tuple[Optional[str], Optional[int]]:
        """
        Get SSH connection information for a pod.
        
        Args:
            pod_id: Pod ID
            
        Returns:
            Tuple of (ip_address, ssh_port) or (None, None) if not available
        """
        try:
            pod_info = self.get_pod(pod_id)
            runtime = pod_info.get("runtime")
            
            if not runtime:
                return None, None
            
            ports = runtime.get("ports", [])
            
            for port in ports:
                if port.get("privatePort") == 22 and port.get("type") == "tcp":
                    ip = port.get("ip")
                    public_port = port.get("publicPort")
                    
                    if ip and public_port:
                        return ip, public_port
            
            return None, None
            
        except Exception as e:
            raise Exception(f"Failed to get SSH connection info: {str(e)}")
    
    def terminate_pod(self, pod_id: str) -> bool:
        """
        Terminate a pod.
        
        Args:
            pod_id: Pod ID
            
        Returns:
            True if successful
        """
        mutation = """
        mutation {
            podTerminate(input: {podId: "%s"})
        }
        """ % pod_id
        
        try:
            response = requests.post(
                self.GRAPHQL_ENDPOINT,
                json={"query": mutation},
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                raise Exception(f"GraphQL errors: {data['errors']}")
            
            return True
            
        except Exception as e:
            raise Exception(f"Failed to terminate pod: {str(e)}")
