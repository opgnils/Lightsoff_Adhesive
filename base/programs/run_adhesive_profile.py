#!/usr/bin/env python3
"""
Helper script to run adhesive profiles from the command line.

Usage:
    python3 run_adhesive_profile.py <profile_name.csv>
    
Example:
    python3 run_adhesive_profile.py adhesive_profiles/fast_rampUp.csv
"""

import sys
import os
import csv
import time
import socket
import select
import termios
import tty

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from base.Devices import get_devices, check_online_devices, ensure_adhesive_listener_running


def send_adhesive_command_tcp(device, cmd: str, port: int = 5001, timeout: float = 2.0):
    """Send a single adhesive command to the unified listener over TCP.

    Args:
        device (dict): Device info with HostName.
        cmd (str): Command string like "0,200,0".
        port (int): TCP port where UnifiedListener is running.
        timeout (float): Socket timeout in seconds.
        
    Returns:
        bool: True if successful, False otherwise.
    """
    host = device["HostName"]
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(cmd.encode("utf-8"))
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send to {device['Host']} ({host}:{port}): {e}")
        return False


def load_profile(profile_path: str):
    """Load adhesive profile from CSV file.
    
    CSV format: time, motor1, motor2, motor3
    
    Args:
        profile_path: Path to CSV file
        
    Returns:
        list: List of (time, [m1, m2, m3]) tuples
    """
    steps = []
    try:
        with open(profile_path, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                # Skip empty lines
                if not row:
                    continue
                # Strip spaces and ignore comments
                parts = [p.strip() for p in row if p.strip() and not p.strip().startswith("#")]
                if len(parts) < 2:
                    continue
                t = float(parts[0])
                # Fill missing motors with 0 if needed
                m1 = float(parts[1]) if len(parts) > 1 else 0.0
                m2 = float(parts[2]) if len(parts) > 2 else 0.0
                m3 = float(parts[3]) if len(parts) > 3 else 0.0
                steps.append((t, [m1, m2, m3]))
    except Exception as e:
        print(f"[ERROR] Failed to load profile: {e}")
        return []
    
    if not steps:
        print("[ERROR] Profile is empty")
        return []
    
    # Sort by time
    steps.sort(key=lambda x: x[0])
    return steps


def send_stop_all(devices):
    """Send STOP ALL (0,0,0) multiple times for robustness."""
    cmd = "0,0,0"
    repeats = 3
    last_success = True
    for i in range(repeats):
        all_success = True
        for d in devices:
            ok = send_adhesive_command_tcp(d, cmd)
            if not ok:
                all_success = False
        if not all_success:
            last_success = False
            print(f"[WARN] STOP attempt {i+1}/{repeats} failed on at least one device")
        time.sleep(0.1)
    print("\n✓ Sent STOP (0,0,0)" if last_success else "\n[WARN] STOP may not have reached all devices")


def run_profile(profile_path: str, devices: list):
    """Execute adhesive profile on selected devices.
    
    Args:
        profile_path: Path to CSV profile
        devices: List of device dicts
    """
    print(f"\n{'='*60}")
    print(f"Running adhesive profile: {os.path.basename(profile_path)}")
    print(f"Devices: {', '.join([d['Host'] for d in devices])}")
    print(f"{'='*60}")
    
    # Ensure listeners are running
    print("\n[1/3] Ensuring unified listeners are running...")
    for d in devices:
        try:
            ensure_adhesive_listener_running(d)
            print(f"  ✓ Listener ready on {d['Host']}")
        except Exception as e:
            print(f"  ✗ Failed to start listener on {d['Host']}: {e}")
            return
    
    # Load profile
    print(f"\n[2/3] Loading profile from {profile_path}...")
    steps = load_profile(profile_path)
    if not steps:
        return
    print(f"  ✓ Loaded {len(steps)} steps")
    
    # Execute profile
    print(f"\n[3/3] Executing profile...")
    print("  Press 'q' or ESC to EMERGENCY STOP (sends 0,0,0 and aborts)")
    print()
    
    start_time = time.time()
    
    # Set stdin to non-blocking raw mode
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    
    try:
        for i, (t_target, motors) in enumerate(steps):
            now = time.time()
            wait = t_target - (now - start_time)
            # Wait in small chunks to poll for emergency key presses
            end_wait = time.time() + max(wait, 0)
            while time.time() < end_wait:
                # Poll stdin for key presses without blocking
                rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                if rlist:
                    ch = sys.stdin.read(1)
                    if ch in ("q", "Q", "\x1b"):
                        print("\n[EMERGENCY] Stop requested during profile...")
                        send_stop_all(devices)
                        time.sleep(1)
                        return
            
            cmd = f"{motors[0]},{motors[1]},{motors[2]}"
            all_success = True
            for d in devices:
                ok = send_adhesive_command_tcp(d, cmd)
                if not ok:
                    all_success = False
            
            status = "✓" if all_success else "✗"
            print(f"  [{i+1:3d}/{len(steps):3d}] t={t_target:6.2f}s -> {cmd:20s} {status}")
        
        print(f"\n{'='*60}")
        print("Profile complete. Sending final STOP (0,0,0)...")
        send_stop_all(devices)
        print(f"{'='*60}\n")
        
    except KeyboardInterrupt:
        print("\n[EMERGENCY] Keyboard interrupt. Sending STOP (0,0,0)...")
        send_stop_all(devices)
        time.sleep(1)
    finally:
        # Restore terminal settings
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 run_adhesive_profile.py <profile.csv>")
        print("\nExample:")
        print("  python3 run_adhesive_profile.py adhesive_profiles/fast_rampUp.csv")
        sys.exit(1)
    
    profile_path = sys.argv[1]
    
    if not os.path.exists(profile_path):
        print(f"[ERROR] Profile not found: {profile_path}")
        sys.exit(1)
    
    # Discover and select devices
    print("Discovering devices...")
    devices = get_devices()
    online_devices = check_online_devices(devices)
    
    if not online_devices:
        print("[ERROR] No devices online!")
        sys.exit(1)
    
    print(f"\nOnline devices ({len(online_devices)}):")
    for i, d in enumerate(online_devices):
        print(f"  [{i+1}] {d['Host']} ({d['HostName']})")
    
    # For simplicity, use all online devices
    # In a real scenario, you might want to prompt the user to select
    selected = online_devices
    
    # Run profile
    run_profile(profile_path, selected)


if __name__ == "__main__":
    main()
