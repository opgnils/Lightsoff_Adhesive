#!/usr/bin/env python3
"""
PressureListener.py

TCP listener for Nanotec motor control on remote Jetsons.
Listens on port 5002 for velocity commands and controls the Nanotec motor
via USB using the nanolib library.

Commands:
  - "CONNECT" - Connect and enable the motor
  - "VELOCITY:<value>" - Set target velocity (e.g., "VELOCITY:500")
  - "STOP" - Stop the motor (set velocity to 0)
  - "DISCONNECT" - Disable and disconnect the motor
  - "STATUS" - Get current motor status (velocity, position, connected state)

Example usage:
    python3 PressureListener.py

The listener will automatically detect the Nanotec motor on /dev/ttyACM* ports.
"""

import socket
import sys
import time
import threading
import glob
import os

HOST = "0.0.0.0"  # Listen on all interfaces
PORT = 5002        # TCP port for pressure motor commands (different from adhesive port 5001)

# Try to import nanolib
try:
    from nanotec_nanolib import Nanolib
    NANOLIB_AVAILABLE = True
except ImportError:
    NANOLIB_AVAILABLE = False
    print("[PressureListener] WARNING: nanotec_nanolib not available!")
    print("[PressureListener] Install with: pip install nanolib")
    print("[PressureListener] Listener will run but motor control will fail.")


