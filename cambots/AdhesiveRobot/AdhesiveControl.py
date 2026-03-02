import serial
import sys
import time


def AdhesiveControl(command: str, port: str = "/dev/ttyACM0", baud: int = 9600):
    """Send a raw adhesive flow command string over serial.

    The Arduino code uses only the last two comma-separated values
    as flow rates (in uL/s) for the two steppers.

    Example command: "1200,400,300" where 400 and 300 are the flows.
    """
    try:
        ser = serial.Serial(port, baud, timeout=1)
        # Match MotorControl behavior: wait briefly for Arduino reset
        time.sleep(2)
        cmd = command.strip() + "\n"
        ser.write(cmd.encode())
        print(f"[AdhesiveControl] Sent: {cmd.strip()} on {port}")
        ser.close()
    except Exception as e:
        print(f"[AdhesiveControl] Error: {e}")


if __name__ == "__main__":
    # Usage: python3 AdhesiveControl.py "1200,400,300" [port]
    if not (2 <= len(sys.argv) <= 3):
        print('Usage example: python3 AdhesiveControl.py "1200,400,300" [port]')
        sys.exit(1)

    cmd_str = sys.argv[1]
    port_arg = sys.argv[2] if len(sys.argv) == 3 else "/dev/ttyACM0"
    AdhesiveControl(cmd_str, port=port_arg)
