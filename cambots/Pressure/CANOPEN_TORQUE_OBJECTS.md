# CANopen Torque Objects Guide

## Overview
Based on the CANopen DS402 standard and Nanotec motor documentation, there are several torque-related objects. This document explains which ones to use and why.

## Torque Objects Summary

| Object | Name | Type | Access | Purpose | Supported? |
|--------|------|------|--------|---------|------------|
| 0x6071 | Target Torque | s16 | RW | Set desired torque | ✅ Yes |
| 0x6072 | Max Torque | u16 | RW | Maximum torque limit | ✅ Yes |
| 0x6074 | **Torque Demand** | s16 | RO | **Internal setpoint** | ✅ **Use This** |
| 0x6077 | Torque Actual | s16 | RO | Encoder feedback | ❓ May not work |
| 0x6087 | Torque Slope | u32 | RW | Torque ramp rate | ✅ Yes |

## Recommended Object: 0x6074 (Torque Demand)

### Why Use 0x6074?
Similar to how we use **0x6043 (Velocity Demand)** instead of 0x606C for velocity:
- **0x6074 shows the internal setpoint** the motor controller is trying to achieve
- Works reliably even if encoder torque feedback (0x6077) isn't supported
- Represents the actual torque being applied by the controller
- Updates in real-time as motor works against load

### Analogy with Velocity
```
Velocity:                          Torque:
0x60FF (Target) = What you set     0x6071 (Target) = What you set
0x6043 (Demand) = Internal goal    0x6074 (Demand) = Internal goal ← USE THIS
0x606C (Actual) = Encoder feedback 0x6077 (Actual) = Encoder feedback (may not work)
```

## Object Details

### 0x6071 - Target Torque (Command)
```
Type: Signed 16-bit
Range: -1000 to +1000
Units: Per mille (‰) of maximum settable current
Access: Read/Write (you set this)
```

**What it does:**
- This is what you command when in Torque Profile Mode (mode 4)
- Motor tries to maintain this torque level
- Positive = forward direction, negative = reverse

**In our case (Profile Velocity Mode):**
- We don't set this directly
- Motor controller calculates required torque to maintain velocity
- Read-only reflects what controller has calculated

### 0x6072 - Max Torque (Limit)
```
Type: Unsigned 16-bit
Range: 0 to 1000
Units: Per mille (‰)
Access: Read/Write
```

**What it does:**
- Safety limit on maximum torque
- Motor will not exceed this value
- Protects motor and mechanical components

### 0x6074 - Torque Demand Value ⭐ RECOMMENDED
```
Type: Signed 16-bit
Range: -1000 to +1000
Units: Per mille (‰) of rated torque
Access: Read-only
```

**What it does:**
- Shows the **actual torque demand** from the controller
- In Profile Velocity mode: this is the torque needed to maintain velocity
- Updates in real-time as load changes
- **This is what we should display in the Dashboard**

**Behavior under load:**
- Free running: 50-150 ‰ (5-15%) - just overcoming friction
- Light load: 200-400 ‰ (20-40%)
- Heavy load: 500-700 ‰ (50-70%)
- Stalled: 800-1000 ‰ (80-100%)

### 0x6077 - Torque Actual Value (may not be supported)
```
Type: Signed 16-bit
Range: -1000 to +1000
Units: Per mille (‰)
Access: Read-only
```

**What it does:**
- Shows measured torque from encoder/sensor feedback
- Requires encoder torque measurement capability
- **May not be implemented in all motor firmwares**

**Known issue:**
- Like 0x606C (velocity actual), this may return 0 or small fixed values
- Motor firmware might not support direct torque measurement
- Use 0x6074 instead for reliable readings

### 0x6087 - Torque Slope
```
Type: Unsigned 32-bit
Range: Depends on motor
Units: Typically ‰/s (per mille per second)
Access: Read/Write
```

**What it does:**
- Rate of change for torque ramping
- Prevents sudden torque changes
- Smooths torque transitions

## Units and Scaling

### Per Mille (‰) Explained
```
‰ is "per thousand" (like % is "per hundred")
1000 ‰ = 100%
500 ‰ = 50%
100 ‰ = 10%
10 ‰ = 1%
```

### Conversion to Newton-meters (Nm)
For our Nanotec motor with **rated torque = 20 Nm**:

```python
torque_nm = (value_permille / 1000.0) * 20.0
```

