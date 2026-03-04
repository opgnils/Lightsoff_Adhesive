# Pressure Motor Control (Nanotec)

TCP-based remote control system for Nanotec motors used in pressure applications.

## Architecture

```
Dashboard (Laptop)  --[TCP 5002]-->  PressureListener (Jetson)  --[USB]-->  Nanotec Motor
```

## Files

- **PressureListener.py**: TCP listener that runs on each Jetson, controls the motor via USB
- Motor control integrated into Dashboard under "Pressure > Manual control"

## Setup on Jetson

### 1. Install Dependencies

```bash
# Install pip if needed
sudo apt install python3-pip

# Install pyserial (may be needed for USB communication)
pip3 install pyserial

# Install Nanotec nanolib
# Note: This library may need to be obtained from Nanotec's website or support
# Contact Nanotec for the correct installation method
pip3 install nanolib  # or download from Nanotec
```

### 2. Connect Motor

- Connect Nanotec motor to Jetson via USB
- Motor will appear as `/dev/ttyACM0` (or similar)
- PressureListener will auto-detect the motor

### 3. Run Listener

```bash
cd ~/Documents/LightsOff_Project/cambots/PressureRobot
python3 PressureListener.py
```

The listener will:
- Auto-detect the Nanotec motor on USB
- Listen on TCP port 5002
- Accept commands from the Dashboard

### 4. Test Connection

From the Dashboard on your laptop:
1. Go to "Pressure > Manual control"
2. Click "Connect Motor"
3. Enter velocity and click "Set Velocity"
4. Click "Stop Motor" to stop
5. Click "Disconnect" when done

## TCP Protocol

The PressureListener accepts these commands on port 5002:

| Command | Description | Response |
|---------|-------------|----------|
| `CONNECT` | Connect and enable motor | `OK:CONNECTED` or `ERROR:<msg>` |
| `VELOCITY:<value>` | Set velocity (e.g., `VELOCITY:500`) | `OK:VELOCITY_SET:<value>` or `ERROR:<msg>` |
| `STOP` | Stop motor (velocity = 0) | `OK:STOPPED` or `ERROR:<msg>` |
| `DISCONNECT` | Disable and disconnect | `OK:DISCONNECTED` or `ERROR:<msg>` |
| `STATUS` | Get motor status | `OK:STATUS:connected=<bool>,velocity=<val>,position=<val>` |

All commands must be newline-terminated (`\n`).

## Motor Control

The PressureListener uses:
- **Nanotec nanolib** Python library
- **CiA-402 (DS402)** state machine for motor enable/disable
- **Profile Velocity Mode** (mode 3) for velocity control
- **Object Dictionary** registers:
  - `0x6040`: Controlword
  - `0x6041`: Statusword  
  - `0x6060`: Operation mode
  - `0x60FF`: Target velocity
  - `0x606C`: Actual velocity
  - `0x6064`: Actual position

## Troubleshooting

### No ACM devices found
- Check USB connection
- Run `ls /dev/ttyACM*` to verify device exists
- Check USB permissions: `sudo usermod -a -G dialout $USER` (logout/login required)

### nanolib not available
- Verify installation: `python3 -c "from nanotec_nanolib import Nanolib"`
- Contact Nanotec support for library installation instructions
- May need to download SDK from Nanotec website

### Connection refused from Dashboard
- Verify PressureListener is running on Jetson
- Check firewall: `sudo ufw allow 5002/tcp`
- Verify Jetson IP address matches SSH config

### Motor not responding
- Check motor power supply
- Verify DS402 enable sequence completes
- Check motor controller LED indicators
- Verify motor firmware is up-to-date

## Development

To modify the listener:
1. Edit `PressureListener.py` on the Jetson
2. Restart the listener process
3. Test from Dashboard

To modify Dashboard pressure control:
1. Edit `Dashboard.py` on your laptop
2. Look for `_pressure_*` methods (around line 2026-2219)
3. Restart Dashboard to test changes