class NanotecMotorController:
    """Nanotec motor controller using nanolib."""
    
    # CiA-402 Object Dictionary indices
    OD_CONTROLWORD = 0x6040
    OD_STATUSWORD = 0x6041
    OD_MODE = 0x6060
    OD_TARGET_VEL = 0x60FF
    OD_VEL_ACT = 0x606C
    OD_POS_ACT = 0x6064
    
    def __init__(self, com_port: str = "/dev/ttyACM0"):
        """Initialize the motor controller.
        
        Args:
            com_port: COM port or device path (e.g., "/dev/ttyACM0")
        """
        self.com_port = com_port
        self.accessor = None
        self.device_handle = None
        self.connected = False
        
    def connect(self) -> tuple[bool, str]:
        """Connect to the motor.
        
        Returns:
            (success: bool, error_message: str)
        """
        if not NANOLIB_AVAILABLE:
            return False, "nanolib library not available"
        
        try:
            # Get accessor
            self.accessor = Nanolib.getNanoLibAccessor()
            
            # Scan for bus hardware
            bus_hw_ids_result = self.accessor.listAvailableBusHardware()
            
            # Convert result to list (it might be a special object)
            try:
                bus_hw_ids = list(bus_hw_ids_result)
            except TypeError:
                # If it's not iterable, try to access it differently
                bus_hw_ids = [bus_hw_ids_result.getBusHardware(i) for i in range(bus_hw_ids_result.size())]
            
            if not bus_hw_ids:
                return False, "No bus hardware found"
            
            print(f"[PressureListener] Found bus hardware: {bus_hw_ids}")
            
            # Choose appropriate bus hardware for the COM port
            bus_hw_id = self._choose_bus_hw(bus_hw_ids)
            if bus_hw_id is None:
                return False, f"No suitable bus hardware for {self.com_port}"
            
            print(f"[PressureListener] Using bus hardware: {bus_hw_id}")
            
            # Open bus hardware
            self.accessor.openBusHardwareWithProtocol(bus_hw_id)
            
            # Scan for devices
            device_ids_result = self.accessor.scanDevices()
            
            # Convert result to list
            try:
                device_ids = list(device_ids_result)
            except TypeError:
                # If it's not iterable, try to access it differently
                device_ids = [device_ids_result.getDevice(i) for i in range(device_ids_result.size())]
            
            if not device_ids:
                return False, "No devices found on bus"
            
            print(f"[PressureListener] Found devices: {device_ids}")
            
            # Connect to first device
            self.device_handle = self.accessor.addDevice(device_ids[0])
            
            # Set operation mode to Profile Velocity (mode 3)
            self.accessor.writeNumber(self.device_handle, self.OD_MODE, 0, 3, 8)
            
            self.connected = True
            print(f"[PressureListener] Connected to motor on {self.com_port}")
            return True, ""
            
        except Exception as e:
            error_msg = f"Connection failed: {e}"
            print(f"[PressureListener] {error_msg}")
            self.connected = False
            return False, error_msg
    
    def _choose_bus_hw(self, bus_hw_ids: list) -> str | None:
        """Choose the appropriate bus hardware ID for the COM port."""
        # Look for VCP (Virtual COM Port) or USB protocol
        for hw_id in bus_hw_ids:
            hw_id_lower = hw_id.lower()
            # Check if this hardware matches our COM port
            if "vcp" in hw_id_lower or "usb" in hw_id_lower:
                # Try to extract port info from hardware ID
                if self.com_port.lower() in hw_id_lower:
                    return hw_id
        
        # Fallback: return first available with VCP protocol
        for hw_id in bus_hw_ids:
            if "vcp" in hw_id.lower():
                return hw_id
        
        # Last resort: return first device
        return bus_hw_ids[0] if bus_hw_ids else None
    
    def enable_motor(self) -> tuple[bool, str]:
        """Enable the motor using DS402 state machine.
        
        Returns:
            (success: bool, error_message: str)
        """
        if not self.connected:
            return False, "Not connected"
        
        try:
            # DS402 enable sequence:
            # 1. Shutdown (controlword = 0x06)
            self.accessor.writeNumber(self.device_handle, self.OD_CONTROLWORD, 0, 0x06, 16)
            time.sleep(0.1)
            
            # 2. Switch on (controlword = 0x07)
            self.accessor.writeNumber(self.device_handle, self.OD_CONTROLWORD, 0, 0x07, 16)
            time.sleep(0.1)
            
            # 3. Enable operation (controlword = 0x0F)
            self.accessor.writeNumber(self.device_handle, self.OD_CONTROLWORD, 0, 0x0F, 16)
            time.sleep(0.1)
            
            print("[PressureListener] Motor enabled")
            return True, ""
            
        except Exception as e:
            error_msg = f"Enable failed: {e}"
            print(f"[PressureListener] {error_msg}")
            return False, error_msg
    
    def set_velocity(self, velocity: int) -> tuple[bool, str]:
        """Set target velocity.
        
        Args:
            velocity: Target velocity in motor units (signed int32)
        
        Returns:
            (success: bool, error_message: str)
        """
        if not self.connected:
            return False, "Not connected"
        
        try:
            # Write target velocity (32-bit signed integer)
            self.accessor.writeNumber(self.device_handle, self.OD_TARGET_VEL, 0, velocity, 32)
            print(f"[PressureListener] Set velocity to {velocity}")
            return True, ""
            
        except Exception as e:
            error_msg = f"Set velocity failed: {e}"
            print(f"[PressureListener] {error_msg}")
            return False, error_msg
    
    def get_actual_velocity(self) -> tuple[bool, int, str]:
        """Get actual velocity from motor.
        
        Returns:
            (success: bool, velocity: int, error_message: str)
        """
        if not self.connected:
            return False, 0, "Not connected"
        
        try:
            velocity = self.accessor.readNumber(self.device_handle, self.OD_VEL_ACT, 0)
            # Convert to signed int32
            velocity = self._to_int32(velocity)
            return True, velocity, ""
            
        except Exception as e:
            error_msg = f"Read velocity failed: {e}"
            return False, 0, error_msg
    
    def get_actual_position(self) -> tuple[bool, int, str]:
        """Get actual position from motor.
        
        Returns:
            (success: bool, position: int, error_message: str)
        """
        if not self.connected:
            return False, 0, "Not connected"
        
        try:
            position = self.accessor.readNumber(self.device_handle, self.OD_POS_ACT, 0)
            # Convert to signed int32
            position = self._to_int32(position)
            return True, position, ""
            
        except Exception as e:
            error_msg = f"Read position failed: {e}"
            return False, 0, error_msg
    
    def _to_int32(self, value: int) -> int:
        """Convert unsigned to signed int32."""
        if value >= 2**31:
            return value - 2**32
        return value
    
    def stop(self) -> tuple[bool, str]:
        """Stop the motor (set velocity to 0).
        
        Returns:
            (success: bool, error_message: str)
        """
        return self.set_velocity(0)
    
    def disable_motor(self) -> tuple[bool, str]:
        """Disable the motor using DS402 state machine.
        
        Returns:
            (success: bool, error_message: str)
        """
        if not self.connected:
            return False, "Not connected"
        
        try:
            # Stop motor first
            self.stop()
            time.sleep(0.1)
            
            # Disable operation (controlword = 0x00)
            self.accessor.writeNumber(self.device_handle, self.OD_CONTROLWORD, 0, 0x00, 16)
            print("[PressureListener] Motor disabled")
            return True, ""
            
        except Exception as e:
            error_msg = f"Disable failed: {e}"
            print(f"[PressureListener] {error_msg}")
            return False, error_msg
    
    def disconnect(self) -> tuple[bool, str]:
        """Disconnect from the motor.
        
        Returns:
            (success: bool, error_message: str)
        """
        try:
            if self.accessor is not None:
                self.accessor.disconnectBusHardware()
            self.connected = False
            print("[PressureListener] Disconnected from motor")
            return True, ""
            
        except Exception as e:
            error_msg = f"Disconnect failed: {e}"
            print(f"[PressureListener] {error_msg}")
            return False, error_msg


