import socket
import sys
import time
import serial
import struct
import threading

HOST = "0.0.0.0"  # listen on all interfaces
PORT = 5001        # TCP port for adhesive commands

# We expect two ACM devices when both Arduino and VESC are connected.
ARDUINO_BAUDRATE = 9600
VESC_BAUDRATE = 115200

# Motor / VESC configuration
# 14-pole outrunner => 7 pole pairs => eRPM = mechanical_RPM * 7
POLE_PAIRS = 7
# User inputs mechanical RPM; internally we clamp to this mechanical limit
MAX_MECH_RPM = 6000

# Shared state for VESC keep-alive
_current_rpm = 0
_vesc_thread_stop = False


def detect_serial_ports():
    """Detect which /dev/ttyACM* is Arduino vs VESC.

    Strategy:
    1. Find all /dev/ttyACM* devices
    2. Try to identify each device by checking its USB attributes or by attempting
       to communicate at expected baudrates
    3. VESC typically has higher baudrate (115200) and responds to VESC protocol
    4. Arduino uses 9600 baud
    
    If we can't distinguish them reliably, we'll try both baudrates on each port.
    """
    import glob
    import os

    acm_devices = sorted(glob.glob("/dev/ttyACM*"))
    print(f"[AdhesiveListener] Detected ACM devices: {acm_devices}")

    if len(acm_devices) == 0:
        print("[AdhesiveListener] Warning: No ACM devices found!")
        return None, None

    arduino_port = None
    vesc_port = None

    # Try to identify devices by USB vendor/product info
    for device in acm_devices:
        try:
            # Extract device number (e.g., "0" from "/dev/ttyACM0")
            dev_num = device.replace("/dev/ttyACM", "")
            
            # Check USB device info via sysfs
            # Typical paths: /sys/class/tty/ttyACMx/device/...
            usb_info_paths = [
                f"/sys/class/tty/ttyACM{dev_num}/device/interface",
                f"/sys/class/tty/ttyACM{dev_num}/device/../interface",
                f"/sys/class/tty/ttyACM{dev_num}/device/product",
            ]
            
            device_info = ""
            for path in usb_info_paths:
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        device_info = f.read().strip().lower()
                        break
            
            print(f"[AdhesiveListener] {device} USB info: '{device_info}'")
            
            # VESC often shows up as "STMicroelectronics Virtual COM Port" or similar
            # Arduino often shows up as "Arduino" or "USB Serial"
            if "vesc" in device_info or "stm" in device_info or "vedder" in device_info:
                vesc_port = device
                print(f"[AdhesiveListener] Identified {device} as VESC based on USB info")
            elif "arduino" in device_info or "usb serial" in device_info:
                arduino_port = device
                print(f"[AdhesiveListener] Identified {device} as Arduino based on USB info")
                
        except Exception as e:
            print(f"[AdhesiveListener] Could not read USB info for {device}: {e}")

    # Fallback heuristic: if we have exactly 2 devices and haven't identified both,
    # assign them based on position
    if len(acm_devices) == 2 and (arduino_port is None or vesc_port is None):
        if arduino_port is None and vesc_port is None:
            # Try the traditional assignment but with ALL available ACM ports
            vesc_port = acm_devices[0]
            arduino_port = acm_devices[1]
            print(f"[AdhesiveListener] Fallback: Assigned {vesc_port} to VESC, {arduino_port} to Arduino")
        elif vesc_port is None:
            # Arduino identified, assign the other to VESC
            vesc_port = [d for d in acm_devices if d != arduino_port][0]
            print(f"[AdhesiveListener] Assigned remaining device {vesc_port} to VESC")
        elif arduino_port is None:
            # VESC identified, assign the other to Arduino
            arduino_port = [d for d in acm_devices if d != vesc_port][0]
            print(f"[AdhesiveListener] Assigned remaining device {arduino_port} to Arduino")
    
    # If only one device, be conservative and assume it's the Arduino
    elif len(acm_devices) == 1 and arduino_port is None and vesc_port is None:
        arduino_port = acm_devices[0]
        print(f"[AdhesiveListener] Only one device found, assuming Arduino: {arduino_port}")
    
    # If we have more than 2 devices, try to identify or warn
    elif len(acm_devices) > 2:
        if arduino_port is None or vesc_port is None:
            print(f"[AdhesiveListener] WARNING: Found {len(acm_devices)} ACM devices but could not confidently identify all!")
            print(f"[AdhesiveListener] Arduino: {arduino_port}, VESC: {vesc_port}")
            print(f"[AdhesiveListener] You may need to manually specify ports or improve detection logic")

    print(f"[AdhesiveListener] Final assignment -> Arduino: {arduino_port}, VESC: {vesc_port}")
    return arduino_port, vesc_port


