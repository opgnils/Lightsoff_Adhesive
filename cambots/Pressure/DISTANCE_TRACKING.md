# Distance Tracking Feature

## Overview
The velocity control interface now includes real-time distance tracking that calculates the linear travel distance of the spindle based on motor velocity.

## Motor Specifications
From `nanotecMotorSpecs.md`:
- **Motor:** Nanotec PD2-C4118L1804-E-01 (NEMA17 stepper)
- **Maximum Velocity:** 100 RPM (motor shaft)
- **Gearbox:** GPLE40-3S-80 (80:1 ratio)
- **Lead Screw:** TR20x4 (4mm per revolution)
- **Encoder:** Magnetic absolute, 1024 counts/rev

## Distance Calculation

### Formula
```
Linear Speed (mm/min) = Motor RPM / 80 × 4 mm/rev
                      = Motor RPM × 0.05 mm/rev

Distance (mm) = Linear Speed × Time (minutes)
```

**Important:** Distance is calculated using the **actual measured velocity** from the motor encoder (not the commanded velocity), ensuring accurate tracking even if the motor doesn't perfectly follow the commanded speed.

### Example Calculations

**Example 1: 100 RPM for 60 seconds**
- Linear speed = 100 × 0.05 = 5 mm/min
- Time = 60 seconds = 1 minute
- Distance = 5 × 1 = **5 mm**

**Example 2: -100 RPM for 30 seconds**
- Linear speed = -100 × 0.05 = -5 mm/min
- Time = 30 seconds = 0.5 minutes
- Distance = -5 × 0.5 = **-2.5 mm**

## Direction Convention

- **Negative RPM (-) = ENGAGE** → Moving down (spindle extends)
- **Positive RPM (+) = DISENGAGE** → Moving up (spindle retracts)

The distance accumulator tracks the total net displacement:
- Negative distance = net downward movement (engaged)
- Positive distance = net upward movement (disengaged)

## User Interface

### Display Components
The velocity control form now shows:
1. **Commanded Velocity** (RPM) - The target velocity you set
2. **Actual Velocity** (RPM) - Real-time feedback from motor encoder
3. **Velocity Tracking Status** - Visual indicator of how well motor tracks commanded velocity:
   - **✓** (Green) - Excellent tracking (within ±10 RPM)
   - **~** (Yellow) - Acceptable tracking (within ±50 RPM)
   - **!** (Red) - Poor tracking (>50 RPM difference)
4. **Distance Traveled** (mm) - continuously updated
5. Three buttons:
   - **Send Velocity** - Apply the entered RPM value
   - **Stop Motor** - Immediately stop (velocity = 0)
   - **Reset Distance** - Clear the distance counter to 0.00 mm

### Real-time Updates
The display updates **every second** while the motor is running, showing:
- Commanded velocity in RPM (what you requested)
- Actual velocity in RPM (what motor encoder reports)
- Direction: ENGAGE (↓), DISENGAGE (↑), or STOPPED
- Accumulated distance with 2 decimal precision (e.g., "12.34 mm")
- Tracking quality indicator

### Status Colors
- **Cyan (Commanded)** - Target velocity
- **Purple (Actual)** - Measured velocity from encoder
- **Red (ENGAGE)** - Negative velocity, moving down
- **Green (DISENGAGE)** - Positive velocity, moving up
- **Gray (STOPPED)** - Zero velocity

## Usage Example

1. **Start listener** (if not running):
   ```
   Menu: 7 → Pressure → Start velocity listener
   ```

2. **Open velocity control**:
   ```
   Menu: 7 → Pressure → Velocity Control
   ```

3. **Set velocity**:
   - Enter RPM value (e.g., -300 for engage at 300 RPM)
   - Press Enter or click "Send Velocity"
   - Distance tracking starts immediately

4. **Monitor progress**:
   - Watch the distance counter update every second
   - Distance = 0.00 mm at start
   - Accumulates while motor runs

5. **Change velocity**:
   - Enter new RPM value
   - Distance continues to accumulate from current value
   - Previous motion is preserved in the counter

6. **Stop and reset**:
   - Click "Stop Motor" to halt movement
   - Click "Reset Distance" to zero the counter
   - Tracking resumes from 0 when you start again

## Technical Implementation

### Velocity Feedback System
The system reads actual velocity from the motor encoder via CANopen object dictionary:
- **Object 0x6043** - Velocity demand value (internal motor setpoint)
- Falls back to 0x6043 if 0x606C (actual velocity) is not supported
- Polled every second during motor operation
- Compared against commanded velocity (Object 0x60FF)

**Note:** The motor firmware uses object 0x6043 (velocity demand) for feedback instead of 0x606C (velocity actual). This provides the internal setpoint the motor controller is trying to achieve.

### Distance Tracking Logic
The `VelocityControl` widget maintains:
- `current_velocity`: Commanded motor RPM (target)
- `actual_velocity`: Measured motor RPM (from 0x6043)
- `distance_traveled`: Accumulated distance in mm (calculated from **actual_velocity**)
- `start_time`: Timestamp when velocity was last set
- `update_timer`: 1-second interval timer for display updates

### Calculation Method
1. **On velocity change**:
   - Calculate distance traveled at old velocity
   - Add to accumulated distance
   - Reset timer with new velocity
   - Start background thread to fetch actual velocity

2. **Every second (while running)**:
   - Query motor for actual velocity (0x606C)
   - Calculate elapsed time since velocity was set
   - Compute current distance = old accumulated + new distance
   - Update display with commanded vs actual velocity
   - Show tracking quality indicator

3. **On stop**:
   - Accumulate final distance
   - Stop the update timer
   - Keep accumulated distance for reference
   - Clear actual velocity reading

### Thread Safety
- Display updates use `call_from_thread()` for safe UI updates
- Timer is properly cleaned up on widget unmount
- No race conditions on distance accumulation

## Precision Notes

- **Time resolution**: 1 second updates
- **Distance precision**: 0.01 mm (2 decimal places)
- **Calculation accuracy**: Based on exact gear ratio and lead screw spec
- **Real-world factors**: Does not account for:
  - Mechanical backlash (~22 arcmin)
  - Step loss/skipped steps
  - Lead screw wear or pitch variation
  - Load-dependent deformation

For high-precision applications, consider adding encoder feedback for closed-loop position control.

## Future Enhancements

Possible improvements:
1. **Position limits**: Set max engage/disengage distances
2. **Speed profiles**: Ramp up/down instead of instant velocity changes
3. **Position feedback**: Read encoder to verify actual position
4. **Auto-stop**: Stop when reaching target distance
5. **History log**: Record velocity changes and distances over time
