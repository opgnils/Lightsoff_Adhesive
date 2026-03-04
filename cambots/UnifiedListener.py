#!/usr/bin/env python3
"""
UnifiedListener.py

Combined TCP listener for both adhesive motors and pressure motor on remote Jetsons.

Listens on TWO ports:
  - Port 5001: Adhesive motor commands (M1,M2,M3 format)
  - Port 5002: Pressure motor commands (CONNECT/VELOCITY/STOP/etc.)

This unified approach is cleaner than running separate listeners since all
motors are connected to the same Jetson.

Example usage:
    python3 UnifiedListener.py
"""

import socket
import sys
import time
import serial
import struct
import threading
import glob
import os
import select

# ═══════════════════════════════════════════════════════════════════════════
# ADHESIVE MOTOR CONFIGURATION (Port 5001)
# ═══════════════════════════════════════════════════════════════════════════

ADHESIVE_HOST = "0.0.0.0"
ADHESIVE_PORT = 5001

ARDUINO_BAUDRATE = 9600
VESC_BAUDRATE = 115200
POLE_PAIRS = 7
MAX_MECH_RPM = 6000

# Shared state for VESC keep-alive
_current_rpm = 0
_vesc_thread_stop = False

# ═══════════════════════════════════════════════════════════════════════════
# PRESSURE MOTOR CONFIGURATION (Port 5002)
# ═══════════════════════════════════════════════════════════════════════════

PRESSURE_HOST = "0.0.0.0"
PRESSURE_PORT = 5002

# Try to import nanolib
try:
    from nanotec_nanolib import Nanolib
    NANOLIB_AVAILABLE = True
except ImportError:
    NANOLIB_AVAILABLE = False
    print("[UnifiedListener] WARNING: nanotec_nanolib not available for pressure motor!")


# ═══════════════════════════════════════════════════════════════════════════
# DEVICE DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def detect_serial_ports():
    """Detect which /dev/ttyACM* is Arduino, VESC, and Nanotec motor.
    
    Returns:
        (arduino_port, vesc_port, nanotec_port)
    """
    acm_devices = sorted(glob.glob("/dev/ttyACM*"))
    print(f"[UnifiedListener] Detected ACM devices: {acm_devices}")

    if len(acm_devices) == 0:
        print("[UnifiedListener] Warning: No ACM devices found!")
        return None, None, None

    arduino_port = None
    vesc_port = None
    nanotec_port = None

    # Try to identify devices by USB vendor/product info
    for device in acm_devices:
        try:
            dev_num = device.replace("/dev/ttyACM", "")
            
            usb_info_paths = [
                f"/sys/class/tty/ttyACM{dev_num}/device/interface",
                f"/sys/class/tty/ttyACM{dev_num}/device/../interface",
                f"/sys/class/tty/ttyACM{dev_num}/device/product",
                f"/sys/class/tty/ttyACM{dev_num}/device/manufacturer",
            ]
            
            device_info = ""
            for path in usb_info_paths:
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        device_info += f.read().strip().lower() + " "
            
            print(f"[UnifiedListener] {device} USB info: '{device_info.strip()}'")
            
            # Identify Nanotec motor
            if "nanotec" in device_info or "nano" in device_info:
                nanotec_port = device
                print(f"[UnifiedListener] Identified {device} as Nanotec motor")
            # Identify VESC
            elif "vesc" in device_info or "stm" in device_info or "vedder" in device_info:
                vesc_port = device
                print(f"[UnifiedListener] Identified {device} as VESC")
            # Identify Arduino
            elif "arduino" in device_info or "usb serial" in device_info:
                arduino_port = device
                print(f"[UnifiedListener] Identified {device} as Arduino")
                
        except Exception as e:
            print(f"[UnifiedListener] Could not read USB info for {device}: {e}")

    # Assign remaining unidentified devices
    unassigned = [d for d in acm_devices if d not in [arduino_port, vesc_port, nanotec_port]]
    
    # Fallback logic for unidentified devices
    if arduino_port is None and len(unassigned) > 0:
        arduino_port = unassigned.pop(0)
        print(f"[UnifiedListener] Assigned {arduino_port} to Arduino (fallback)")
    
    if vesc_port is None and len(unassigned) > 0:
        vesc_port = unassigned.pop(0)
        print(f"[UnifiedListener] Assigned {vesc_port} to VESC (fallback)")

    print(f"[UnifiedListener] Final assignment -> Arduino: {arduino_port}, VESC: {vesc_port}, Nanotec: {nanotec_port}")
    return arduino_port, vesc_port, nanotec_port


