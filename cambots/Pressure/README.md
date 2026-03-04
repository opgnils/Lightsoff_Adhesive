# Pressure Control Module

This module provides control for the Nanotec motor used in the pressure system.

## Motor Specifications

- **Model**: Nanotec PD2-C4118L1804-E-01
- **Maximum Velocity**: 100 RPM (motor shaft)
- **Gearbox**: GPLE40-3S-80 (80:1 ratio)
- **Lead Screw**: TR20x4 (4mm per revolution)
- **Encoder**: Magnetic absolute, 1024 counts/rev

**Linear Speed Calculation:**
- Maximum linear speed: 100 RPM × 0.05 mm/rev = 5 mm/min = 0.083 mm/sec

## Files

- `velocity_test.py` - Standalone test script for motor velocity control
- `velocity_control.py` - TCP listener for real-time velocity control
- `start_velocity_listener.sh` - Helper script to start the velocity listener
- `debug_velocity.py` - Debug script for velocity readback diagnostics
- `test_velocity_objects.py` - Quick test for CANopen velocity objects
- `__init__.py` - Python package initialization

## Usage

### 1. Run Velocity Test

The velocity test runs a predefined sequence:
- Positive velocity (100 RPM) for 2 seconds
- Negative velocity (-100 RPM) for 2 seconds
- Smooth stop

**Note:** Maximum safe velocity is 100 RPM.

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

# Get actual velocity from encoder
echo "GET_VELOCITY" | nc <remote-host> 5002

# Shutdown listener
echo "STOP" | nc <remote-host> 5002
```

## Protocol

The velocity control listener accepts the following commands on port 5002:

### Set Velocity
Send an integer value (RPM):
```
<velocity_rpm>\n
```
Response:
```
OK:<velocity>\n
```

### Get Actual Velocity
Send:
```
GET_VELOCITY\n
```
Response:
```
ACTUAL:<rpm>\n
```
This returns the actual motor velocity from the encoder (Object 0x606C).

### Stop Listener
Send:
```
STOP\n
```
Response:
```
OK:STOPPING\n
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

### Velocity Readback Shows 0
If actual velocity always shows 0 RPM:

1. **Run the debug script** to see what values the motor is reporting:
   ```bash
   cd ~/Documents/LightsOff_Project/cambots/Pressure
   python3 debug_velocity.py
   ```
   This will test reading from multiple velocity objects (0x60FF, 0x6043, 0x606C) and show position changes.

2. **Check the listener logs** for debug output:
   ```bash
   # Restart listener to see fresh debug output
   pkill -f velocity_control
   python3 velocity_control.py
   
   # In another terminal, test GET_VELOCITY
   echo "GET_VELOCITY" | nc localhost 5002
   ```
   Look for lines starting with `[DEBUG]` showing what was read from each object.

3. **Verify motor is actually moving**:
   - Check if you hear/see the motor spinning
   - Watch the position value (0x6064) - it should change if motor is moving
   - Try higher velocities (500+ RPM) for more obvious movement

4. **Check mode of operation**:
   - Must be in Profile Velocity mode (0x6060 = 3)
   - Some motors need different settings for encoder feedback

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
