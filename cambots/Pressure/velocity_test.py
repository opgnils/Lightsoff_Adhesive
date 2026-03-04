import time
from nanotec_nanolib import Nanolib

# ----------------- user settings -----------------
# Leave empty to auto-detect first available device
# Or set to specific description like "PD2-C4118L1804-E-01"
TARGET_DESC_CONTAINS = ""

VEL_POS = 300
VEL_NEG = -300
RUN_MS = 2000

TIMEOUT_MS = 4000

# ----------------- helpers -----------------
def msleep(ms: int):
    time.sleep(ms / 1000.0)

def now_ms() -> int:
    return int(time.time() * 1000)

OD_CONTROLWORD = Nanolib.OdIndex(0x6040, 0x00)
OD_STATUSWORD  = Nanolib.OdIndex(0x6041, 0x00)
OD_MODE        = Nanolib.OdIndex(0x6060, 0x00)
OD_TARGET_VEL  = Nanolib.OdIndex(0x60FF, 0x00)
OD_ERROR_REG   = Nanolib.OdIndex(0x1001, 0x00)  # Error register (uint8)

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
    # DS402: Statusword bit 3 = Fault
    return bool(sw & (1 << 3))

def fault_reset_if_needed(accessor, dev):
    sw = rnum(accessor, dev, OD_STATUSWORD)
    if is_fault(sw):
        print("[WARN] Drive is in FAULT. Sending fault reset.")
        # Controlword bit 7 = Fault reset
        w(accessor, dev, OD_CONTROLWORD, 0x0080, 16)
        msleep(100)
        # After reset, many drives go to "Switch on disabled"
        # No strict wait here; we proceed with standard sequence.

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

def velocity_test():
    accessor: Nanolib.NanoLibAccessor = Nanolib.getNanoLibAccessor()

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

    dev_handle = None
    try:
        scan_res = accessor.scanDevices(bus_hw_id, None)
        if scan_res.hasError():
            raise RuntimeError(f"scanDevices failed: {scan_res.getError()}")
        dev_ids = scan_res.getResult()
        if not dev_ids:
            raise RuntimeError("No devices found on bus.")

        # Optional: select by description
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

        # Check error register (optional but useful)
        try:
            err = rnum(accessor, dev_handle, OD_ERROR_REG) & 0xFF
            if err != 0:
                print(f"[WARN] Error register 0x1001 = {err:#x}")
        except Exception:
            pass

        fault_reset_if_needed(accessor, dev_handle)

        # Mode of operation = 3 (Profile velocity)
        w(accessor, dev_handle, OD_MODE, 3, 8)

        # DS402 sequence
        w(accessor, dev_handle, OD_CONTROLWORD, 0x0006, 16)  # shutdown
        wait_status(accessor, dev_handle, 0x21)

        w(accessor, dev_handle, OD_CONTROLWORD, 0x0007, 16)  # switch on
        wait_status(accessor, dev_handle, 0x23)

        w(accessor, dev_handle, OD_CONTROLWORD, 0x000F, 16)  # enable operation
        wait_status(accessor, dev_handle, 0x27)

        # Run
        w(accessor, dev_handle, OD_TARGET_VEL, int(VEL_POS), 32)
        msleep(RUN_MS)

        w(accessor, dev_handle, OD_TARGET_VEL, int(VEL_NEG), 32)
        msleep(RUN_MS)

        # Smooth stop
        w(accessor, dev_handle, OD_TARGET_VEL, 0, 32)
        msleep(200)

        # Disable
        w(accessor, dev_handle, OD_CONTROLWORD, 0x0000, 16)

        print("Done.")

    finally:
        if dev_handle is not None:
            try:
                accessor.disconnectDevice(dev_handle)
            except Exception:
                pass
            try:
                accessor.removeDevice(dev_handle)
            except Exception:
                pass
        try:
            accessor.closeBusHardware(bus_hw_id)
        except Exception:
            pass

if __name__ == "__main__":
    velocity_test()
