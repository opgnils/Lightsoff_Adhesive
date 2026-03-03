# Adhesive Robot Control Guide

This guide explains how to control the adhesive robot from the Dashboard and command line.

## Overview

The adhesive robot has 3 motors:
- **Motor 1**: RPM control (max: ±6000 RPM)
- **Motor 2**: Flowrate A in µL/s (max: ±1150 µL/s)
- **Motor 3**: Flowrate B in µL/s (max: ±1150 µL/s)

Control is done via TCP commands sent to port 5001 on the robot's hostname.

## Dashboard Menu

The Dashboard provides 4 adhesive control options:

### 1. Manual Control
- **Purpose**: Send individual motor commands interactively
- **How it works**:
  - Ensures adhesive listeners are running on all selected devices
  - Displays current motor configuration and limits
  - Provides instructions for sending TCP commands

- **Manual Command Format**: `motor1,motor2,motor3`
  ```bash
  # Example: Set Motor1=1000 RPM, Motor2=500 µL/s, Motor3=500 µL/s
  echo "1000,500,500" | nc robot_hostname 5001
  
  # Stop all motors
  echo "0,0,0" | nc robot_hostname 5001
  ```

### 2. Run Profile
- **Purpose**: Execute pre-programmed sequences from CSV files
- **Location**: `base/programs/adhesive_profiles/`
- **Available profiles**:
  - `adh_test_profile.csv` - Test profile
  - `adh_test_nonsync.csv` - Non-synchronized test
  - `fast_rampUp.csv` - Quick ramp-up sequence

- **How to run**:
  ```bash
  cd base/programs
  python3 run_adhesive_profile.py adhesive_profiles/fast_rampUp.csv
  ```

- **CSV Format**:
  ```csv
  # time, motor1_rpm, motor2_ul_s, motor3_ul_s
  0.0,  0,    0,    0      # Start at rest
  2.0,  1000, 500,  500    # Ramp up at 2 seconds
  10.0, 2000, 1000, 1000   # Full speed at 10 seconds
  15.0, 0,    0,    0      # Stop at 15 seconds
  ```

- **Features**:
  - ✅ Automatic listener startup
  - ✅ Timed command execution
  - ✅ Emergency stop (press 'q' during execution)
  - ✅ Final safety stop (sends 0,0,0)
  - ✅ Progress display

### 3. View History
- **Purpose**: Review past adhesive operations from log files
- **Location**: `base/programs/logs/` or `logs/`
- **Format**: JSONL (JSON Lines) files with timestamps and messages

### 4. Emergency Stop
- **Purpose**: Immediately halt all adhesive motors
- **How it works**:
  - Sends `0,0,0` command 3 times for redundancy
  - Uses TCP socket connection for speed
  - Logs emergency stop event
- **Use when**:
  - Unexpected behavior detected
  - Need to abort profile execution
  - Safety concern arises

## Profile Runner Script

The `run_adhesive_profile.py` script provides standalone profile execution.

### Usage
```bash
python3 run_adhesive_profile.py <profile.csv>
```

### Features
- Auto-discovers online devices
- Ensures adhesive listeners are running (port 5001)
- Loads and validates CSV profile
- Executes timed motor commands
- Emergency stop: Press 'q', ESC, or Ctrl+C
- Sends final safety stop (0,0,0)

### Example
```bash
# Run fast ramp-up profile
cd /home/icd-wmpc06/Documents/Lightsoff_Adhesive/base/programs
python3 run_adhesive_profile.py adhesive_profiles/fast_rampUp.csv
```

### Output
```
============================================================
Running adhesive profile: fast_rampUp.csv
Devices: robot1, robot2
============================================================

[1/3] Ensuring adhesive listeners are running...
  ✓ Listener ready on robot1
  ✓ Listener ready on robot2

[2/3] Loading profile from adhesive_profiles/fast_rampUp.csv...
  ✓ Loaded 12 steps

[3/3] Executing profile...
  Press 'q' or ESC to EMERGENCY STOP (sends 0,0,0 and aborts)

  [  1/ 12] t=  0.00s -> 0,0,0                ✓
  [  2/ 12] t=  2.00s -> 1000,500,500         ✓
  [  3/ 12] t=  5.00s -> 1500,750,750         ✓
  ...
```

