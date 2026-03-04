"""
Nanotec Motor Control Module
Provides velocity-based control for Nanotec motors via Nanolib
"""

import time
import socket
from typing import Optional, Tuple

try:
    from nanotec_nanolib import Nanolib
    NANOLIB_AVAILABLE = True
except ImportError:
    NANOLIB_AVAILABLE = False
    print("[WARNING] nanotec_nanolib not available. Nanotec motor control will be disabled.")


class NanotecMotorController:
    """Controller for Nanotec motors using Profile Velocity mode."""
    
    # Object Dictionary indices (CiA-402 standard)
    OD_CONTROLWORD = Nanolib.OdIndex(0x6040, 0x00) if NANOLIB_AVAILABLE else None
    OD_STATUSWORD = Nanolib.OdIndex(0x6041, 0x00) if NANOLIB_AVAILABLE else None
    OD_MODE = Nanolib.OdIndex(0x6060, 0x00) if NANOLIB_AVAILABLE else None
    OD_TARGET_VEL = Nanolib.OdIndex(0x60FF, 0x00) if NANOLIB_AVAILABLE else None
    OD_VEL_ACT = Nanolib.OdIndex(0x606C, 0x00) if NANOLIB_AVAILABLE else None
    OD_POS_ACT = Nanolib.OdIndex(0x6064, 0x00) if NANOLIB_AVAILABLE else None
    
    def __init__(self, com_port: str = "COM7"):
        """Initialize the Nanotec motor controller.
        
        Args:
            com_port: COM port or device path (e.g., "COM7" or "/dev/ttyACM0")
        """
        if not NANOLIB_AVAILABLE:
            raise RuntimeError("nanotec_nanolib library is not available")
        
        self.com_port = com_port
        self.accessor = None
        self.bus_hw_id = None
        self.device_handle = None
        self.is_connected = False
        
    def connect(self) -> Tuple[bool, str]:
        """Connect to the Nanotec motor.
        
        Returns:
            (success, error_message)
        """
        try:
            # Get Nanolib accessor
            self.accessor = Nanolib.getNanoLibAccessor()
            
            # List available bus hardware
            bus_result = self.accessor.listAvailableBusHardware()
            if bus_result.hasError():
                return False, f"Failed to list bus hardware: {bus_result.getError()}"
            
            bus_list = bus_result.getResult()
            if not bus_list:
                return False, "No bus hardware found"
            
            # Find matching bus hardware
            self.bus_hw_id = self._choose_bus_hw(bus_list, self.com_port)
            if not self.bus_hw_id:
                return False, f"Could not find bus hardware for {self.com_port}"
            
            # Open bus hardware
            open_result = self.accessor.openBusHardwareWithProtocol(
                self.bus_hw_id, 
                Nanolib.BusHardwareOptions()
            )
            if open_result.hasError():
                return False, f"Failed to open bus: {open_result.getError()}"
            
            # Scan for devices
            scan_result = self.accessor.scanDevices(self.bus_hw_id, None)
            if scan_result.hasError():
                return False, f"Device scan failed: {scan_result.getError()}"
            
            device_ids = scan_result.getResult()
            if not device_ids:
                return False, "No devices found on bus"
            
            # Add and connect to first device
            dev_result = self.accessor.addDevice(device_ids[0])
            if dev_result.hasError():
                return False, f"Failed to add device: {dev_result.getError()}"
            
            self.device_handle = dev_result.getResult()
            
            connect_result = self.accessor.connectDevice(self.device_handle)
            if connect_result.hasError():
                return False, f"Failed to connect device: {connect_result.getError()}"
            
            self.is_connected = True
            return True, ""
            
        except Exception as e:
            return False, f"Connection exception: {str(e)}"
    
    def _choose_bus_hw(self, bus_list, com_port: str):
        """Choose the correct bus hardware from the list."""
        com_port_upper = com_port.upper()
        
        # First try: match name and "VCP" protocol
        for bus in bus_list:
            name = (bus.getName() or "").upper()
            protocol = (bus.getProtocol() or "").upper()
            if com_port_upper in name and "VCP" in protocol:
                return bus
        
        # Second try: just match name
        for bus in bus_list:
            name = (bus.getName() or "").upper()
            if com_port_upper in name:
                return bus
        
        # Fallback: return first available
        return bus_list[0] if bus_list else None
    
    def enable_motor(self) -> Tuple[bool, str]:
        """Enable the motor using DS402 state machine.
        
        Returns:
            (success, error_message)
        """
        if not self.is_connected:
            return False, "Not connected"
        
        try:
            # Set Profile Velocity mode (mode 3)
            self._write(self.OD_MODE, 3, 8)
            
            # DS402 enable sequence
            # Shutdown -> Switch on disabled
            self._write(self.OD_CONTROLWORD, 0x0006, 16)
            self._wait_status(0x21)
            
            # Ready to switch on
            self._write(self.OD_CONTROLWORD, 0x0007, 16)
            self._wait_status(0x23)
            
            # Switched on -> Operation enabled
            self._write(self.OD_CONTROLWORD, 0x000F, 16)
            self._wait_status(0x27)
            
            return True, ""
            
        except Exception as e:
            return False, f"Enable failed: {str(e)}"
    
    def set_velocity(self, velocity: int) -> Tuple[bool, str]:
        """Set target velocity.
        
        Args:
            velocity: Target velocity in motor units (can be negative for reverse)
        
        Returns:
            (success, error_message)
        """
        if not self.is_connected:
            return False, "Not connected"
        
        try:
            self._write(self.OD_TARGET_VEL, int(velocity), 32)
            return True, ""
        except Exception as e:
            return False, f"Set velocity failed: {str(e)}"
    
    def get_actual_velocity(self) -> Tuple[Optional[int], str]:
        """Read actual velocity.
        
        Returns:
            (velocity, error_message) - velocity is None on error
        """
        if not self.is_connected:
            return None, "Not connected"
        
        try:
            vel = self._read(self.OD_VEL_ACT)
            return self._to_int32(vel), ""
        except Exception as e:
            return None, f"Read velocity failed: {str(e)}"
    
    def get_actual_position(self) -> Tuple[Optional[int], str]:
        """Read actual position.
        
        Returns:
            (position, error_message) - position is None on error
        """
        if not self.is_connected:
            return None, "Not connected"
        
        try:
            pos = self._read(self.OD_POS_ACT)
            return self._to_int32(pos), ""
        except Exception as e:
            return None, f"Read position failed: {str(e)}"
    
    def stop(self) -> Tuple[bool, str]:
        """Stop the motor (set velocity to 0).
        
        Returns:
            (success, error_message)
        """
        return self.set_velocity(0)
    
    def disable_motor(self) -> Tuple[bool, str]:
        """Disable the motor.
        
        Returns:
            (success, error_message)
        """
        if not self.is_connected:
            return False, "Not connected"
        
        try:
            # Stop first
            self.stop()
            time.sleep(0.2)
            
            # Disable
            self._write(self.OD_CONTROLWORD, 0x0000, 16)
            return True, ""
        except Exception as e:
            return False, f"Disable failed: {str(e)}"
    
    def disconnect(self):
        """Disconnect from the motor and close bus hardware."""
        try:
            if self.is_connected:
                self.disable_motor()
            
            if self.device_handle and self.accessor:
                self.accessor.disconnectDevice(self.device_handle)
            
            if self.bus_hw_id and self.accessor:
                self.accessor.closeBusHardware(self.bus_hw_id)
            
            self.is_connected = False
            
        except Exception as e:
            print(f"[WARNING] Disconnect error: {e}")
    
    def _write(self, od_index, value: int, bitlen: int):
        """Write to object dictionary."""
        result = self.accessor.writeNumber(self.device_handle, value, od_index, bitlen)
        if result.hasError():
            raise RuntimeError(f"Write {od_index.toString()} failed: {result.getError()}")
    
    def _read(self, od_index) -> int:
        """Read from object dictionary."""
        result = self.accessor.readNumber(self.device_handle, od_index)
        if result.hasError():
            raise RuntimeError(f"Read {od_index.toString()} failed: {result.getError()}")
        return int(result.getResult())
    
    def _wait_status(self, masked_expected: int, timeout_ms: int = 4000):
        """Wait for specific status word value."""
        start = int(time.time() * 1000)
        while True:
            sw = self._read(self.OD_STATUSWORD)
            if (sw & 0xEF) == masked_expected:
                return sw
            if int(time.time() * 1000) - start > timeout_ms:
                raise TimeoutError(f"Timeout waiting for status {hex(masked_expected)}")
            time.sleep(0.01)
    
    @staticmethod
    def _to_int32(x: int) -> int:
        """Convert unsigned to signed int32."""
        x &= 0xFFFFFFFF
        return x - 0x100000000 if x & 0x80000000 else x


# Convenience function for checking if Nanolib is available
def is_nanolib_available() -> bool:
    """Check if Nanolib is available on this system."""
    return NANOLIB_AVAILABLE
