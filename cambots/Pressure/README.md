# Pressure Control Module

This module provides control for the Nanotec motor used in the pressure system.

## Files

- `velocity_test.py` - Standalone test script for motor velocity control
- `velocity_control.py` - TCP listener for real-time velocity control
- `start_velocity_listener.sh` - Helper script to start the velocity listener
- `__init__.py` - Python package initialization

## Usage

### 1. Run Velocity Test

The velocity test runs a predefined sequence:
- Positive velocity (300 RPM) for 2 seconds
- Negative velocity (-300 RPM) for 2 seconds
- Smooth stop

Run from command line:
```bash
cd ~/Documents/LightsOff_Project/cambots/Pressure
python3 velocity_test.py
```

Or use the Dashboard: `Pressure → Run Nanotec`

### 2. Real-time Velocity Control

For interactive control with the Dashboard, you need to start the velocity control listener first.

#### Start the listener:
```bash
cd ~/Documents/LightsOff_Project/cambots/Pressure
bash start_velocity_listener.sh
```

Or manually:
```bash
python3 velocity_control.py
```

The listener will:
- Initialize the Nanotec motor
- Enable the motor (DS402 state machine)
- Listen on TCP port 5002 for velocity commands
- Accept integer velocity values (RPM)
- Update motor speed in real-time

#### Use from Dashboard:
1. Start the listener on your remote machine (see above)
2. Open Dashboard on your control machine
3. Navigate to: `Pressure → Velocity Control`
4. Enter velocity value in RPM and press Enter or click "Send Velocity"
5. Click "Stop Motor" to set velocity to 0

#### Use from command line:
```bash
# Send velocity command
echo "500" | nc <remote-host> 5002

# Stop motor
echo "0" | nc <remote-host> 5002

# Shutdown listener
echo "STOP" | nc <remote-host> 5002
```

## Configuration

Edit the configuration variables at the top of the Python files:

- `COM_PORT` - Serial port for Nanotec motor (default: "COM7")
- `TARGET_DESC_CONTAINS` - Device description filter (default: "PD2-C4118L1804-E-01")
- `LISTEN_PORT` - TCP port for velocity listener (default: 5002)

## Requirements

- `nanotec-nanolib` Python package
- Nanotec motor connected via USB/Serial
- Network connectivity for remote control

## Troubleshooting

### Motor not found
- Check USB connection
- Verify COM_PORT setting
- Ensure nanotec-nanolib is installed

### Listener connection refused
- Ensure listener is running: `ps aux | grep velocity_control`
- Check port is not in use: `lsof -i:5002`
- Verify firewall settings allow port 5002

### Motor fault
- The script will attempt automatic fault reset
- Check motor error register (0x1001)
- Power cycle the motor if persistent faults occur
