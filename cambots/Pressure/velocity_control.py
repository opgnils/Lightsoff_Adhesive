#!/usr/bin/env python3
"""
Nanotec Motor Velocity Control - Interactive Listener
Listens on a TCP port for velocity commands and updates motor speed in real-time.
"""
import socket
import sys
import time
from nanotec_nanolib import Nanolib

# ----------------- Configuration -----------------
# Leave empty to auto-detect first available device
# Or set to specific description like "PD2-C4118L1804-E-01"
TARGET_DESC_CONTAINS = ""
TIMEOUT_MS = 4000
LISTEN_PORT = 5002  # Different port from adhesive (5001)

# ----------------- Helper Functions -----------------
def msleep(ms: int):
    time.sleep(ms / 1000.0)

def now_ms() -> int:
    return int(time.time() * 1000)

OD_CONTROLWORD = Nanolib.OdIndex(0x6040, 0x00)
OD_STATUSWORD  = Nanolib.OdIndex(0x6041, 0x00)
OD_MODE        = Nanolib.OdIndex(0x6060, 0x00)
OD_TARGET_VEL  = Nanolib.OdIndex(0x60FF, 0x00)
OD_ERROR_REG   = Nanolib.OdIndex(0x1001, 0x00)

def w(accessor: Nanolib.NanoLibAccessor, dev: Nanolib.DeviceHandle,
      od: Nanolib.OdIndex, value: int, bitlen: int):
    r = accessor.writeNumber(dev, value, od, bitlen)
    if r.hasError():
        raise RuntimeError(f"writeNumber({od.toString()}={value}) failed: {r.getError()}")

def rnum(accessor: Nanolib.NanoLibAccessor, dev: Nanolib.DeviceHandle,
         od: Nanolib.OdIndex) -> int:
    r = accessor.readNumber(dev, od)
    if r.hasError():
        raise RuntimeError(f"readNumber({od.toString()}) failed: {r.getError()}")
    return int(r.getResult())

def wait_status(accessor: Nanolib.NanoLibAccessor, dev: Nanolib.DeviceHandle,
                masked_expected: int, timeout_ms: int = TIMEOUT_MS) -> int:
    t0 = now_ms()
    while True:
        sw = rnum(accessor, dev, OD_STATUSWORD)
        if (sw & 0xEF) == masked_expected:
            return sw
        if now_ms() - t0 > timeout_ms:
            raise TimeoutError(
                f"Timeout waiting status {(sw & 0xEF):#x} != {masked_expected:#x} (sw={sw:#x})"
            )
        msleep(10)

def is_fault(sw: int) -> bool:
    return bool(sw & (1 << 3))

def fault_reset_if_needed(accessor, dev):
    sw = rnum(accessor, dev, OD_STATUSWORD)
    if is_fault(sw):
        print("[WARN] Drive is in FAULT. Sending fault reset.")
        w(accessor, dev, OD_CONTROLWORD, 0x0080, 16)
        msleep(100)

def choose_bus_hw(bus_list):
    """Choose the first available bus hardware."""
    if not bus_list:
        return None
    
    # Prefer USB/serial connections
    for b in bus_list:
        proto = (b.getProtocol() or "").upper()
        if "USB" in proto or "SERIAL" in proto or "VCP" in proto:
            return b
    
    # Otherwise return the first one
    return bus_list[0]