## Creating Custom Profiles

1. Create a new CSV file in `adhesive_profiles/` directory
2. Use format: `time, motor1, motor2, motor3`
3. Time values in seconds (can be decimal: 2.5, 10.75, etc.)
4. Motor values within limits:
   - Motor 1: -6000 to +6000 RPM
   - Motor 2: -1150 to +1150 µL/s
   - Motor 3: -1150 to +1150 µL/s
5. Comments allowed (start line with `#`)
6. Empty lines are ignored

### Example Custom Profile
```csv
# Custom adhesive application profile
# time, motor1_rpm, motor2_ul_s, motor3_ul_s

# Initial startup
0.0,   0,    0,    0
1.0,   500,  250,  250

# Gradual ramp-up
5.0,   1000, 500,  500
10.0,  1500, 750,  750
15.0,  2000, 1000, 1000

# Hold at full speed
30.0,  2000, 1000, 1000

# Gradual shutdown
35.0,  1500, 750,  750
40.0,  1000, 500,  500
42.0,  500,  250,  250

# Complete stop
45.0,  0,    0,    0
```

## Adhesive Listener

The `AdhesiveListener.py` service runs on each robot and:
- Listens on TCP port 5001
- Receives motor command strings (e.g., "1000,500,500")
- Controls the physical motors via serial/GPIO
- Auto-starts when needed via SSH

### Manual Listener Management
```bash
# Check if listener is running
ssh user@robot_hostname "ps aux | grep AdhesiveListener.py"

# Start listener manually (if needed)
ssh user@robot_hostname "cd ~/Documents/LightsOff_Project && python3 cambots/AdhesiveRobot/AdhesiveListener.py &"

# Restart from Dashboard
# Use: Adhesive Robot -> Restart listener option (in App.py CLI)
```

## Safety Notes

⚠️ **Always:**
- Test profiles with low values first
- Keep emergency stop accessible
- Monitor motor behavior during execution
- Verify limits before running profiles
- Use safety stop (0,0,0) when finished

⚠️ **Motor Limits:**
- Motor 1 (RPM): Exceeding ±6000 may damage mechanism
- Motors 2&3 (µL/s): Exceeding ±1150 may cause overflow
- Negative values reverse direction (use with caution)

⚠️ **Profile Timing:**
- Ensure sufficient time between steps for motor response
- Rapid changes may cause mechanical stress
- Include gradual ramp-up/down phases
- Always end with stop command (0,0,0)

## Troubleshooting

### Listener Not Responding
```bash
# Check listener status
ssh user@robot "ps aux | grep AdhesiveListener"

# Kill and restart
ssh user@robot "pkill -f AdhesiveListener.py"
# Then use Dashboard or run manually
```

### Commands Not Working
1. Verify device is online: `ping robot_hostname`
2. Check listener is running (see above)
3. Test TCP connection: `nc -zv robot_hostname 5001`
4. Try manual command: `echo "0,0,0" | nc robot_hostname 5001`

### Profile Execution Issues
- **Profile not found**: Check path and spelling
- **Permission denied**: Run `chmod +x run_adhesive_profile.py`
- **CSV parsing error**: Verify format (time,m1,m2,m3)
- **Devices offline**: Run device discovery first

## Integration with Dashboard

From the Dashboard:
1. **Connect** menu: Discover and select robots
2. **Adhesive Robot** menu: Access control options
3. **Manual control**: Displays instructions and current state
4. **Run profile**: Lists available profiles and execution command
5. **Emergency Stop**: One-click safety halt
6. **View history**: Check past operations

The Dashboard provides a unified view but delegates profile execution to the standalone script for better control and monitoring.
