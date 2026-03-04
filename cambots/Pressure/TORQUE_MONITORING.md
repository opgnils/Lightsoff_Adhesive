# Torque Monitoring Feature

## Overview
The velocity control interface now includes real-time torque monitoring, displaying the current motor load alongside velocity feedback. This provides immediate insight into the mechanical resistance and helps detect issues like stalling, binding, or excessive load.

## Motor Torque Specifications

From `nanotecMotorSpecs.md`:
- **Rated output torque**: 20 Nm (at motor shaft, before gearbox)
- **Max output torque**: 32 Nm
- **Gearbox ratio**: 80:1
- **Output torque at spindle**: Up to 1600 Nm (20 Nm × 80) rated, 2560 Nm max

## CANopen Torque Object

### Object 0x6077 - Torque Actual Value
- **Type**: Signed 16-bit integer
- **Units**: Per mille (‰) of rated torque
- **Range**: -1000 to +1000 (represents -100% to +100%)
- **Resolution**: 0.1% per unit

### Value Interpretation

| Raw Value | Percentage | Torque (Nm) | Status |
|-----------|------------|-------------|--------|
| 0 | 0% | 0 Nm | No load |
| 100 | 10% | 2 Nm | Light load |
| 300 | 30% | 6 Nm | Normal operation |
| 700 | 70% | 14 Nm | High load |
| 1000 | 100% | 20 Nm | Maximum rated |
| >1000 | >100% | >20 Nm | Overload (up to 160% = 32 Nm max) |

**Note**: Negative values indicate torque in the opposite direction (motor braking or back-driven).

## Display Features

### Real-time Torque Display
The Dashboard shows torque in two formats:
1. **Newton-meters (Nm)** - Absolute torque at motor shaft
2. **Percentage (%)** - Percentage of rated torque (20 Nm)

### Color-coded Load Indicators

- **Green** (<30%) - Light load, normal operation
- **Yellow** (30-70%) - Medium load, motor working
- **Red** (>70%) - High load, approaching limits

### Status Panel Example
```
Current Status:
  • Commanded: 100 RPM DISENGAGE (↓)
  • Actual: 98 RPM ✓
  • Torque: 8.2 Nm (41.0%)
  • Distance traveled: 15.47 mm
```

## Usage Scenarios

### 1. Normal Operation
- **Torque**: 10-40% (2-8 Nm)
- **Status**: Green to yellow
- **Meaning**: Motor moving freely with normal mechanical resistance

### 2. High Load / Resistance
- **Torque**: 50-80% (10-16 Nm)
- **Status**: Yellow to red
- **Meaning**: Significant mechanical resistance
- **Actions**: 
  - Check for binding or obstruction
  - Verify load is within specifications
  - Reduce velocity if needed

### 3. Stalling / Overload
- **Torque**: >80% (>16 Nm)
- **Status**: Red
- **Meaning**: Motor struggling, may stall
- **Actions**:
  - Stop immediately to prevent damage
  - Investigate cause of excessive load
  - Check mechanical alignment

### 4. No Load / Free Running
- **Torque**: <10% (<2 Nm)
- **Status**: Green
- **Meaning**: Very light load, possibly disconnected
- **Check**: Mechanical coupling is engaged

## Technical Implementation

### Backend (velocity_control.py)

Added torque readback function:
```python
def get_actual_torque(accessor, dev_handle) -> int:
    """Get actual motor torque in per mille (‰) of rated torque."""
    torque = rnum(accessor, dev_handle, OD_TORQUE_ACTUAL, signed=True)
    return torque
```

### TCP Protocol

New commands:
- **`GET_TORQUE`** - Returns: `TORQUE:500` (torque in ‰)
- **`GET_STATUS`** - Returns: `STATUS:100,500` (velocity,torque)

The Dashboard uses `GET_STATUS` to fetch both velocity and torque in a single query for efficiency.

### Frontend (Dashboard.py)

The `VelocityControl` widget:
- Polls motor status every second
- Converts raw torque (‰) to Nm: `torque_nm = (raw / 1000.0) * 20.0`
- Converts to percentage: `torque_percent = raw / 10.0`
- Applies color coding based on load level
- Updates display with all status information

## Torque Calculation at Spindle

To calculate actual force at the spindle output:

```
Spindle Torque = Motor Torque × Gearbox Ratio
Spindle Torque = 20 Nm × 80 = 1600 Nm (rated)

Axial Force = Spindle Torque / (Lead / 2π)
            = 1600 Nm / (0.004 m / 2π)
            = 1600 / 0.000637
            = 2,512,000 N
            = 2,512 kN
            = 251.2 tons (rated force)
```

**At 100% motor torque (20 Nm), the spindle can theoretically generate ~251 tons of axial force.**

## Safety Considerations

### Maximum Load Warnings
- **70-100%**: Yellow warning - approaching maximum rated torque
- **>100%**: Red warning - exceeding rated torque (motor can handle up to 160% briefly)

### Monitoring Recommendations
1. **During engagement**: Monitor torque increase to detect when spindle contacts workpiece
2. **During operation**: Ensure torque stays below 80% for continuous operation
3. **Stall detection**: If torque >90% and velocity drops to 0, motor has stalled

### Emergency Stop Conditions
Consider stopping motor automatically if:
- Torque >150% for more than 1 second
- Velocity drops to 0 while torque >70%
- Rapid torque spikes (may indicate mechanical shock)

## Troubleshooting

### Torque Shows 0
- Motor might be disconnected or in wrong mode
- Check that motor is in Profile Velocity mode (mode 3)
- Verify motor is receiving commands

### Torque Fluctuates Wildly
- Mechanical vibration or binding
- Check alignment of spindle and gearbox
- Inspect for loose connections

### Torque Higher Than Expected
- Excessive friction in mechanism
- Misalignment causing binding
- Need for lubrication
- Mechanical obstruction

### Torque Lower Than Expected
- Motor not fully engaged
- Slipping coupling
- Load not properly applied

## Data Logging Recommendations

For quality control and diagnostics, consider logging:
- Timestamp
- Commanded velocity (RPM)
- Actual velocity (RPM)
- Torque (Nm and %)
- Distance traveled (mm)
- Direction (engage/disengage)

This data can help:
- Detect wear patterns over time
- Identify process variations
- Troubleshoot mechanical issues
- Optimize operation parameters

## Future Enhancements

Possible additions:
1. **Torque limits** - User-configurable maximum torque alert
2. **Automatic stall detection** - Stop motor if torque too high
3. **Torque-based positioning** - Stop at specific torque level (force control)
4. **Historical torque plot** - Graph torque over time
5. **Peak torque tracking** - Record maximum torque per cycle
6. **Force calculation** - Convert torque to spindle force in kN

## Related Files

- `velocity_control.py` - Torque readback implementation
- `Dashboard.py` - Torque display in UI
- `nanotecMotorSpecs.md` - Motor specifications
- `VELOCITY_FEEDBACK.md` - Velocity monitoring documentation
- `DISTANCE_TRACKING.md` - Distance calculation details