def initialize_motor():
    """Initialize motor and return accessor and device handle."""
    accessor = Nanolib.getNanoLibAccessor()
    
    bus_res = accessor.listAvailableBusHardware()
    if bus_res.hasError():
        raise RuntimeError(f"listAvailableBusHardware failed: {bus_res.getError()}")
    bus_list = bus_res.getResult()
    if not bus_list:
        raise RuntimeError("No bus hardware found.")
    
    print("---- Available bus hardware ----")
    for i, b in enumerate(bus_list):
        print(f"{i}: name='{b.getName()}', protocol='{b.getProtocol()}'")
    
    bus_hw_id = choose_bus_hw(bus_list)
    if not bus_hw_id:
        raise RuntimeError("No suitable bus hardware found")
    print(f"---- Using bus hardware ----\nname='{bus_hw_id.getName()}' protocol='{bus_hw_id.getProtocol()}'")
    
    open_res = accessor.openBusHardwareWithProtocol(bus_hw_id, Nanolib.BusHardwareOptions())
    if open_res.hasError():
        raise RuntimeError(f"openBusHardwareWithProtocol failed: {open_res.getError()}")
    
    scan_res = accessor.scanDevices(bus_hw_id, None)
    if scan_res.hasError():
        raise RuntimeError(f"scanDevices failed: {scan_res.getError()}")
    dev_ids = scan_res.getResult()
    if not dev_ids:
        raise RuntimeError("No devices found on bus.")
    
    dev_id = dev_ids[0]
    if TARGET_DESC_CONTAINS:
        for d in dev_ids:
            s = d.toString() if hasattr(d, "toString") else str(d)
            if TARGET_DESC_CONTAINS in s:
                dev_id = d
                break
    
    print("Found device:", dev_id.toString() if hasattr(dev_id, "toString") else dev_id)
    
    add_res = accessor.addDevice(dev_id)
    if add_res.hasError():
        raise RuntimeError(f"addDevice failed: {add_res.getError()}")
    dev_handle = add_res.getResult()
    
    con_res = accessor.connectDevice(dev_handle)
    if con_res.hasError():
        raise RuntimeError(f"connectDevice failed: {con_res.getError()}")
    
    # Check error register
    try:
        err = rnum(accessor, dev_handle, OD_ERROR_REG) & 0xFF
        if err != 0:
            print(f"[WARN] Error register 0x1001 = {err:#x}")
    except Exception:
        pass
    
    fault_reset_if_needed(accessor, dev_handle)
    
    # Mode of operation = 3 (Profile velocity)
    w(accessor, dev_handle, OD_MODE, 3, 8)
    
    # DS402 state machine sequence
    print("Initializing motor state machine...")
    w(accessor, dev_handle, OD_CONTROLWORD, 0x0006, 16)  # shutdown
    wait_status(accessor, dev_handle, 0x21)
    
    w(accessor, dev_handle, OD_CONTROLWORD, 0x0007, 16)  # switch on
    wait_status(accessor, dev_handle, 0x23)
    
    w(accessor, dev_handle, OD_CONTROLWORD, 0x000F, 16)  # enable operation
    wait_status(accessor, dev_handle, 0x27)
    
    # IMPORTANT: Set velocity to 0 to prevent motor from running
    # Motor will stay enabled but stationary until a velocity command is received
    w(accessor, dev_handle, OD_TARGET_VEL, 0, 32)
    print("Motor initialized at velocity 0 (stationary).")
    
    print("Motor ready for velocity commands.")
    
    return accessor, dev_handle, bus_hw_id

def set_velocity(accessor, dev_handle, velocity: int):
    """Set motor velocity."""
    w(accessor, dev_handle, OD_TARGET_VEL, int(velocity), 32)
    print(f"Velocity set to: {velocity} RPM")

def cleanup_motor(accessor, dev_handle, bus_hw_id):
    """Cleanup motor connection."""
    try:
        # Stop motor
        w(accessor, dev_handle, OD_TARGET_VEL, 0, 32)
        msleep(200)
        
        # Disable
        w(accessor, dev_handle, OD_CONTROLWORD, 0x0000, 16)
        
        # Disconnect
        accessor.disconnectDevice(dev_handle)
        accessor.removeDevice(dev_handle)
        accessor.closeBusHardware(bus_hw_id)
        print("Motor cleanup complete.")
    except Exception as e:
        print(f"Error during cleanup: {e}")

def start_listener():
    """Start TCP listener for velocity commands."""
    print(f"Starting Nanotec Velocity Control Listener on port {LISTEN_PORT}...")
    
    # Initialize motor
    try:
        accessor, dev_handle, bus_hw_id = initialize_motor()
    except Exception as e:
        print(f"Failed to initialize motor: {e}")
        sys.exit(1)
    
    # Create TCP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind(('0.0.0.0', LISTEN_PORT))
        server_socket.listen(5)
        server_socket.settimeout(1.0)  # Non-blocking accept with timeout
        
        print(f"Listening on port {LISTEN_PORT}...")
        print("Ready to receive velocity commands. Send 'STOP' to exit.")
        
        while True:
            try:
                client_socket, addr = server_socket.accept()
                client_socket.settimeout(5.0)
                
                try:
                    data = client_socket.recv(1024).decode('utf-8').strip()
                    
                    if not data:
                        continue
                    
                    print(f"Received from {addr}: {data}")
                    
                    # Check for stop command
                    if data.upper() == "STOP":
                        print("STOP command received. Shutting down...")
                        client_socket.sendall(b"OK:STOPPING\n")
                        client_socket.close()
                        break
                    
                    # Parse velocity value
                    try:
                        velocity = int(data)
                        set_velocity(accessor, dev_handle, velocity)
                        client_socket.sendall(f"OK:{velocity}\n".encode('utf-8'))
                    except ValueError:
                        error_msg = f"ERROR:Invalid velocity value: {data}"
                        print(error_msg)
                        client_socket.sendall(f"{error_msg}\n".encode('utf-8'))
                    
                except socket.timeout:
                    print(f"Client timeout from {addr}")
                except Exception as e:
                    print(f"Error handling client {addr}: {e}")
                finally:
                    client_socket.close()
                    
            except socket.timeout:
                # No connection, continue waiting
                continue
            except KeyboardInterrupt:
                print("\nKeyboard interrupt received. Shutting down...")
                break
            except Exception as e:
                print(f"Error accepting connection: {e}")
                
    finally:
        server_socket.close()
        cleanup_motor(accessor, dev_handle, bus_hw_id)
        print("Listener stopped.")

if __name__ == "__main__":
    start_listener()
