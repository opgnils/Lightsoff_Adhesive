# Velocity Readback Debugging

## Issue
Actual velocity is showing 0 RPM even when motor is commanded to run at 100-200 RPM.

## Possible Causes

### 1. Velocity Units Mismatch
The motor might report velocity in different units than RPM:
- **Target velocity (0x60FF)**: Set in RPM
- **Actual velocity (0x606C)**: Might be in encoder counts/second or other units
- Some motors require unit conversion based on motor parameters

### 2. Profile Velocity Mode Behavior
In Profile Velocity mode (mode 3):
- Motor may ramp to target velocity over time
- 0x606C might only update when motor reaches steady state
- Try reading **0x6043 (Velocity Demand)** instead - this shows the internal setpoint

### 3. Encoder Not Configured
- Motor might not have encoder feedback enabled
- Encoder resolution might not be set correctly
- Some firmware versions don't support velocity readback

### 4. Motor Not Actually Moving
- Check if you can hear/see the motor spinning
- Verify position (0x6064) is changing
- Motor might be stalling or not enabled properly

## Debug Tools

### Debug Script: `debug_velocity.py`
Comprehensive test script that:
- Initializes motor properly
- Tests multiple velocities (100, 200, -100, -200, 0)
- Reads from ALL velocity-related objects:
  - **0x60FF**: Target velocity (what you set)
  - **0x6043**: Velocity demand (internal setpoint)
  - **0x606C**: Actual velocity (encoder feedback)
  - **0x6064**: Actual position (to verify movement)
- Takes multiple samples over time
- Shows position delta to confirm motor is moving

**Usage:**
```bash
cd ~/Documents/LightsOff_Project/cambots/Pressure
python3 debug_velocity.py
```

**Expected output:**
```
Testing velocity: 100 RPM
----------------------------------------
  Set target velocity: 100
  [1] Target velocity (0x60FF): 100
  [1] Velocity demand (0x6043): 97
  [1] Actual velocity (0x606C): 0 or ???
  [1] Position: 1523 (delta: 45)
  
  [2] Target velocity (0x60FF): 100
  [2] Velocity demand (0x6043): 100
  [2] Actual velocity (0x606C): 98
  [2] Position: 1612 (delta: 89)
```

### Updated velocity_control.py
Now includes debug output when GET_VELOCITY is called:
```python
[DEBUG] Read 0x606C (actual velocity): 0
[DEBUG] Read 0x6043 (velocity demand): 98
[DEBUG] Read 0x60FF (target velocity): 100
```

This helps diagnose which object has valid data.

## Solutions to Try

### Solution 1: Use Velocity Demand Instead
If 0x606C always returns 0, use 0x6043 (velocity demand):

```python
# In velocity_control.py, change get_actual_velocity():
def get_actual_velocity(accessor, dev_handle) -> int:
    try:
        # Try velocity demand first (more reliable on some motors)
        vel_demand = rnum(accessor, dev_handle, OD_VEL_DEMAND)
        return vel_demand
    except:
        # Fall back to actual velocity
        actual_vel = rnum(accessor, dev_handle, OD_ACTUAL_VEL)
        return actual_vel
```

### Solution 2: Calculate from Position
If velocity objects don't work, calculate from position changes:

```python
last_position = 0
last_time = 0

def get_actual_velocity(accessor, dev_handle) -> int:
    global last_position, last_time
    
    import time
    current_time = time.time()
    current_pos = rnum(accessor, dev_handle, OD_ACTUAL_POS)
    
    if last_time > 0:
        dt = current_time - last_time  # seconds
        dpos = current_pos - last_position  # encoder counts
        
        # Convert to RPM
        # Assuming 1024 counts/rev encoder
        rpm = (dpos / 1024.0) / (dt / 60.0)
        
        last_position = current_pos
        last_time = current_time
        return int(rpm)
    else:
        last_position = current_pos
        last_time = current_time
        return 0
```

### Solution 3: Check Motor Parameters
Some motors require setting velocity encoder resolution:

```python
# Motor-specific parameter (check manual)
OD_VEL_ENCODER_RES = Nanolib.OdIndex(0x6094, 0x01)  # Example
# Set encoder pulses per revolution
w(accessor, dev_handle, OD_VEL_ENCODER_RES, 1024, 32)
```

### Solution 4: Use Different Mode
Try **Cyclic Synchronous Velocity Mode (mode 9)** instead of Profile Velocity:

```python
# Instead of mode 3, use mode 9
w(accessor, dev_handle, OD_MODE, 9, 8)

# In cyclic mode, actual velocity might be more accurate
```

## Next Steps

1. **Run debug_velocity.py** on the motor machine to see actual values
2. **Check which object returns non-zero values**:
   - If 0x6043 works → Use velocity demand
   - If 0x606C is always 0 → Calculate from position
   - If position changes but velocities are 0 → Encoder issue
3. **Review motor documentation** for specific object indices
4. **Try different operation modes** if needed

## Technical Notes

### CANopen Objects
- **0x6040**: Controlword (command motor)
- **0x6041**: Statusword (motor state)
- **0x6043**: Velocity demand value (internal setpoint after profile)
- **0x6060**: Modes of operation (3 = profile velocity)
- **0x6064**: Position actual value (encoder counts)
- **0x606C**: Velocity actual value (encoder-based speed)
- **0x60FF**: Target velocity (your command)

### Units
Typical units for Nanotec motors:
- **Position**: Encoder counts (1024 per revolution for magnetic encoder)
- **Velocity**: RPM or counts/second (depends on firmware)
- **Target velocity**: Usually RPM when in profile velocity mode

### Profile Velocity Mode Behavior
When you set target velocity (0x60FF):
1. Motor calculates trajectory based on acceleration limits
2. Velocity demand (0x6043) shows the current setpoint in the ramp
3. Actual velocity (0x606C) shows measured speed from encoder
4. Motor follows the profile until reaching target velocity

If acceleration is slow, actual velocity lags behind target.