def detect_nanotec_port():
    """Detect Nanotec motor on /dev/ttyACM* ports.
    
    Returns:
        str: Device path (e.g., "/dev/ttyACM0") or None
    """
    acm_devices = sorted(glob.glob("/dev/ttyACM*"))
    print(f"[PressureListener] Detected ACM devices: {acm_devices}")
    
    if not acm_devices:
        print("[PressureListener] WARNING: No ACM devices found!")
        return None
    
    # Try to identify Nanotec device by USB vendor/product info
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
            
            print(f"[PressureListener] {device} USB info: '{device_info.strip()}'")
            
            # Look for Nanotec identifiers
            if "nanotec" in device_info or "nano" in device_info:
                print(f"[PressureListener] Identified {device} as Nanotec motor")
                return device
                
        except Exception as e:
            print(f"[PressureListener] Could not read USB info for {device}: {e}")
    
    # Fallback: use first available ACM device
    if acm_devices:
        print(f"[PressureListener] Using first ACM device: {acm_devices[0]}")
        return acm_devices[0]
    
    return None


def main():
    """Main listener loop."""
    print(f"[PressureListener] Starting on {HOST}:{PORT}")
    print(f"[PressureListener] nanolib available: {NANOLIB_AVAILABLE}")
    
    # Detect Nanotec motor port
    motor_port = detect_nanotec_port()
    if motor_port is None:
        print("[PressureListener] ERROR: Could not detect Nanotec motor port!")
        print("[PressureListener] Listener will run but CONNECT command will fail.")
        motor_port = "/dev/ttyACM0"  # Default fallback
    
    # Create motor controller
    motor = NanotecMotorController(motor_port)
    
    # Create TCP server socket
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_sock.bind((HOST, PORT))
        server_sock.listen(5)
        print(f"[PressureListener] Listening on {HOST}:{PORT}")
        
        while True:
            print("[PressureListener] Waiting for connection...")
            client_sock, client_addr = server_sock.accept()
            print(f"[PressureListener] Client connected from {client_addr}")
            
            try:
                buffer = ""
                while True:
                    data = client_sock.recv(1024)
                    if not data:
                        break
                    
                    buffer += data.decode("utf-8", errors="ignore")
                    
                    # Process complete commands (newline-delimited)
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        cmd = line.strip().upper()
                        
                        if not cmd:
                            continue
                        
                        print(f"[PressureListener] Received command: {cmd}")
                        
                        # Process command
                        response = ""
                        
                        if cmd == "CONNECT":
                            success, error = motor.connect()
                            if success:
                                success, error = motor.enable_motor()
                                if success:
                                    response = "OK:CONNECTED"
                                    print("[PressureListener] Motor connected and enabled")
                                else:
                                    response = f"ERROR:{error}"
                            else:
                                response = f"ERROR:{error}"
                        
                        elif cmd.startswith("VELOCITY:"):
                            try:
                                velocity_str = cmd.split(":", 1)[1]
                                velocity = int(velocity_str)
                                success, error = motor.set_velocity(velocity)
                                if success:
                                    response = f"OK:VELOCITY_SET:{velocity}"
                                else:
                                    response = f"ERROR:{error}"
                            except (ValueError, IndexError) as e:
                                response = f"ERROR:Invalid velocity format: {e}"
                        
                        elif cmd == "STOP":
                            success, error = motor.stop()
                            if success:
                                response = "OK:STOPPED"
                            else:
                                response = f"ERROR:{error}"
                        
                        elif cmd == "DISCONNECT":
                            success, error = motor.disable_motor()
                            if success:
                                motor.disconnect()
                                response = "OK:DISCONNECTED"
                            else:
                                response = f"ERROR:{error}"
                        
                        elif cmd == "STATUS":
                            if motor.connected:
                                vel_ok, vel, vel_err = motor.get_actual_velocity()
                                pos_ok, pos, pos_err = motor.get_actual_position()
                                
                                if vel_ok and pos_ok:
                                    response = f"OK:STATUS:connected=true,velocity={vel},position={pos}"
                                else:
                                    errors = []
                                    if not vel_ok:
                                        errors.append(f"vel_error={vel_err}")
                                    if not pos_ok:
                                        errors.append(f"pos_error={pos_err}")
                                    response = f"ERROR:{','.join(errors)}"
                            else:
                                response = "OK:STATUS:connected=false"
                        
                        else:
                            response = f"ERROR:Unknown command: {cmd}"
                        
                        # Send response
                        if response:
                            client_sock.sendall(f"{response}\n".encode("utf-8"))
                            print(f"[PressureListener] Sent response: {response}")
            
            except Exception as e:
                print(f"[PressureListener] Client handler error: {e}")
            
            finally:
                print(f"[PressureListener] Client {client_addr} disconnected")
                client_sock.close()
    
    except KeyboardInterrupt:
        print("\n[PressureListener] Shutting down...")
    
    finally:
        if motor.connected:
            motor.disable_motor()
            motor.disconnect()
        server_sock.close()
        print("[PressureListener] Listener stopped")


if __name__ == "__main__":
    main()
