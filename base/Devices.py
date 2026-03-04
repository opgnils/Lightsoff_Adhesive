import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from yaspin import yaspin
import time

def ping_device(device_host, timeout=1):
    """
    Ping a device to check if it's online
    
    Args:
        device_host (str): IP address or hostname of the device
        timeout (int): Timeout in seconds for the ping
        
    Returns:
        bool: True if device is reachable, False otherwise
    """
    try:
        # Use ping command with timeout
        result = subprocess.run(
            ['ping', '-c', '1', '-W', str(timeout), device_host],
            capture_output=True,
            text=True,
            timeout=timeout + 1
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception as e:
        print(f"Error pinging {device_host}: {e}")
        return False

def check_online_devices(devices, max_workers=10):
    """
    Check which devices are online by pinging them in parallel
    
    Args:
        devices (list): List of device dictionaries
        max_workers (int): Maximum number of concurrent ping operations
        
    Returns:
        list: List of online devices
    """
    online_devices = []
    
    print("\nChecking device availability...")
    
    def ping_and_check(device):
        """Helper function to ping a device and return result"""
        device_host = device['HostName']
        device_name = device['Host']
        
        if ping_device(device_host):
            print(f"  {device_name} ({device_host}) - ✓ Online")
            return device
        else:
            print(f"  {device_name} ({device_host}) - ✗ Offline")
            return None
    
    # Use ThreadPoolExecutor for parallel pinging
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all ping tasks
        future_to_device = {executor.submit(ping_and_check, device): device for device in devices}
        
        # Collect results as they complete
        for future in as_completed(future_to_device):
            result = future.result()
            if result is not None:
                online_devices.append(result)
    
    return online_devices

def get_devices(config = 'config_lightsoff'):

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    path = os.path.join(root,f'ssh/{config}')

    with open(path, 'r') as file:
        config_lines = file.readlines()

    devices = []
    current_device = {}

    for line in config_lines:
        if line.startswith("Host "):
            if current_device:
                devices.append(current_device)
            current_device = {"Host": line.split()[1]}
        elif line.startswith("  HostName "):
            current_device["HostName"] = line.split()[1]
        elif line.startswith("  User "):
            current_device["User"] = line.split()[1]
    if current_device:
        devices.append(current_device)

    return devices

def get_network():
    try:
        result = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True)
        output = result.stdout
        ssid_line = next(line for line in output.split('\n') if "SSID" in line and "BSSID" not in line)
        ssid = ssid_line.split(":")[1].strip()
        return ssid        
    except Exception as e:
        return None
    
def execute_remote_python_file(device_host, device_user, python_file_path, venv_path="~/venv", password=None):
    """
    Execute a Python file on a remote device using SSH with virtual environment
    
    Args:
        device_host (str): IP address or hostname of the device
        device_user (str): Username for SSH connection
        python_file_path (str): Path to the Python file on the remote device
        venv_path (str): Path to the virtual environment on the remote device
        password (str): SSH password (optional, uses sshpass if provided)
    """
    try:
        # Build SSH command with or without password
        if password:
            ssh_command = [
                'sshpass', '-p', password,
                'ssh', '-o', 'StrictHostKeyChecking=no',
                f'{device_user}@{device_host}',
                f'cd ~/Documents/LightsOff_Project && source {venv_path}/bin/activate && python {python_file_path}'
            ]
        else:
            ssh_command = [
                'ssh', 
                f'{device_user}@{device_host}',
                f'cd ~/Documents/LightsOff_Project && source {venv_path}/bin/activate && python {python_file_path}'
            ]        
        
        # Execute the SSH command
        result = subprocess.run(ssh_command, capture_output=True, text=True, timeout=30)
        

        return result
                
    except subprocess.TimeoutExpired:
        print(f"Command timed out after 30 seconds")
    except Exception as e:
        print(f"Exception occurred while executing remote command: {e}")