def open_arduino_serial(port):
    """Open the Arduino serial port with a short reset delay. Returns a serial object or None."""
    if port is None:
        print("[AdhesiveListener] No Arduino serial port configured.")
        return None
    try:
        ser = serial.Serial(port, ARDUINO_BAUDRATE, timeout=1)
        time.sleep(2)  # reset delay so Arduino is ready
        print(f"[AdhesiveListener] Opened Arduino serial {port} @ {ARDUINO_BAUDRATE}")
        return ser
    except Exception as e:
        print(f"[AdhesiveListener] Failed to open Arduino serial port {port}: {e}")
        return None


def open_vesc_serial(port):
    """Open the VESC serial port. Returns a serial object or None."""
    if port is None:
        print("[AdhesiveListener] No VESC serial port configured.")
        return None
    try:
        ser = serial.Serial(port, VESC_BAUDRATE, timeout=0.1)
        time.sleep(0.5)
        print(f"[AdhesiveListener] Opened VESC serial {port} @ {VESC_BAUDRATE}")
        return ser
    except Exception as e:
        print(f"[AdhesiveListener] Failed to open VESC serial port {port}: {e}")
        return None


def crc16_ccitt(data: bytes, poly: int = 0x1021, crc: int = 0x0000) -> int:
    """Compute CRC16-CCITT over data (as used by VESC)."""
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
    """Send a COMM_SET_RPM command to the VESC over the given serial connection."""
    if ser is None or not ser.is_open:
        return
    COMM_SET_RPM = 8
    payload = bytes([COMM_SET_RPM]) + struct.pack(">i", int(rpm))
    frame = pack_vesc_frame(payload)
    try:
        ser.write(frame)
        ser.flush()
        print(f"[AdhesiveListener] Sent to VESC: RPM={rpm}")
    except Exception as e:
        print(f"[AdhesiveListener] Error writing to VESC serial: {e}")
        try:
            ser.close()
        except Exception:
            pass
        # Caller will attempt to reopen on next use.


def vesc_keepalive_loop(get_serial, get_port, interval: float = 0.2):
    """Background loop that periodically sends the last commanded RPM to the VESC.

    get_serial: callable returning the current vesc_ser object
    get_port: callable returning the current vesc_port string
    interval: delay between keep-alive frames
    """
    global _current_rpm, _vesc_thread_stop
    while not _vesc_thread_stop:
        vesc_ser = get_serial()
        vesc_port = get_port()

        if vesc_ser is None or not vesc_ser.is_open:
            if vesc_port is not None:
                print("[AdhesiveListener] VESC keepalive: serial not open, attempting reopen...")
                vesc_ser_new = open_vesc_serial(vesc_port)
                # update reference in caller by rebinding through get_serial side-effect
                if vesc_ser_new is not None:
                    # We can't assign into the outer scope here, so rely on the
                    # main thread to refresh vesc_ser on next command. For now
                    # just use the local handle to send the frame once.
                    vesc_set_rpm(vesc_ser_new, _current_rpm)
                    try:
                        vesc_ser_new.close()
                    except Exception:
                        pass
        else:
            vesc_set_rpm(vesc_ser, _current_rpm)

        time.sleep(interval)