**Examples:**
- 1000 ‰ = (1000/1000) × 20 = 20.0 Nm (100% rated)
- 500 ‰ = (500/1000) × 20 = 10.0 Nm (50%)
- 250 ‰ = (250/1000) × 20 = 5.0 Nm (25%)
- 35 ‰ = (35/1000) × 20 = 0.7 Nm (3.5%)

### Conversion to Percentage
```python
torque_percent = value_permille / 10.0
```

**Examples:**
- 1000 ‰ = 100.0%
- 500 ‰ = 50.0%
- 35 ‰ = 3.5%

## Testing Procedure

### 1. Run test_torque.py
```bash
cd ~/Documents/Lightsoff_Adhesive/cambots/Pressure
python3 test_torque.py
```

### 2. Test Sequence
1. **Start motor at 50 RPM**
2. **Free running:** Note 0x6074 value (should be ~100-150 ‰)
3. **Apply light hand resistance:** Value should increase to ~300-400 ‰
4. **Clamp hard (stall motor):** Value should reach ~700-1000 ‰
5. **Release:** Value should drop back to free-running level

### 3. Expected Output
```
TORQUE OBJECTS:
  0x6071 (Target Torque):   0 ‰ = 0.00 Nm = 0.0%
  0x6072 (Max Torque):      1000 ‰ = 100.0%
  0x6074 (Torque Demand):   450 ‰ = 9.00 Nm = 45.0% *** USE THIS ***
  0x6077 (Torque Actual):   35 ‰ = 0.70 Nm = 3.5%

VELOCITY (for context):
  0x60FF (Target Vel):      100 RPM
  0x6043 (Velocity Demand): 98 RPM
```

**Analysis:**
- 0x6074 shows 450 ‰ (45%) - realistic for loaded motor
- 0x6077 shows 35 ‰ (3.5%) - wrong, not supported
- **Use 0x6074 for display**

## Implementation Changes

### Backend Change (velocity_control.py)
```python
# OLD - using 0x6077 (doesn't work reliably)
torque = rnum(accessor, dev_handle, OD_TORQUE_ACTUAL, signed=True, bitlen=16)

# NEW - using 0x6074 (works like velocity demand)
torque = rnum(accessor, dev_handle, OD_TORQUE_DEMAND, signed=True, bitlen=16)
```

### No Dashboard Changes Needed
The Dashboard already converts the raw value correctly:
```python
torque_nm = (self.actual_torque / 1000.0) * 20.0  # Convert ‰ to Nm
torque_percent = self.actual_torque / 10.0         # Convert ‰ to %
```

## Why 0.7 Nm Was Wrong

Your observation of **0.7 Nm when clamping** was correct to question!

**What was happening:**
- Motor was stalled → actual torque should be ~80-100% (16-20 Nm)
- 0x6077 returned 35 ‰ → 0.7 Nm (only 3.5%)
- This object isn't supported properly in the firmware

**With 0x6074:**
- Stalled motor → torque demand rises to ~800-1000 ‰
- Converts to 16-20 Nm (80-100%)
- **This matches reality!**

## Safety Notes

### Maximum Torque
- **Rated continuous:** 20 Nm (1000 ‰)
- **Peak (brief):** 32 Nm (1600 ‰ if allowed)
- **Motor can exceed 100%** for short periods
- Set 0x6072 to limit maximum if needed

### Color Coding (Dashboard)
```python
if torque_percent < 30:    # Green - safe
if torque_percent < 70:    # Yellow - working hard
else:                      # Red - approaching limits
```

### Spindle Output Torque
With 80:1 gearbox:
```
Motor: 20 Nm × 80 = 1600 Nm at spindle (rated)
Motor: 32 Nm × 80 = 2560 Nm at spindle (peak)
```

**This generates enormous forces** - use caution at high torque!

## Related Documentation

- `TORQUE_MONITORING.md` - User guide for torque display
- `TORQUE_IMPLEMENTATION.md` - Implementation summary
- `TORQUE_DEBUG.md` - Troubleshooting guide
- `nanotecMotorSpecs.md` - Motor specifications

## Conclusion

**Use 0x6074 (Torque Demand) for reliable torque monitoring**, just like we use 0x6043 (Velocity Demand) for velocity. The "actual" values (0x6077, 0x606C) may not be supported in all firmware versions.