# ═══════════════════════════════════════════════════════════════════════════
# ADHESIVE MOTOR FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def open_arduino_serial(port):
    """Open the Arduino serial port."""
    if port is None:
        return None
    try:
        ser = serial.Serial(port, ARDUINO_BAUDRATE, timeout=1)
        time.sleep(2)
        print(f"[UnifiedListener] Opened Arduino serial {port} @ {ARDUINO_BAUDRATE}")
        return ser
    except Exception as e:
        print(f"[UnifiedListener] Failed to open Arduino serial port {port}: {e}")
        return None


def open_vesc_serial(port):
    """Open the VESC serial port."""
    if port is None:
        return None
    try:
        ser = serial.Serial(port, VESC_BAUDRATE, timeout=0.1)
        time.sleep(0.5)
        print(f"[UnifiedListener] Opened VESC serial {port} @ {VESC_BAUDRATE}")
        return ser
    except Exception as e:
        print(f"[UnifiedListener] Failed to open VESC serial port {port}: {e}")
        return None


def crc16_ccitt(data: bytes, poly: int = 0x1021, crc: int = 0x0000) -> int:
    """Compute CRC16-CCITT for VESC protocol."""
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def pack_vesc_frame(payload: bytes) -> bytes:
    """Pack a VESC UART short frame with CRC."""
    start = 0x02
    length = len(payload)
    crc = crc16_ccitt(payload)
    end = 0x03
    frame = bytes([start, length]) + payload + struct.pack(">H", crc) + bytes([end])
    return frame


def vesc_set_rpm(ser, rpm: int):
    """Send RPM command to VESC."""
    if ser is None or not ser.is_open:
        return
    COMM_SET_RPM = 8
    payload = bytes([COMM_SET_RPM]) + struct.pack(">i", int(rpm))
    frame = pack_vesc_frame(payload)
    try:
        ser.write(frame)
        ser.flush()
    except Exception as e:
        print(f"[UnifiedListener] Error writing to VESC: {e}")


def vesc_keepalive_loop(get_serial, interval: float = 0.2):
    """Background loop for VESC keep-alive."""
    global _current_rpm, _vesc_thread_stop
    while not _vesc_thread_stop:
        vesc_ser = get_serial()
        if vesc_ser is not None and vesc_ser.is_open:
            vesc_set_rpm(vesc_ser, _current_rpm)
        time.sleep(interval)


# ═══════════════════════════════════════════════════════════════════════════
# PRESSURE MOTOR (NANOTEC) CLASS
# ═══════════════════════════════════════════════════════════════════════════

class NanotecMotorController:
    """Nanotec motor controller using nanolib."""
    
    OD_CONTROLWORD = 0x6040
    OD_STATUSWORD = 0x6041
    OD_MODE = 0x6060
    OD_TARGET_VEL = 0x60FF
    OD_VEL_ACT = 0x606C
    OD_POS_ACT = 0x6064
    
    def __init__(self, com_port: str):
        self.com_port = com_port
        self.accessor = None
        self.device_handle = None
        self.connected = False
        
    def connect(self) -> tuple[bool, str]:
        if not NANOLIB_AVAILABLE:
            return False, "nanolib library not available"
        
        try:
            self.accessor = Nanolib.getNanoLibAccessor()
            
            bus_hw_ids_result = self.accessor.listAvailableBusHardware()
            
            # Try to get bus hardware IDs - API returns a special result object
            bus_hw_ids = []
            try:
                # Try direct iteration first
                bus_hw_ids = list(bus_hw_ids_result)
            except (TypeError, AttributeError):
                # If that fails, try using getBusHardware method
                try:
                    count = bus_hw_ids_result.size() if hasattr(bus_hw_ids_result, 'size') else len(bus_hw_ids_result)
                    bus_hw_ids = [bus_hw_ids_result.getBusHardware(i) for i in range(count)]
                except Exception as inner_e:
                    print(f"[UnifiedListener] Warning: Could not iterate bus hardware IDs: {inner_e}")
                    # Last resort: assume single device
                    if hasattr(bus_hw_ids_result, 'getBusHardware'):
                        try:
                            bus_hw_ids = [bus_hw_ids_result.getBusHardware(0)]
                        except:
                            pass
            
            if not bus_hw_ids:
                return False, "No bus hardware found"
            
            bus_hw_id = bus_hw_ids[0]  # Use first available
            self.accessor.openBusHardwareWithProtocol(bus_hw_id)
            
            device_ids_result = self.accessor.scanDevices()
            
            # Try to get device IDs - same issue with result object
            device_ids = []
            try:
                device_ids = list(device_ids_result)
            except (TypeError, AttributeError):
                try:
                    count = device_ids_result.size() if hasattr(device_ids_result, 'size') else len(device_ids_result)
                    device_ids = [device_ids_result.getDevice(i) for i in range(count)]
                except Exception as inner_e:
                    print(f"[UnifiedListener] Warning: Could not iterate device IDs: {inner_e}")
                    # Last resort: assume single device
                    if hasattr(device_ids_result, 'getDevice'):
                        try:
                            device_ids = [device_ids_result.getDevice(0)]
                        except:
                            pass
            
            if not device_ids:
                return False, "No devices found on bus"
            
            self.device_handle = self.accessor.addDevice(device_ids[0])
            self.accessor.writeNumber(self.device_handle, self.OD_MODE, 0, 3, 8)
            
            self.connected = True
            print(f"[UnifiedListener] Nanotec motor connected")
            return True, ""
            
        except Exception as e:
            self.connected = False
            error_msg = f"Nanotec connection error: {str(e)}"
            print(f"[UnifiedListener] {error_msg}")
            return False, error_msg
    
    def enable_motor(self) -> tuple[bool, str]:
        if not self.connected:
            return False, "Not connected"
        try:
            self.accessor.writeNumber(self.device_handle, self.OD_CONTROLWORD, 0, 0x06, 16)
            time.sleep(0.1)
            self.accessor.writeNumber(self.device_handle, self.OD_CONTROLWORD, 0, 0x07, 16)
            time.sleep(0.1)
            self.accessor.writeNumber(self.device_handle, self.OD_CONTROLWORD, 0, 0x0F, 16)
            time.sleep(0.1)
            return True, ""
        except Exception as e:
            return False, str(e)
    
    def set_velocity(self, velocity: int) -> tuple[bool, str]:
        if not self.connected:
            return False, "Not connected"
        try:
            self.accessor.writeNumber(self.device_handle, self.OD_TARGET_VEL, 0, velocity, 32)
            return True, ""
        except Exception as e:
            return False, str(e)
    
    def stop(self) -> tuple[bool, str]:
        return self.set_velocity(0)
    
    def disable_motor(self) -> tuple[bool, str]:
        if not self.connected:
            return False, "Not connected"
        try:
            self.stop()
            time.sleep(0.1)
            self.accessor.writeNumber(self.device_handle, self.OD_CONTROLWORD, 0, 0x00, 16)
            return True, ""
        except Exception as e:
            return False, str(e)
    
    def disconnect(self) -> tuple[bool, str]:
        try:
            if self.accessor is not None:
                self.accessor.disconnectBusHardware()
            self.connected = False
            return True, ""
        except Exception as e:
            return False, str(e)


