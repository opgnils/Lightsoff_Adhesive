#!/usr/bin/env python3
"""
Quick test to see what values different velocity objects return
Run this while motor is moving at 200 RPM
"""
import sys
import time
from nanotec_nanolib import Nanolib

def main():
    print("=== Velocity Objects Test ===")
    print("Make sure motor is running at 200 RPM before starting!\n")
    input("Press Enter when motor is moving...")
    
    # Setup
    accessor = Nanolib.getNanoLibAccessor()
    accessor.setup()
    
    # Scan for device
    result = accessor.listAvailableBusHardware()
    if result.hasError():
        print(f"Error: {result.getError()}")
        return 1
    
    bus_hw_ids = result.getResult()
    if not bus_hw_ids:
        print("No bus hardware found")
        return 1
    
    # Open first available
    bus_hw_id = bus_hw_ids[0]
    bus_hw_options = Nanolib.BusHardwareOptions()
    bus_hw_options.addOption("can-baudrate", "1000000")
    
    result = accessor.openBusHardwareWithProtocol(bus_hw_id, bus_hw_options)
    if result.hasError():
        print(f"Error opening bus: {result.getError()}")
        return 1
    
    # Scan devices
    result = accessor.scanDevices(bus_hw_id, None)
    if result.hasError():
        print(f"Error scanning: {result.getError()}")
        return 1
    
    device_ids = result.getResult()
    if not device_ids:
        print("No devices found")
        return 1
    
    # Connect to first device
    result = accessor.addDevice(device_ids[0])
    if result.hasError():
        print(f"Error adding device: {result.getError()}")
        return 1
    
    dev_handle = result.getResult()
    
    result = accessor.connectDevice(dev_handle)
    if result.hasError():
        print(f"Error connecting: {result.getError()}")
        return 1
    
    print("Connected!\n")
    
    # Define objects
    OD_TARGET_VEL  = Nanolib.OdIndex(0x60FF, 0x00)
    OD_VEL_DEMAND  = Nanolib.OdIndex(0x6043, 0x00)
    OD_ACTUAL_VEL  = Nanolib.OdIndex(0x606C, 0x00)
    OD_ACTUAL_POS  = Nanolib.OdIndex(0x6064, 0x00)
    
    def read_signed(od):
        """Read as signed 32-bit"""
        r = accessor.readNumber(dev_handle, od)
        if r.hasError():
            return None, r.getError()
        value = int(r.getResult())
        if value >= 0x80000000:
            value = value - 0x100000000
        return value, None
    
    # Read 5 times with 0.5s delay
    print("Reading velocity objects 5 times:\n")
    last_pos = None
    
    for i in range(5):
        print(f"--- Sample {i+1} ---")
        
        # Target velocity (what you commanded)
        val, err = read_signed(OD_TARGET_VEL)
        if err:
            print(f"  0x60FF (Target):  ERROR - {err}")
        else:
            print(f"  0x60FF (Target):  {val} RPM")
        
        # Velocity demand (internal setpoint)
        val, err = read_signed(OD_VEL_DEMAND)
        if err:
            print(f"  0x6043 (Demand):  ERROR - {err}")
        else:
            print(f"  0x6043 (Demand):  {val} RPM")
        
        # Actual velocity (encoder feedback)
        val, err = read_signed(OD_ACTUAL_VEL)
        if err:
            print(f"  0x606C (Actual):  ERROR - {err}")
        else:
            print(f"  0x606C (Actual):  {val} RPM")
        
        # Position (to calculate velocity manually)
        val, err = read_signed(OD_ACTUAL_POS)
        if err:
            print(f"  0x6064 (Position): ERROR - {err}")
        else:
            print(f"  0x6064 (Position): {val} counts")
            if last_pos is not None:
                delta = val - last_pos
                # 1024 counts/rev, 0.5 sec interval
                rpm = (delta / 1024.0) * (60.0 / 0.5)
                print(f"    -> Calculated velocity: {rpm:.1f} RPM")
            last_pos = val
        
        print()
        time.sleep(0.5)
    
    print("\n=== Analysis ===")
    print("Which object showed 200 RPM (or close to it)?")
    print("  - If 0x60FF shows 200: Target is set correctly")
    print("  - If 0x6043 shows 200: Motor is trying to reach 200 RPM")
    print("  - If 0x606C shows 200: Encoder feedback is working")
    print("  - If calculated shows 200: Motor is actually moving at 200 RPM")
    print("\nIf only 0x6043 works, we'll use that for feedback!")
    
    # Cleanup
    accessor.disconnectDevice(dev_handle)
    accessor.closeBusHardware(bus_hw_id)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