def start_remote_python_file_in_thread(
    device_host, device_user, python_file_path, venv_path="~/venv", arguments = "", password=None, timeout=None, verbose=False
):
    """
    Start a Python file on a remote device using SSH in a background thread (non-blocking).
    Returns the Thread object
    """

    def run_remote():
        try:
            if verbose:
                print(f"[DEBUG] Preparing to start remote Python file: {python_file_path}")
                print(f"[DEBUG] Device host: {device_host}, user: {device_user}, venv: {venv_path}, password: {'***' if password else None}")
            if password:
                ssh_command = [
                    'sshpass', '-p', password,
                    'ssh', '-o', 'StrictHostKeyChecking=no',
                    f'{device_user}@{device_host}',
                    f'cd ~/Documents/LightsOff_Project && source {venv_path}/bin/activate && python {python_file_path} {arguments}'
                ]
            else:
                ssh_command = [
                    'ssh',
                    f'{device_user}@{device_host}',
                    f'cd ~/Documents/LightsOff_Project && source {venv_path}/bin/activate && python {python_file_path} {arguments}'
                ]
            if verbose:
                print(f"[DEBUG] SSH command: {' '.join(ssh_command)}")
            proc = subprocess.Popen(
                ssh_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            # Continuously read output
            while True:
                out = proc.stdout.readline()
                err = proc.stderr.readline()
                if verbose and out:
                    print(f"[REMOTE STDOUT] {out.strip()}")
                if verbose and err:
                    print(f"[REMOTE STDERR] {err.strip()}")
                if out == '' and err == '' and proc.poll() is not None:
                    break
            if verbose:
                print(f"[DEBUG] Remote process finished with code {proc.returncode}")
        except Exception as e:
            if verbose:
                print(f"[EXCEPTION] Exception occurred while executing remote command: {e}")

    thread = threading.Thread(target=run_remote, daemon=True)
    thread.start()
    return thread

def launch_remote_file(device, remote_python_file:str, remote_venv_path = "~/Documents/LightsOff_Project/lightsoff_env", arguments = ""):
    with yaspin(text=f"Lauching Remote Test on {device['Host']}...", color="light_green") as spinner:
        print(f"[DEBUG] Launching aruco tracking on device: {device}")
        # Paths on the remote device
        try:
            thread = start_remote_python_file_in_thread(
                device_host=device['HostName'],
                device_user=device['User'],
                python_file_path=remote_python_file,
                venv_path=remote_venv_path,
                arguments= arguments,
                password="lightsoff",
                timeout=None,
                verbose=False
            )
            spinner.ok("✅")
            print(f"[DEBUG] Thread started: {thread}")
            return True, thread
        except Exception as e:
            spinner.fail("💥")
            print(f"[EXCEPTION] Failed to launch file: {e}")
            return False,

def run_updates(devices, config = "config_lightsoff"):
    """
    Run deploy.sh for each device to push updates.
    Returns a dictionary with device hosts as keys and lists of updated files as values.
    """
    update_results = {}
    
    for device in devices:
        host = device['Host']
        print(f"updating {host}")
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'deploy.sh'))
        updated_files = []
        
        try:
            result = subprocess.run(
                ['bash', script_path, host, config],
                capture_output=True,
                text=True,
                timeout=120
            )
            print(f"Deploy to {host}: Return code {result.returncode}")
            
            # Parse rsync output to extract updated files
            if result.stdout:
                for line in result.stdout.split('\n'):
                    # rsync shows transferred files in the output
                    # Look for lines that indicate file transfers (excluding directory lines ending with /)
                    if line.strip() and not line.endswith('/') and not line.startswith('sending') and not line.startswith('total') and not line.startswith('sent') and not line.startswith('Deploying') and not line.startswith('Deployment'):
                        # Skip progress indicators and summary lines
                        if '%' not in line and 'bytes' not in line and 'speedup' not in line:
                            # Clean up the line (remove leading indicators like > or +)
                            clean_line = line.strip().lstrip('>+ ')
                            if clean_line and '/' in clean_line:
                                updated_files.append(clean_line)
                
                print(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                print(f"STDERR:\n{result.stderr}")
            
            update_results[host] = updated_files
            
        except Exception as e:
            print(f"Error deploying to {host}: {e}")
            update_results[host] = []
    
    print("Updates Complete")
    time.sleep(1)
    return update_results


def cleanup_remote_python_processes(devices, config="config_lightsoff"):
    """
    Simple function to kill any existing Python processes on remote devices.
    This ensures a clean state before starting new tracking processes.
    """
    print("🧹 Cleaning up any existing remote Python processes...")
    
    for device in devices:
        device_name = device['Host']
        print(f"  Checking {device_name}...")
        
        try:
            # First, check what Python processes are running
            check_command = [
                'sshpass', '-p', 'lightsoff',
                'ssh', '-o', 'StrictHostKeyChecking=no', 
                '-o', 'ConnectTimeout=5',
                f"{device['User']}@{device['HostName']}",
                'ps aux | grep python | grep -E "(cambots|track_)" | grep -v grep'
            ]
            
            check_result = subprocess.run(check_command, capture_output=True, text=True, timeout=10)
            
            if check_result.returncode == 0 and check_result.stdout.strip():
                processes = check_result.stdout.strip().split('\n')
                print(f"    Found {len(processes)} Python processes to kill:")
                for i, process in enumerate(processes, 1):
                    # Extract PID and command from ps output
                    parts = process.split()
                    if len(parts) >= 11:
                        pid = parts[1]
                        command = ' '.join(parts[10:])[:80] + "..." if len(' '.join(parts[10:])) > 80 else ' '.join(parts[10:])
                        print(f"      {i}. PID {pid}: {command}")
                    else:
                        print(f"      {i}. {process}")
                
                # Kill the processes with -9 (force kill)
                kill_command = [
                    'sshpass', '-p', 'lightsoff',
                    'ssh', '-o', 'StrictHostKeyChecking=no', 
                    '-o', 'ConnectTimeout=5',
                    f"{device['User']}@{device['HostName']}",
                    'pkill -9 -f "python.*cambots" || pkill -9 -f "python.*track_" || pkill -9 -f "UnifiedListener" || pkill -9 -f "AdhesiveListener" || true'
                ]
                
                kill_result = subprocess.run(kill_command, capture_output=True, text=True, timeout=10)
                print(f"    ✅ Kill command sent (exit code: {kill_result.returncode})")
                
                # Verify cleanup
                time.sleep(1)
                verify_result = subprocess.run(check_command, capture_output=True, text=True, timeout=10)
                if verify_result.returncode == 0 and verify_result.stdout.strip():
                    remaining = len(verify_result.stdout.strip().split('\n'))
                    print(f"    ⚠️  {remaining} processes still running after cleanup")
                else:
                    print(f"    ✅ All processes successfully terminated")
                    
            else:
                print(f"    ✅ No Python processes found")
            
        except Exception as e:
            print(f"    ❌ Warning: Could not clean {device_name}: {e}")
    
    print("🧹 Cleanup complete\n")

def launch_remote_adhesive_debug(device, arguments: str):
    """DEBUG helper: run AdhesiveControl.py exactly like manual Jetson test.

    This bypasses the venv and uses the full path with python3.
    """
    host = device["HostName"]
    user = device["User"]

    remote_cmd = (
        "cd ~/Documents/LightsOff_Project && "
        "python3 cambots/AdhesiveRobot/AdhesiveControl.py "
        f"\"{arguments}\""
    )

    ssh_command = [
        "sshpass",
        "-p",
        "lightsoff",
        "ssh",
        f"{user}@{host}",
        remote_cmd,
    ]

    print(f"[DEBUG] Adhesive SSH command for {device['Host']}: {' '.join(ssh_command)}")

    def run_remote():
        try:
            result = subprocess.run(
                ssh_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            print(f"[DEBUG] Adhesive stdout ({device['Host']}):\n{result.stdout}")
            if result.stderr:
                print(f"[DEBUG] Adhesive stderr ({device['Host']}):\n{result.stderr}")
        except Exception as e:
            print(f"Error running adhesive debug command on {device['Host']}: {e}")

    thread = threading.Thread(target=run_remote, daemon=True)
    thread.start()
    return True, thread

def ensure_adhesive_listener_running(device, port: int = 5001, force_restart: bool = False):
    """Ensure UnifiedListener.py is running on the remote device.

    Checks for an existing process and starts one if necessary.
    Uses UnifiedListener.py which handles adhesive motors (3 motors via VESC + Arduino).
    
    Args:
        device: Device configuration dictionary
        port: TCP port for unified listener (default 5001)
        force_restart: If True, kills existing listener and starts fresh. 
                      If False, only starts if not already running.
    """
    host = device["HostName"]
    user = device["User"]

    # Command to check if UnifiedListener is already running
    check_cmd = (
        'ps aux | grep -E "UnifiedListener" | grep -v grep'
    )

    ssh_check = [
        "sshpass",
        "-p",
        "lightsoff",
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=5",
        f"{user}@{host}",
        check_cmd,
    ]

    # First check if it's already running
    try:
        result = subprocess.run(ssh_check, capture_output=True, text=True, timeout=10)
        already_running = result.returncode == 0 and result.stdout.strip() != ""
    except Exception as e:
        print(f"[UnifiedListener] Error checking listener on {device['Host']}: {e}")
        already_running = False

    # If already running and not forcing restart, just verify port
    if already_running and not force_restart:
        print(f"[UnifiedListener] Already running on {device['Host']}, verifying port {port}...")
        
        # Verify port 5001 is listening
        port_check_cmd = (
            f"(lsof -i :{port} -sTCP:LISTEN 2>/dev/null || netstat -ln 2>/dev/null | grep ':{port}.*LISTEN') && "
            f"echo 'PORT_LISTENING' || echo 'PORT_NOT_READY'"
        )
        ssh_port_check = [
            "sshpass", "-p", "lightsoff", "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=5",
            f"{user}@{host}",
            port_check_cmd,
        ]
        
        try:
            port_result = subprocess.run(ssh_port_check, capture_output=True, text=True, timeout=10)
            port_listening = "PORT_LISTENING" in port_result.stdout
            
            if port_listening:
                print(f"[UnifiedListener] Already running and verified on {device['Host']} - port {port} listening")
                return True
            else:
                print(f"[UnifiedListener] Process running but port {port} not ready on {device['Host']}, will restart...")
                force_restart = True  # Port not ready, need to restart
        except Exception as e:
            print(f"[UnifiedListener] Error checking port on {device['Host']}: {e}, will restart...")
            force_restart = True

    # Kill existing listeners if forcing restart or if port wasn't ready
    if force_restart or already_running:
        kill_listener_cmd = (
            "pkill -9 -f 'UnifiedListener.py' 2>/dev/null; "
            "pkill -9 -f 'AdhesiveListener.py' 2>/dev/null; "
            "pkill -9 -f 'PressureListener.py' 2>/dev/null; "
            "pkill -9 -f 'nohup python3 cambots' 2>/dev/null; "
            "true"
        )
        
        ssh_kill = [
            "sshpass",
            "-p",
            "lightsoff",
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=5",
            f"{user}@{host}",
            kill_listener_cmd,
        ]
        
        try:
            subprocess.run(ssh_kill, capture_output=True, text=True, timeout=10)
            print(f"[UnifiedListener] Killed existing listener on {device['Host']}")
            time.sleep(1.5)  # Give the OS time to release port
        except Exception as e:
            print(f"[UnifiedListener] Warning: Could not kill existing listener on {device['Host']}: {e}")
            time.sleep(1.0)

    # Start the UnifiedListener in the background using nohup
    start_cmd = (
        "cd ~/Documents/LightsOff_Project && "
        "nohup python3 cambots/UnifiedListener.py "
        ">> unified_listener.log 2>&1 &"
    )

    ssh_start = [
        "sshpass",
        "-p",
        "lightsoff",
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=5",
        f"{user}@{host}",
        start_cmd,
    ]

    try:
        result = subprocess.run(ssh_start, capture_output=True, text=True, timeout=10)
        print(f"[UnifiedListener] Start command sent to {device['Host']}")
        
        # Wait and verify it actually started (with retries)
        # AdhesiveListener needs time to detect serial ports and initialize
        max_attempts = 10  # Increased from 5
        for attempt in range(max_attempts):
            time.sleep(1.5)  # Increased from 1 second - give more time for initialization
            
            # First check: Look for the process
            verify_result = subprocess.run(ssh_check, capture_output=True, text=True, timeout=10)
            process_running = verify_result.returncode == 0 and verify_result.stdout.strip() != ""
            
            # Second check: Verify port is listening
            port_check_cmd = (
                f"(lsof -i :{port} -sTCP:LISTEN 2>/dev/null || netstat -ln 2>/dev/null | grep ':{port}.*LISTEN') && "
                f"echo 'PORT_LISTENING' || echo 'PORT_NOT_READY'"
            )
            ssh_port_check = [
                "sshpass", "-p", "lightsoff", "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=5",
                f"{user}@{host}",
                port_check_cmd,
            ]
            port_result = subprocess.run(ssh_port_check, capture_output=True, text=True, timeout=10)
            port_listening = "PORT_LISTENING" in port_result.stdout
            
            if process_running and port_listening:
                print(f"[UnifiedListener] Successfully started and verified on {device['Host']} - port {port} listening (attempt {attempt + 1}/{max_attempts})")
                return True
            elif process_running:
                print(f"[UnifiedListener] Process running but port {port} not ready yet on {device['Host']} (attempt {attempt + 1}/{max_attempts}, waiting...)")
            else:
                print(f"[UnifiedListener] Process not detected yet on {device['Host']} (attempt {attempt + 1}/{max_attempts}, waiting...)")
        
        # If we get here, check one more time if at least the process is running
        verify_result = subprocess.run(ssh_check, capture_output=True, text=True, timeout=10)
        process_running = verify_result.returncode == 0 and verify_result.stdout.strip() != ""
        
        if process_running:
            print(f"[UnifiedListener] Process is running on {device['Host']} after {max_attempts} attempts")
            print(f"[UnifiedListener] Port may still be initializing - assuming success")
            return True
        else:
            print(f"[UnifiedListener] WARNING: Process not detected on {device['Host']} after {max_attempts} attempts")
            print(f"[UnifiedListener] Check the log file on the device: tail -30 ~/Documents/LightsOff_Project/unified_listener.log")
            return False  # Changed from True - if process isn't running, something is wrong
            
    except Exception as e:
        print(f"[UnifiedListener] Failed to start on {device['Host']}: {e}")
        return False