# ═══════════════════════════════════════════════════════════════════════════
# ADHESIVE LISTENER HANDLER (Port 5001)
# ═══════════════════════════════════════════════════════════════════════════

def handle_adhesive_client(client_sock, client_addr, arduino_ser, vesc_ser, arduino_port, vesc_port):
    """Handle adhesive motor commands on port 5001."""
    global _current_rpm
    
    print(f"[UnifiedListener] Adhesive client connected from {client_addr}")
    
    try:
        buffer = ""
        while True:
            data = client_sock.recv(1024)
            if not data:
                break
            
            buffer += data.decode("utf-8", errors="ignore")
            
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                cmd = line.strip()
                
                if not cmd:
                    continue
                
                # Parse command: m1,m2,m3
                parts = cmd.split(",")
                if len(parts) != 3:
                    print(f"[UnifiedListener] Ignoring malformed adhesive command: {cmd}")
                    continue

                m1_str, m2_str, m3_str = parts

                # Motor 1 via VESC
                try:
                    mech_rpm = float(m1_str)
                except ValueError:
                    mech_rpm = 0.0

                if mech_rpm > MAX_MECH_RPM:
                    mech_rpm = float(MAX_MECH_RPM)
                elif mech_rpm < -MAX_MECH_RPM:
                    mech_rpm = float(-MAX_MECH_RPM)

                m1_erpm = int(mech_rpm * POLE_PAIRS)
                _current_rpm = m1_erpm

                # Motors 2 & 3 via Arduino
                arduino_line = cmd + "\n"
                try:
                    if arduino_ser is None or not arduino_ser.is_open:
                        if arduino_port is not None:
                            arduino_ser = open_arduino_serial(arduino_port)
                    
                    if arduino_ser is not None:
                        arduino_ser.write(arduino_line.encode("utf-8"))
                        arduino_ser.flush()
                except Exception as e:
                    print(f"[UnifiedListener] Error writing to Arduino: {e}")
    
    except Exception as e:
        print(f"[UnifiedListener] Adhesive client handler error: {e}")
    
    finally:
        print(f"[UnifiedListener] Adhesive client {client_addr} disconnected")
        client_sock.close()


# ═══════════════════════════════════════════════════════════════════════════
# PRESSURE LISTENER HANDLER (Port 5002)
# ═══════════════════════════════════════════════════════════════════════════