def main():
    # Detect ports for Arduino (motors 2 & 3) and VESC (motor 1)
    arduino_port, vesc_port = detect_serial_ports()

    arduino_ser = open_arduino_serial(arduino_port)
    # Don't hard-fail if Arduino is missing; we still want to be able to send
    # Motor 1 (VESC) commands if available.

    vesc_ser = open_vesc_serial(vesc_port)

    # Start VESC keep-alive thread so that the last commanded RPM is held
    # until changed or set to zero.
    def _get_vesc_ser():
        return vesc_ser

    def _get_vesc_port():
        return vesc_port

    global _vesc_thread_stop
    _vesc_thread_stop = False
    vesc_thread = threading.Thread(
        target=vesc_keepalive_loop,
        args=(_get_vesc_ser, _get_vesc_port),
        daemon=True,
    )
    vesc_thread.start()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            # SO_REUSEPORT might not be available on all systems
            pass
        
        try:
            s.bind((HOST, PORT))
        except OSError as e:
            if e.errno == 98:  # Address already in use
                print(f"[AdhesiveListener] ERROR: Port {PORT} is already in use!")
                print(f"[AdhesiveListener] Kill the existing process with: pkill -9 -f AdhesiveListener")
                print(f"[AdhesiveListener] Or check what's using the port: lsof -i :{PORT}")
                sys.exit(1)
            else:
                raise
        
        s.listen(5)
        print(f"[AdhesiveListener] Listening for commands on {HOST}:{PORT}")

        try:
            while True:
                conn, addr = s.accept()
                with conn:
                    print(f"[AdhesiveListener] Connection from {addr}")
                    # Read once per connection; commands are small
                    try:
                        data = conn.recv(1024)
                    except Exception as e:
                        print(f"[AdhesiveListener] Error receiving TCP data: {e}")
                        continue

                    if not data:
                        continue

                    try:
                        text = data.decode("utf-8", errors="ignore")
                    except Exception as e:
                        print(f"[AdhesiveListener] Decode error: {e}")
                        continue

                    cmd = text.strip()
                    if not cmd:
                        continue

                    # Expect a triple like "m1,m2,m3" where
                    #   m1 = Motor 1 RPM (VESC)
                    #   m2 = Motor 2 value (Arduino)
                    #   m3 = Motor 3 value (Arduino)
                    parts = cmd.split(",")
                    if len(parts) != 3:
                        print(f"[AdhesiveListener] Ignoring malformed command: {cmd}")
                        continue

                    m1_str, m2_str, m3_str = parts

                    # --- Handle Motor 1 via VESC ---
                    try:
                        mech_rpm = float(m1_str)
                    except ValueError:
                        mech_rpm = 0.0

                    # Clamp mechanical RPM to a safe range.
                    if mech_rpm > MAX_MECH_RPM:
                        mech_rpm = float(MAX_MECH_RPM)
                    elif mech_rpm < -MAX_MECH_RPM:
                        mech_rpm = float(-MAX_MECH_RPM)

                    # Convert mechanical RPM to electrical RPM (eRPM) for VESC.
                    m1_erpm = int(mech_rpm * POLE_PAIRS)

                    # Update shared target RPM (in eRPM); background thread will keep sending it.
                    global _current_rpm
                    _current_rpm = m1_erpm

                    # --- Handle Motors 2 & 3 via Arduino ---
                    # We keep the existing protocol: send the whole line to Arduino.
                    line = cmd + "\n"

                    try:
                        if arduino_ser is None or not arduino_ser.is_open:
                            if arduino_port is not None:
                                print("[AdhesiveListener] Arduino serial not open, attempting reopen...")
                                arduino_ser = open_arduino_serial(arduino_port)
                                if arduino_ser is None:
                                    print("[AdhesiveListener] Reopen of Arduino serial failed, dropping Arduino part of command.")
                                    continue
                            else:
                                # No Arduino configured at all; nothing to send.
                                continue

                        arduino_ser.write(line.encode("utf-8"))
                        arduino_ser.flush()
                        print(f"[AdhesiveListener] Sent to Arduino: {line.strip()}")
                    except Exception as e:
                        print(f"[AdhesiveListener] Error writing to Arduino serial: {e}")
                        # Try reopening once, then drop this command
                        try:
                            if arduino_ser is not None:
                                arduino_ser.close()
                        except Exception:
                            pass
                        arduino_ser = open_arduino_serial(arduino_port)
                        if arduino_ser is None:
                            print("[AdhesiveListener] Could not recover Arduino serial; future Arduino commands may fail until process is restarted.")
        finally:
            print("[AdhesiveListener] Shutting down, closing serials.")
            # Signal keep-alive thread to stop
            _vesc_thread_stop = True
            try:
                if arduino_ser is not None and arduino_ser.is_open:
                    arduino_ser.close()
            except Exception:
                pass
            try:
                if vesc_ser is not None and vesc_ser.is_open:
                    vesc_ser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
