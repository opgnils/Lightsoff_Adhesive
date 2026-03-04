#!/usr/bin/env python3
"""
Simple script to find available Nanotec devices and test connection.
Run this first to verify your motor is connected and find the correct port.
"""
from nanotec_nanolib import Nanolib

def list_devices():
    """List all available bus hardware and devices."""
    accessor = Nanolib.getNanoLibAccessor()
    
    print("=" * 60)
    print("NANOTEC DEVICE SCANNER")
    print("=" * 60)
    
    # List available bus hardware
    print("\n1. Scanning for bus hardware...")
    bus_res = accessor.listAvailableBusHardware()
    if bus_res.hasError():
        print(f"ERROR: Failed to list bus hardware: {bus_res.getError()}")
        return
    
    bus_list = bus_res.getResult()
    if not bus_list:
        print("ERROR: No bus hardware found!")
        print("\nPossible issues:")
        print("  - Motor not connected via USB")
        print("  - USB cable faulty")
        print("  - Driver not installed")
        print("  - Permissions issue (try: sudo usermod -a -G dialout $USER)")
        return
    
    print(f"Found {len(bus_list)} bus hardware device(s):\n")
    for i, b in enumerate(bus_list):
        name = b.getName() or "Unknown"
        protocol = b.getProtocol() or "Unknown"
        print(f"  [{i}] Name: {name}")
        print(f"      Protocol: {protocol}")
        print()
    
    # Try to open and scan each bus
    print("2. Scanning for motor devices...")
    for i, bus_hw_id in enumerate(bus_list):
        print(f"\n  Scanning bus [{i}]: {bus_hw_id.getName()}...")
        
        try:
            open_res = accessor.openBusHardwareWithProtocol(bus_hw_id, Nanolib.BusHardwareOptions())
            if open_res.hasError():
                print(f"    ERROR: Could not open bus: {open_res.getError()}")
                continue
            
            scan_res = accessor.scanDevices(bus_hw_id, None)
            if scan_res.hasError():
                print(f"    ERROR: Scan failed: {scan_res.getError()}")
                accessor.closeBusHardware(bus_hw_id)
                continue
            
            dev_ids = scan_res.getResult()
            if not dev_ids:
                print(f"    No devices found on this bus")
                accessor.closeBusHardware(bus_hw_id)
                continue
            
            print(f"    Found {len(dev_ids)} device(s):")
            for j, dev_id in enumerate(dev_ids):
                dev_str = dev_id.toString() if hasattr(dev_id, "toString") else str(dev_id)
                print(f"      [{j}] {dev_str}")
            
            accessor.closeBusHardware(bus_hw_id)
            
        except Exception as e:
            print(f"    ERROR: {e}")
    
    print("\n" + "=" * 60)
    print("SCAN COMPLETE")
    print("=" * 60)
    print("\nIf you found your motor above, update velocity_control.py with:")
    print("  - The correct bus hardware name/protocol")
    print("  - Or remove TARGET_DESC_CONTAINS filter to use any device")
    print()

if __name__ == "__main__":
    list_devices()