def handle_pressure_client(client_sock, client_addr, motor):
    """Handle pressure motor commands on port 5002."""
    print(f"[UnifiedListener] Pressure client connected from {client_addr}")
    
    try:
        buffer = ""
        while True:
            data = client_sock.recv(1024)
            if not data:
                break
            
            buffer += data.decode("utf-8", errors="ignore")
            
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                cmd = line.strip().upper()
                
                if not cmd:
                    continue
                
                response = ""
                
                if cmd == "CONNECT":
                    success, error = motor.connect()
                    if success:
                        success, error = motor.enable_motor()
                        response = "OK:CONNECTED" if success else f"ERROR:{error}"
                    else:
                        response = f"ERROR:{error}"
                
                elif cmd.startswith("VELOCITY:"):
                    try:
                        velocity = int(cmd.split(":", 1)[1])
                        success, error = motor.set_velocity(velocity)
                        response = f"OK:VELOCITY_SET:{velocity}" if success else f"ERROR:{error}"
                    except (ValueError, IndexError) as e:
                        response = f"ERROR:Invalid velocity: {e}"
                
                elif cmd == "STOP":
                    success, error = motor.stop()
                    response = "OK:STOPPED" if success else f"ERROR:{error}"
                
                elif cmd == "DISCONNECT":
                    success, error = motor.disable_motor()
                    if success:
                        motor.disconnect()
                        response = "OK:DISCONNECTED"
                    else:
                        response = f"ERROR:{error}"
                
                elif cmd == "STATUS":
                    response = f"OK:STATUS:connected={motor.connected}"
                
                else:
                    response = f"ERROR:Unknown command: {cmd}"
                
                if response:
                    client_sock.sendall(f"{response}\n".encode("utf-8"))
    
    except Exception as e:
        print(f"[UnifiedListener] Pressure client handler error: {e}")
    
    finally:
        print(f"[UnifiedListener] Pressure client {client_addr} disconnected")
        client_sock.close()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN UNIFIED LISTENER
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """Main unified listener loop."""
    global _vesc_thread_stop
    
    print("[UnifiedListener] Starting unified listener...")
    print(f"[UnifiedListener] Adhesive port: {ADHESIVE_PORT}")
    print(f"[UnifiedListener] Pressure port: {PRESSURE_PORT}")
    print(f"[UnifiedListener] nanolib available: {NANOLIB_AVAILABLE}")
    
    # Detect devices
    arduino_port, vesc_port, nanotec_port = detect_serial_ports()
    
    # Open adhesive motor serials
    arduino_ser = open_arduino_serial(arduino_port)
    vesc_ser = open_vesc_serial(vesc_port)
    
    # Create pressure motor controller
    motor = NanotecMotorController(nanotec_port if nanotec_port else "/dev/ttyACM1")
    
    # Start VESC keep-alive thread
    vesc_keepalive_thread = threading.Thread(
        target=vesc_keepalive_loop,
        args=(lambda: vesc_ser,),
        daemon=True
    )
    vesc_keepalive_thread.start()
    
    # Create server sockets
    adhesive_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    adhesive_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    adhesive_sock.bind((ADHESIVE_HOST, ADHESIVE_PORT))
    adhesive_sock.listen(5)
    
    pressure_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pressure_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    pressure_sock.bind((PRESSURE_HOST, PRESSURE_PORT))
    pressure_sock.listen(5)
    
    print(f"[UnifiedListener] Listening on ports {ADHESIVE_PORT} (adhesive) and {PRESSURE_PORT} (pressure)")
    
    try:
        while True:
            # Use select to wait for connections on either port
            readable, _, _ = select.select([adhesive_sock, pressure_sock], [], [])
            
            for sock in readable:
                client_sock, client_addr = sock.accept()
                
                if sock == adhesive_sock:
                    # Spawn thread for adhesive client
                    thread = threading.Thread(
                        target=handle_adhesive_client,
                        args=(client_sock, client_addr, arduino_ser, vesc_ser, arduino_port, vesc_port),
                        daemon=True
                    )
                    thread.start()
                
                elif sock == pressure_sock:
                    # Spawn thread for pressure client
                    thread = threading.Thread(
                        target=handle_pressure_client,
                        args=(client_sock, client_addr, motor),
                        daemon=True
                    )
                    thread.start()
    
    except KeyboardInterrupt:
        print("\n[UnifiedListener] Shutting down...")
    
    finally:
        _vesc_thread_stop = True
        
        if motor.connected:
            motor.disable_motor()
            motor.disconnect()
        
        if arduino_ser and arduino_ser.is_open:
            arduino_ser.close()
        if vesc_ser and vesc_ser.is_open:
            vesc_ser.close()
        
        adhesive_sock.close()
        pressure_sock.close()
        
        print("[UnifiedListener] Listener stopped")


if __name__ == "__main__":
    main()
