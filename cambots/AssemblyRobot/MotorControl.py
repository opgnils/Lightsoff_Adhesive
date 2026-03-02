import serial
import time
import sys

def MotorControl(turn: bool, rpm: int, duration: int, port="/dev/ttyUSB0", baud=9600):
    try:
        ser = serial.Serial(port, baud, timeout=1)
        time.sleep(2)  # wait for Arduino reset
        value = rpm if turn else -rpm
        cmd = f"{value}\n"
        ser.write(cmd.encode())
        print(f"[MotorControl] Sent: {cmd.strip()}")
        time.sleep(duration)
        ser.write(b"0\n")  # stop motor
        ser.close()
    except Exception as e:
        print(f"[MotorControl] Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 MotorControl.py <True/False> <RPM> <seconds>")
        sys.exit(1)

    turn_flag = sys.argv[1].lower() in ["true", "1", "yes"]
    rpm_val = int(sys.argv[2])
    duration_val = int(sys.argv[3])

    MotorControl(turn_flag, rpm_val, duration_val)
