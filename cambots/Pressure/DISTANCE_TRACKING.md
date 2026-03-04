# Distance Tracking Feature

## Overview
The velocity control interface now includes real-time distance tracking that calculates the linear travel distance of the spindle based on motor velocity.

## Motor Specifications
From `nanotecMotorSpecs.md`:
- **Motor:** Nanotec PD2-C4118L1804-E-01 (NEMA17 stepper)
- **Gearbox:** GPLE40-3S-80 (80:1 ratio)
- **Lead Screw:** TR20x4 (4mm per revolution)

## Distance Calculation

### Formula
```
Linear Speed (mm/min) = Motor RPM / 80 × 4 mm/rev
                      = Motor RPM × 0.05 mm/rev

Distance (mm) = Linear Speed × Time (minutes)
```

### Example Calculations

**Example 1: 300 RPM for 60 seconds**
- Linear speed = 300 × 0.05 = 15 mm/min
- Time = 60 seconds = 1 minute
- Distance = 15 × 1 = **15 mm**

**Example 2: -500 RPM for 30 seconds**
- Linear speed = -500 × 0.05 = -25 mm/min
- Time = 30 seconds = 0.5 minutes
- Distance = -25 × 0.5 = **-12.5 mm**

## Direction Convention

- **Negative RPM (-) = ENGAGE** → Moving down (spindle extends)
- **Positive RPM (+) = DISENGAGE** → Moving up (spindle retracts)

The distance accumulator tracks the total net displacement:
- Negative distance = net downward movement (engaged)
- Positive distance = net upward movement (disengaged)

## User Interface

### Display Components
The velocity control form now shows:
1. **Current Velocity** (RPM) with direction indicator
2. **Distance Traveled** (mm) - continuously updated
3. Three buttons:
   - **Send Velocity** - Apply the entered RPM value
   - **Stop Motor** - Immediately stop (velocity = 0)
   - **Reset Distance** - Clear the distance counter to 0.00 mm

### Real-time Updates
The display updates **every second** while the motor is running, showing:
- Current velocity in RPM
- Direction: ENGAGE (↓), DISENGAGE (↑), or STOPPED
- Accumulated distance with 2 decimal precision (e.g., "12.34 mm")

### Status Colors
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

### Distance Tracking Logic
The `VelocityControl` widget maintains:
- `current_velocity`: Current motor RPM
- `distance_traveled`: Accumulated distance in mm
- `start_time`: Timestamp when velocity was last set
- `update_timer`: 1-second interval timer for display updates

### Calculation Method
1. **On velocity change**:
   - Calculate distance traveled at old velocity
   - Add to accumulated distance
   - Reset timer with new velocity

2. **Every second (while running)**:
   - Calculate elapsed time since velocity was set
   - Compute current distance = old accumulated + new distance
   - Update display

3. **On stop**:
   - Accumulate final distance
   - Stop the update timer
   - Keep accumulated distance for reference

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
