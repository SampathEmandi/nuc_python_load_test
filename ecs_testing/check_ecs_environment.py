"""
ECS Environment Checker - Check ECS task resource limits and configuration.
"""

import os
import json
import sys
import logging
from pathlib import Path

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def check_ecs_environment():
    """Check ECS environment and resource limits."""
    
    print("="*60)
    print("ECS TASK RESOURCE LIMITS CHECK")
    print("="*60)
    
    # Check if running in ECS
    ecs_metadata_uri = os.environ.get('ECS_CONTAINER_METADATA_URI_V4')
    if ecs_metadata_uri:
        print("[OK] Running in ECS")
        print(f"  Metadata URI: {ecs_metadata_uri}")
        
        # Try to get task metadata
        try:
            import urllib.request
            metadata = json.loads(
                urllib.request.urlopen(f"{ecs_metadata_uri}/task", timeout=2).read()
            )
            print(f"\nTask ARN: {metadata.get('TaskARN', 'N/A')[:80]}...")
            print(f"Cluster: {metadata.get('Cluster', 'N/A')}")
            print(f"Task Definition: {metadata.get('Family', 'N/A')}")
            print(f"Revision: {metadata.get('Revision', 'N/A')}")
        except Exception as e:
            print(f"\n[WARN] Could not fetch task metadata: {e}")
    else:
        print("[WARN] Not detected as ECS task (or metadata unavailable)")
        print("  This script can still check system limits")
    
    # Check CPU/Memory from environment (ECS sets these)
    cpu_units = os.environ.get('ECS_CPU_LIMIT', '')
    memory_mb = os.environ.get('ECS_MEMORY_LIMIT', '')
    
    if cpu_units:
        cpu_vcpu = int(cpu_units) / 1024  # ECS CPU is in CPU units (1024 = 1 vCPU)
        print(f"\nCPU: {cpu_vcpu:.2f} vCPU ({cpu_units} CPU units)")
    else:
        print("\nCPU: Not available from environment")
        try:
            import psutil
            cpu_count = psutil.cpu_count()
            print(f"  Detected: {cpu_count} CPU cores")
        except:
            pass
    
    if memory_mb:
        memory_gb = int(memory_mb) / 1024
        print(f"Memory: {memory_gb:.2f} GB ({memory_mb} MB)")
        # Estimate connections based on memory
        # Reserve 50% for system, use 50% for connections at 3KB each
        available_for_connections = (int(memory_mb) * 0.5) / 0.003
        print(f"  -> Can support ~{int(available_for_connections)} connections (rough estimate)")
    else:
        print("Memory: Not available from environment")
        try:
            import psutil
            mem = psutil.virtual_memory()
            total_mb = mem.total / (1024 * 1024)
            available_mb = mem.available / (1024 * 1024)
            print(f"  Total: {total_mb:.0f} MB")
            print(f"  Available: {available_mb:.0f} MB")
            available_for_connections = (available_mb * 0.5) / 0.003
            print(f"  -> Can support ~{int(available_for_connections)} connections (rough estimate)")
        except ImportError:
            print("  Install psutil for detailed memory info: pip install psutil")
    
    # File descriptors
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        print(f"\nFile descriptors: soft={soft}, hard={hard}")
        print(f"  -> Can support ~{soft - 100} connections")
        
        # ECS containers often have lower defaults
        if soft < 4096:
            print(f"  [WARN] Low limit! Consider setting in task definition:")
            print(f"     ulimits: [{{name: nofile, softLimit: 65536, hardLimit: 65536}}]")
        elif soft < 65536:
            print(f"  [INFO] Consider increasing to 65536 for better capacity")
        else:
            print(f"  [OK] Good limit for high connection counts")
    except:
        print("\nFile descriptors: Unable to check (Windows?)")
    
    # Network mode
    network_mode = os.environ.get('ECS_NETWORK_MODE', 'unknown')
    if network_mode != 'unknown':
        print(f"\nNetwork mode: {network_mode}")
        if network_mode == 'awsvpc':
            print("  -> Each task gets its own ENI (better isolation)")
        elif network_mode == 'bridge':
            print("  -> Shared network (better connection density)")
        elif network_mode == 'host':
            print("  -> Uses host network (best performance)")
    
    # Check Python version
    print(f"\nPython version: {sys.version.split()[0]}")
    
    # Check if required packages are available
    print(f"\nRequired packages:")
    packages = ['asyncio', 'websockets', 'aiohttp']
    for pkg in packages:
        try:
            __import__(pkg)
            print(f"  [OK] {pkg}")
        except ImportError:
            print(f"  [MISSING] {pkg}")
    
    print(f"\n{'='*60}")
    print("RECOMMENDATIONS:")
    print(f"{'='*60}")
    print("1. Set ulimits in task definition for file descriptors")
    print("2. Monitor CloudWatch metrics: CPUUtilization, MemoryUtilization")
    print("3. Start with 100 sessions, increase gradually")
    print("4. Watch for: NetworkCreditError, connection timeouts")
    print("5. Use service auto-scaling based on connection count")
    
    return {
        'ecs_detected': ecs_metadata_uri is not None,
        'cpu_units': cpu_units,
        'memory_mb': memory_mb,
        'file_descriptors_soft': soft if 'soft' in locals() else None,
        'network_mode': network_mode
    }


if __name__ == "__main__":
    check_ecs_environment()

