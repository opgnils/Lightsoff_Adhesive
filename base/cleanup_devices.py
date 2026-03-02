#!/usr/bin/env python3
"""
Simple script to clean up any running Python processes on remote devices.
This should be run before starting tracking to ensure a clean state.
"""
import sys
import os
import subprocess

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from base.Devices import get_devices, check_online_devices

def cleanup_remote_python_processes(devices, config="config_lightsoff"):
    """
    Kill all Python processes on remote devices to ensure clean state.
    
    Args:
        devices (list): List of device dictionaries
        config (str): SSH config file name
    """
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    ssh_config_path = os.path.join(root, f'ssh/{config}')
    
    print("🧹 Cleaning up remote Python processes...")
    
    for device in devices:
        device_name = device['Host']
        print(f"\nCleaning {device_name}...")
        
        try:
            # First, check what Python processes are running
            check_command = [
                'ssh', '-F', ssh_config_path,
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ConnectTimeout=5',
                '-o', 'BatchMode=yes',
                device_name,
                'ps aux | grep python | grep -v grep'
            ]
            
            check_result = subprocess.run(check_command, capture_output=True, text=True, timeout=10)
            
            if check_result.returncode == 0 and check_result.stdout.strip():
                print(f"  Found Python processes on {device_name}:")
                for line in check_result.stdout.strip().split('\n'):
                    print(f"    {line}")
                
                # Kill all Python processes (except system ones)
                kill_command = [
                    'ssh', '-F', ssh_config_path,
                    '-o', 'StrictHostKeyChecking=no',
                    '-o', 'ConnectTimeout=5',
                    '-o', 'BatchMode=yes',
                    device_name,
                    # Kill python processes in user directories, but avoid system python
                    'pkill -f "python.*Documents" || pkill -f "python.*cambots" || pkill -f "python.*track_" || true'
                ]
                
                kill_result = subprocess.run(kill_command, capture_output=True, text=True, timeout=10)
                
                if kill_result.returncode == 0:
                    print(f"  ✅ Cleanup command sent to {device_name}")
                else:
                    print(f"  ⚠️  Kill command failed on {device_name}: {kill_result.stderr}")
                
                # Wait and verify
                import time
                time.sleep(2)
                
                verify_result = subprocess.run(check_command, capture_output=True, text=True, timeout=10)
                if verify_result.returncode == 0 and verify_result.stdout.strip():
                    remaining_count = len(verify_result.stdout.strip().split('\n'))
                    print(f"  ⚠️  {remaining_count} Python processes still running on {device_name}")
                else:
                    print(f"  ✅ No Python processes found on {device_name}")
            else:
                print(f"  ✅ No Python processes found on {device_name}")
                
        except subprocess.TimeoutExpired:
            print(f"  ❌ Timeout connecting to {device_name}")
        except Exception as e:
            print(f"  ❌ Error cleaning {device_name}: {e}")
    
    print("\n🧹 Remote cleanup complete!")

if __name__ == "__main__":
    CONFIG = "config_lightsoff"
    
    # Get devices
    devices = get_devices(config=CONFIG)
    
    # Check which are online
    online_devices = check_online_devices(devices)
    
    if not online_devices:
        print("No devices are online!")
        sys.exit(1)
    
    # Clean them up
    cleanup_remote_python_processes(online_devices, CONFIG)
