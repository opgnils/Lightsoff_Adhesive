# Torque Monitoring Implementation Summary

## Overview
Added real-time torque monitoring to the velocity control system, providing visibility into motor load and mechanical resistance.

## Changes Made

### 1. Backend - velocity_control.py

**Added CANopen object**:
```python
OD_TORQUE_ACTUAL = Nanolib.OdIndex(0x6077, 0x00)  # Torque actual value
```

**New function**:
```python
def get_actual_torque(accessor, dev_handle) -> int:
    """Get actual motor torque in per mille (‰) of rated torque."""
    torque = rnum(accessor, dev_handle, OD_TORQUE_ACTUAL, signed=True)
    return torque
```

**New TCP commands**:
- `GET_TORQUE` - Returns torque only
- `GET_STATUS` - Returns both velocity and torque (used by Dashboard)

### 2. Frontend - Dashboard.py

**Added state variable**:
```python
self.actual_torque = 0  # Actual motor torque in per mille (‰)
```

**Updated `_fetch_actual_velocity()`**:
- Now fetches both velocity and torque using `GET_STATUS` command
- Parses response: `STATUS:100,500` (velocity,torque)
- More efficient - one TCP call instead of two

**Updated display**:
- Converts torque from ‰ to Nm: `torque_nm = (raw / 1000.0) * 20.0`
- Converts to percentage: `torque_percent = raw / 10.0`
- Color coding:
  - Green (<30%): Light load
  - Yellow (30-70%): Medium load
  - Red (>70%): High load

### 3. Documentation

**New file**: `TORQUE_MONITORING.md`
- Complete torque monitoring guide
- Value interpretation table
- Color coding explanation
- Usage scenarios
- Troubleshooting guide
- Safety considerations
- Spindle force calculations

**Updated files**:
- `README.md` - Added GET_TORQUE and GET_STATUS commands
- `VELOCITY_FEEDBACK.md` - Updated example display with torque

## Motor Torque Specifications

- **Rated torque**: 20 Nm (motor shaft)
- **Max torque**: 32 Nm (160% overload capacity)
- **CANopen units**: Per mille (‰) - 1000 = 100% = 20 Nm
- **Resolution**: 0.1% (1 unit = 0.02 Nm)

## Display Example

```
Current Status:
  • Commanded: 100 RPM DISENGAGE (↓)
  • Actual: 98 RPM ✓
  • Torque: 8.2 Nm (41.0%)
  • Distance traveled: 15.47 mm
```

## Benefits

1. **Real-time load monitoring** - See motor stress level instantly
2. **Mechanical issue detection** - High torque indicates binding or obstruction
3. **Process optimization** - Understand load patterns during operation
4. **Safety** - Warning before motor reaches limits
5. **Quality control** - Detect anomalies in mechanical resistance

## Torque-based Applications

### 1. Contact Detection
Monitor torque increase to detect when spindle contacts workpiece:
- Free running: <10% torque
- Contact: Sudden increase to 20-40%

### 2. Stall Detection
Automatic detection of motor stalling:
- Velocity → 0
- Torque → >70%
- Action: Stop motor, alert operator

### 3. Force Control (Future)
Use torque feedback for force-controlled operations:
- Set target torque (e.g., 50%)
- Move until torque reached
- Stop and hold position

### 4. Wear Monitoring
Track torque over time to detect mechanical wear:
- Increasing baseline torque → friction increase
- Suggest maintenance when threshold exceeded

## Spindle Force Calculation

At 100% motor torque (20 Nm):
```
Spindle Torque = 20 Nm × 80 (gearbox) = 1600 Nm
Axial Force = 1600 Nm / (0.004 m / 2π) = 2,512 kN ≈ 251 tons
```

**This is theoretical maximum. Actual safe force is much lower due to mechanical limits.**

## Testing Recommendations

1. **No-load test**: Verify torque <10% when running free
2. **Light load test**: Apply small resistance, verify torque 10-30%
3. **Normal operation**: Monitor typical torque range during real work
4. **Overload test**: Carefully test with heavy load, verify motor stops before damage
5. **Stall test**: Block spindle, verify torque reaches 100% and motor stops

## Safety Warnings

⚠️ **High torque = high forces at spindle**
- 50% motor torque = ~125 tons spindle force
- 100% motor torque = ~251 tons spindle force
- Use extreme caution when operating at high torque
- Ensure mechanical components rated for these forces

⚠️ **Overload protection**
- Motor can handle 160% (32 Nm) briefly
- Continuous operation should stay <80%
- Consider adding automatic limits in software

## Files Modified

1. `cambots/Pressure/velocity_control.py`
   - Added OD_TORQUE_ACTUAL object
   - Added get_actual_torque() function
   - Added GET_TORQUE and GET_STATUS commands

2. `base/programs/Dashboard.py`
   - Added actual_torque state variable
   - Modified _fetch_actual_velocity() to fetch torque
   - Updated display with torque information and color coding

3. Documentation:
   - Created `TORQUE_MONITORING.md` (comprehensive guide)
   - Updated `README.md` (protocol documentation)
   - Updated `VELOCITY_FEEDBACK.md` (display example)

## Next Steps

Possible enhancements:
1. Add torque limit alerts
2. Implement automatic stall detection
3. Add torque history graph
4. Log torque data for analysis
5. Implement force-based positioning mode

## Conclusion

The torque monitoring feature is now fully integrated with the velocity control system. The Dashboard displays real-time torque alongside velocity and distance, providing complete visibility into motor operation and mechanical load.
