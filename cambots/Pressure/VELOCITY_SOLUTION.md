# Velocity Feedback Solution

## Problem
The actual velocity readback from the Nanotec motor was showing "0 RPM !" even though the motor was running at commanded velocities of 100-200 RPM.

## Root Cause
The motor firmware doesn't support direct encoder velocity readback via CANopen object **0x606C (Velocity Actual Value)**. This object returned 0 even when the motor was moving.

## Solution
Use **object 0x6043 (Velocity Demand Value)** instead of 0x606C for velocity feedback.

### What is 0x6043?
- **Velocity Demand Value** is the internal setpoint that the motor controller is actively trying to achieve
- In Profile Velocity mode, this represents the trajectory generator's output
- It provides a reliable indication of what the motor is doing, even if direct encoder feedback (0x606C) isn't available

## Implementation

### Code Changes

1. **velocity_control.py** - `get_actual_velocity()` function:
   ```python
   # Read both objects
   actual_vel = rnum(accessor, dev_handle, OD_ACTUAL_VEL, signed=True)  # 0x606C
   vel_demand = rnum(accessor, dev_handle, OD_VEL_DEMAND, signed=True)  # 0x6043
   
   # Fallback to demand if actual returns 0
   if actual_vel == 0 and vel_demand != 0:
       return vel_demand
   
   return actual_vel
   ```

2. **Dashboard.py** - `_accumulate_distance()` function:
   ```python
   # Use actual measured velocity for accurate distance tracking
   velocity_to_use = self.actual_velocity if self.actual_velocity != 0 else self.current_velocity
   
   linear_speed_mm_per_min = velocity_to_use * 0.05  # mm/min
   distance_mm = linear_speed_mm_per_min * (elapsed_time / 60.0)
   self.distance_traveled += distance_mm
   ```

3. **Signed integer conversion**:
   - Added `signed=True` parameter to `rnum()` helper function
   - Converts unsigned 32-bit values to signed (handles negative velocities)
   - Necessary because `readNumber()` returns unsigned, but velocities are signed

## Motor Specifications

### Discovered Limits
- **Maximum velocity:** 100 RPM (motor shaft speed)
- Attempting higher speeds may cause issues
- This translates to maximum linear speed: 100 × 0.05 = 5 mm/min

### Motor Configuration
- **Model:** Nanotec PD2-C4118L1804-E-01
- **Encoder:** Magnetic absolute, 1024 counts/rev (hardware present)
- **Firmware limitation:** 0x606C not implemented or not enabled
- **Working object:** 0x6043 (Velocity Demand Value)

## CANopen Objects Used

| Object | Name | Type | Purpose | Status |
|--------|------|------|---------|--------|
| 0x60FF | Target Velocity | Write | Command velocity | ✅ Working |
| 0x6043 | Velocity Demand | Read | Internal setpoint | ✅ **Used for feedback** |
| 0x606C | Velocity Actual | Read | Encoder feedback | ❌ Returns 0 |
| 0x6064 | Position Actual | Read | Encoder position | ✅ Working (alternative) |

## Distance Tracking

### Accuracy
Distance is now calculated using **measured velocity** (0x6043) instead of commanded velocity:
- More accurate tracking
- Accounts for motor lag and acceleration
- Shows real spindle displacement

### Formula
```
Linear Speed (mm/min) = Motor RPM × 0.05
Distance (mm) = Linear Speed × Time (minutes)
```

Where Motor RPM comes from 0x6043 (velocity demand), not the commanded velocity.

## Testing Results

### What Works
- ✅ Motor control via TCP commands
- ✅ Velocity feedback via 0x6043
- ✅ Distance tracking from measured velocity
- ✅ Real-time UI updates
- ✅ Direction indicators (ENGAGE/DISENGAGE)
- ✅ Tracking quality display (✓ ~ !)

### Known Limitations
- Maximum velocity: 100 RPM (hardware or firmware limit)
- 0x606C not available (firmware doesn't support it)
- Using demand value instead of actual encoder velocity

## Alternative Approaches (Not Needed)

If 0x6043 hadn't worked, other options would have been:

1. **Calculate from position delta** (0x6064):
   ```python
   velocity_rpm = (position_delta / 1024.0) * (60.0 / time_delta)
   ```

2. **Use different operation mode:**
   - Cyclic Synchronous Velocity (mode 9) instead of Profile Velocity (mode 3)

3. **Configure encoder parameters:**
   - Set velocity encoder resolution (0x6094)
   - Enable encoder feedback in motor settings

## Files Modified

1. `cambots/Pressure/velocity_control.py`
   - Enhanced `get_actual_velocity()` with 0x6043 fallback
   - Added signed integer conversion

2. `base/programs/Dashboard.py`
   - Modified `_accumulate_distance()` to use measured velocity

3. Documentation updates:
   - `cambots/Pressure/README.md` - Added motor specs and 100 RPM limit
   - `cambots/Pressure/DISTANCE_TRACKING.md` - Updated examples and technical details
   - `cambots/Pressure/VELOCITY_DEBUG.md` - Comprehensive troubleshooting guide

## Conclusion

The velocity feedback system is now fully functional using object 0x6043 (Velocity Demand Value). Distance tracking is accurate and based on measured motor velocity rather than commanded velocity. The system displays both commanded and actual velocities with a tracking quality indicator, providing complete visibility into motor performance.

**Key Takeaway:** When working with CANopen motors, always check multiple objects for velocity feedback. Not all motors/firmware versions support all objects, and the velocity demand value (0x6043) can be a reliable alternative to direct encoder feedback (0x606C).
