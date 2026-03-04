#!/usr/bin/env python3
"""
Torque Diagnostic Test
Run this while motor is under load to see raw torque values
"""
import sys
import time
from nanotec_nanolib import Nanolib

def main():
    print("=== Torque Diagnostic Test ===\n")
    
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
    OD_TARGET_TORQUE = Nanolib.OdIndex(0x6071, 0x00)  # Target torque (what we set)
    OD_MAX_TORQUE = Nanolib.OdIndex(0x6072, 0x00)     # Max torque limit
    OD_TORQUE_DEMAND = Nanolib.OdIndex(0x6074, 0x00)  # Torque demand value (internal)
    OD_TORQUE_ACTUAL = Nanolib.OdIndex(0x6077, 0x00)  # Torque actual value
    OD_CURRENT_ACTUAL = Nanolib.OdIndex(0x6078, 0x00) # Current actual value
    OD_TARGET_VEL = Nanolib.OdIndex(0x60FF, 0x00)     # Target velocity
    OD_VEL_DEMAND = Nanolib.OdIndex(0x6043, 0x00)     # Velocity demand
    
    def read_raw(od):
        """Read raw unsigned value"""
        r = accessor.readNumber(dev_handle, od)
        if r.hasError():
            return None, r.getError()
        return int(r.getResult()), None
    
    def read_signed_16(od):
        """Read as signed 16-bit"""
        r = accessor.readNumber(dev_handle, od)
        if r.hasError():
            return None, r.getError()
        value = int(r.getResult())
        # Mask to 16-bit and convert to signed
        value = value & 0xFFFF
        if value >= 0x8000:
            value = value - 0x10000
        return value, None
    
    def read_signed_32(od):
        """Read as signed 32-bit"""
        r = accessor.readNumber(dev_handle, od)
        if r.hasError():
            return None, r.getError()
        value = int(r.getResult())
        if value >= 0x80000000:
            value = value - 0x100000000
        return value, None
    
    print("Instructions:")
    print("1. Start motor at known velocity (e.g., 50 RPM)")
    print("2. Apply load by hand or clamp")
    print("3. Watch torque values change")
    print("4. Press Ctrl+C to stop\n")
    input("Press Enter to start monitoring...")
    print()
    
    try:
        while True:
            print("-" * 70)
            print("TORQUE OBJECTS:")
            
            # 0x6071 - Target torque (what's commanded)
            val, err = read_signed_16(OD_TARGET_TORQUE)
            if err:
                print(f"  0x6071 (Target Torque):   ERROR - {err}")
            else:
                torque_nm = (val / 1000.0) * 20.0
                torque_pct = val / 10.0
                print(f"  0x6071 (Target Torque):   {val} ‰ = {torque_nm:.2f} Nm = {torque_pct:.1f}%")
            
            # 0x6072 - Max torque limit
            val, err = read_signed_16(OD_MAX_TORQUE)
            if err:
                print(f"  0x6072 (Max Torque):      ERROR - {err}")
            else:
                print(f"  0x6072 (Max Torque):      {val} ‰ = {val/10.0:.1f}%")
            
            # 0x6074 - Torque demand (internal setpoint) *** THIS IS THE ONE WE WANT ***
            val, err = read_signed_16(OD_TORQUE_DEMAND)
            if err:
                print(f"  0x6074 (Torque Demand):   ERROR - {err}")
            else:
                torque_nm = (val / 1000.0) * 20.0
                torque_pct = val / 10.0
                print(f"  0x6074 (Torque Demand):   {val} ‰ = {torque_nm:.2f} Nm = {torque_pct:.1f}% *** USE THIS ***")
            
            # 0x6077 - Torque actual (may not be supported)
            val, err = read_signed_16(OD_TORQUE_ACTUAL)
            if err:
                print(f"  0x6077 (Torque Actual):   ERROR - {err}")
            else:
                torque_nm = (val / 1000.0) * 20.0
                torque_pct = val / 10.0
                print(f"  0x6077 (Torque Actual):   {val} ‰ = {torque_nm:.2f} Nm = {torque_pct:.1f}%")
            
            print("\nVELOCITY (for context):")
            
            # Target velocity
            val, err = read_signed_32(OD_TARGET_VEL)
            if err:
                print(f"  0x60FF (Target Vel):      ERROR")
            else:
                print(f"  0x60FF (Target Vel):      {val} RPM")
            
            # Velocity demand
            val, err = read_signed_32(OD_VEL_DEMAND)
            if err:
                print(f"  0x6043 (Velocity Demand): ERROR")
            else:
                print(f"  0x6043 (Velocity Demand): {val} RPM")
            
            print("\nOTHER:")
            
            # Try to read current (if available)
            val, err = read_signed_16(OD_CURRENT_ACTUAL)
            if err:
                print(f"  0x6078 (Current):         Not available")
            else:
                print(f"  0x6078 (Current):         {val}")
            
            print()
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\nStopped.")
    
    # Cleanup
    accessor.disconnectDevice(dev_handle)
    accessor.closeBusHardware(bus_hw_id)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
