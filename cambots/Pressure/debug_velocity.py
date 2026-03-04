#!/usr/bin/env python3
"""
Debug script to test velocity readback from Nanotec motor.
"""
import time
from nanotec_nanolib import Nanolib

def msleep(ms: int):
    time.sleep(ms / 1000.0)

def now_ms() -> int:
    return int(time.time() * 1000)

# Object dictionary indices
OD_CONTROLWORD = Nanolib.OdIndex(0x6040, 0x00)
OD_STATUSWORD  = Nanolib.OdIndex(0x6041, 0x00)
OD_MODE        = Nanolib.OdIndex(0x6060, 0x00)
OD_VEL_DEMAND  = Nanolib.OdIndex(0x6043, 0x00)
OD_TARGET_VEL  = Nanolib.OdIndex(0x60FF, 0x00)
OD_ACTUAL_VEL  = Nanolib.OdIndex(0x606C, 0x00)
OD_ACTUAL_POS  = Nanolib.OdIndex(0x6064, 0x00)
OD_ERROR_REG   = Nanolib.OdIndex(0x1001, 0x00)

def w(accessor, dev, od, value: int, bitlen: int):
    r = accessor.writeNumber(dev, value, od, bitlen)
    if r.hasError():
        raise RuntimeError(f"writeNumber({od.toString()}={value}) failed: {r.getError()}")

def rnum(accessor, dev, od, signed: bool = False, bitlen: int = 32) -> int:
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

def wait_status(accessor, dev, masked_expected: int, timeout_ms: int = 4000) -> int:
    t0 = now_ms()
    while True:
        sw = rnum(accessor, dev, OD_STATUSWORD)
        if (sw & 0xEF) == masked_expected:
            return sw
        if now_ms() - t0 > timeout_ms:
            raise TimeoutError(f"Timeout waiting status")
        msleep(10)

def choose_bus_hw(bus_list):
    if not bus_list:
        return None
    for b in bus_list:
        proto = (b.getProtocol() or "").upper()
        if "USB" in proto or "SERIAL" in proto or "VCP" in proto:
            return b
    return bus_list[0]

def main():
    print("=" * 60)
    print("Nanotec Motor Velocity Debug Test")
    print("=" * 60)
    
    # Initialize
    accessor = Nanolib.getNanoLibAccessor()
    
    bus_res = accessor.listAvailableBusHardware()
    if bus_res.hasError():
        print(f"ERROR: {bus_res.getError()}")
        return
    
    bus_list = bus_res.getResult()
    bus_hw_id = choose_bus_hw(bus_list)
    print(f"Using bus: {bus_hw_id.getName()}")
    
    open_res = accessor.openBusHardwareWithProtocol(bus_hw_id, Nanolib.BusHardwareOptions())
    if open_res.hasError():
        print(f"ERROR opening bus: {open_res.getError()}")
        return
    
    scan_res = accessor.scanDevices(bus_hw_id, None)
    if scan_res.hasError():
        print(f"ERROR scanning: {scan_res.getError()}")
        return
    
    dev_ids = scan_res.getResult()
    if not dev_ids:
        print("ERROR: No devices found")
        return
    
    dev_id = dev_ids[0]
    print(f"Found device: {dev_id.toString()}")
    
    add_res = accessor.addDevice(dev_id)
    if add_res.hasError():
        print(f"ERROR adding device: {add_res.getError()}")
        return
    
    dev_handle = add_res.getResult()
    
    con_res = accessor.connectDevice(dev_handle)
    if con_res.hasError():
        print(f"ERROR connecting: {con_res.getError()}")
        return
    
    print("Connected successfully!")
    print()
    
    try:
        # Set mode to profile velocity (3)
        print("Setting mode to Profile Velocity (3)...")
        w(accessor, dev_handle, OD_MODE, 3, 8)
        
        # Initialize motor
        print("Initializing motor state machine...")
        w(accessor, dev_handle, OD_CONTROLWORD, 0x0006, 16)
        wait_status(accessor, dev_handle, 0x21)
        print("  -> Ready to switch on")
        
        w(accessor, dev_handle, OD_CONTROLWORD, 0x0007, 16)
        wait_status(accessor, dev_handle, 0x23)
        print("  -> Switched on")
        
        w(accessor, dev_handle, OD_CONTROLWORD, 0x000F, 16)
        wait_status(accessor, dev_handle, 0x27)
        print("  -> Operation enabled")
        print()
        
        # Read initial values
        print("Reading initial values:")
        pos_start = rnum(accessor, dev_handle, OD_ACTUAL_POS)
        print(f"  Position: {pos_start}")
        print()
        
        # Test different velocities
        test_velocities = [100, 200, -100, -200, 0]
        
        for vel in test_velocities:
            print(f"Testing velocity: {vel} RPM")
            print("-" * 40)
            
            # Set velocity
            w(accessor, dev_handle, OD_TARGET_VEL, vel, 32)
            print(f"  Set target velocity: {vel}")
            
            # Wait for motor to stabilize
            time.sleep(2)
            
            # Read back multiple times
            for i in range(5):
                try:
                    target = rnum(accessor, dev_handle, OD_TARGET_VEL, signed=True)
                    print(f"  [{i+1}] Target velocity (0x60FF): {target} RPM")
                except Exception as e:
                    print(f"  [{i+1}] Error reading target: {e}")
                
                try:
                    demand = rnum(accessor, dev_handle, OD_VEL_DEMAND, signed=True)
                    print(f"  [{i+1}] Velocity demand (0x6043): {demand} RPM")
                except Exception as e:
                    print(f"  [{i+1}] Error reading demand: {e}")
                
                try:
                    actual = rnum(accessor, dev_handle, OD_ACTUAL_VEL, signed=True)
                    print(f"  [{i+1}] Actual velocity (0x606C): {actual} RPM")
                except Exception as e:
                    print(f"  [{i+1}] Error reading actual: {e}")
                
                try:
                    pos = rnum(accessor, dev_handle, OD_ACTUAL_POS)
                    print(f"  [{i+1}] Position: {pos} (delta: {pos - pos_start})")
                    pos_start = pos
                except Exception as e:
                    print(f"  [{i+1}] Error reading position: {e}")
                
                print()
                time.sleep(0.5)
            
            print()
        
        # Stop motor
        print("Stopping motor...")
        w(accessor, dev_handle, OD_TARGET_VEL, 0, 32)
        time.sleep(1)
        
        print("Test complete!")
        
    finally:
        # Cleanup
        try:
            w(accessor, dev_handle, OD_TARGET_VEL, 0, 32)
            w(accessor, dev_handle, OD_CONTROLWORD, 0x0000, 16)
            accessor.disconnectDevice(dev_handle)
            accessor.removeDevice(dev_handle)
            accessor.closeBusHardware(bus_hw_id)
        except:
            pass

if __name__ == "__main__":
    main()
