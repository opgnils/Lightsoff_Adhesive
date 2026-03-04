#!/usr/bin/env python3
"""
Simple torque reading test - checks if torque objects can be read at all.
"""

import sys
import time
from nanotec_nanolib import Nanolib

# OD Indices
OD_TORQUE_DEMAND = Nanolib.OdIndex(0x6074, 0x00)
OD_TORQUE_ACTUAL = Nanolib.OdIndex(0x6077, 0x00)
OD_CURRENT_ACTUAL = Nanolib.OdIndex(0x6078, 0x00)
OD_TARGET_TORQUE = Nanolib.OdIndex(0x6071, 0x00)
OD_TARGET_VELOCITY = Nanolib.OdIndex(0x60FF, 0x00)
OD_VEL_DEMAND = Nanolib.OdIndex(0x6043, 0x00)

def rnum(accessor, dev, od, signed=False, bitlen=32):
    """Read a number from CANopen object."""
    r = accessor.readNumber(dev, od)
    if r.hasError():
        raise RuntimeError(f"readNumber({od.toString()}) failed: {r.getError()}")
    value = int(r.getResult())
    
    # Convert unsigned to signed if requested
    if signed:
        if bitlen == 16 and value >= 0x8000:
            value = value - 0x10000
        elif bitlen == 32 and value >= 0x80000000:
            value = value - 0x100000000
    
    return value

def main():
    accessor = Nanolib.getNanoLibAccessor()
    
    # Scan for bus hardware
    result = accessor.listAvailableBusHardware()
    if result.hasError():
        print(f"Error listing bus hardware: {result.getError()}")
        return 1
    
    bus_hw_ids = result.getResult()
    if not bus_hw_ids:
        print("No bus hardware found")
        return 1
    
    # Use first available
    bus_hw_id = bus_hw_ids[0]
    print(f"Using bus hardware: {bus_hw_id.getName()}")
    
    # Open bus hardware
    bus_hw_options = Nanolib.BusHardwareOptions()
    result = accessor.openBusHardwareWithProtocol(bus_hw_id, bus_hw_options)
    if result.hasError():
        print(f"Error opening bus hardware: {result.getError()}")
        return 1
    
    # Scan for devices
    print("Scanning for devices...")
    result = accessor.scanDevices(bus_hw_id, "")
    if result.hasError():
        print(f"Error scanning devices: {result.getError()}")
        return 1
    
    device_ids = result.getResult()
    if not device_ids:
        print("No devices found")
        return 1
    
    # Connect to first device
    device_id = device_ids[0]
    print(f"Connecting to device: {device_id.getDescription()}")
    
    result = accessor.addDevice(device_id)
    if result.hasError():
        print(f"Error adding device: {result.getError()}")
        return 1
    
    dev_handle = result.getResult()
    
    result = accessor.connectDevice(dev_handle)
    if result.hasError():
        print(f"Error connecting device: {result.getError()}")
        return 1
    
    print("\nReading torque values every second (Ctrl+C to stop)...")
    print("Format: [timestamp] Velocity | Current 0x6078 | Torque 0x6074 | Torque 0x6077 | Torque 0x6071")
    print("-" * 100)
    
    try:
        while True:
            timestamp = time.strftime("%H:%M:%S")
            
            # Read velocity for context
            try:
                vel = rnum(accessor, dev_handle, OD_VEL_DEMAND, signed=True, bitlen=32)
            except Exception as e:
                vel = f"ERROR"
            
            # Try 0x6078 (Current actual) - most reliable indicator of load
            try:
                current_6078 = rnum(accessor, dev_handle, OD_CURRENT_ACTUAL, signed=True, bitlen=16)
                current_str = f"{current_6078:5d} ‰ ({current_6078/10.0:5.1f}%)"
            except Exception as e:
                current_str = f"ERROR: {str(e)[:20]}"
            
            # Try 0x6074 (Torque demand)
            try:
                torque_6074 = rnum(accessor, dev_handle, OD_TORQUE_DEMAND, signed=True, bitlen=16)
                torque_6074_str = f"{torque_6074:5d} ‰ ({torque_6074/10.0:5.1f}%)"
            except Exception as e:
                torque_6074_str = f"ERROR: {str(e)[:20]}"
            
            # Try 0x6077 (Torque actual)
            try:
                torque_6077 = rnum(accessor, dev_handle, OD_TORQUE_ACTUAL, signed=True, bitlen=16)
                torque_6077_str = f"{torque_6077:5d} ‰ ({torque_6077/10.0:5.1f}%)"
            except Exception as e:
                torque_6077_str = f"ERROR: {str(e)[:20]}"
            
            # Try 0x6071 (Target torque)
            try:
                torque_6071 = rnum(accessor, dev_handle, OD_TARGET_TORQUE, signed=True, bitlen=16)
                torque_6071_str = f"{torque_6071:5d} ‰ ({torque_6071/10.0:5.1f}%)"
            except Exception as e:
                torque_6071_str = f"ERROR: {str(e)[:20]}"
            
            print(f"[{timestamp}] Vel: {vel:4} RPM | 0x6078: {current_str:25s} | 0x6074: {torque_6074_str:25s} | 0x6077: {torque_6077_str:25s} | 0x6071: {torque_6071_str:25s}")
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\nStopping...")
    
    # Cleanup
    accessor.disconnectDevice(dev_handle)
    accessor.closeBusHardware(bus_hw_id)
    print("Done.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
