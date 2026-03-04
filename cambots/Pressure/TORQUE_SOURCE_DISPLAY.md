# Torque Display with Source Object

## Changes Made

### 1. velocity_control.py
**Function `get_actual_torque()` now returns a tuple:**
- Returns: `(torque_value, source_object)`
- Example: `(150, "0x6078")` means 150 ‰ from Current Actual object

**Updated debug output with checkmarks:**
- ✓ Success: `[DEBUG] ✓ Read 0x6078 (current actual): 150 ‰ (15.0%)`
- ✗ Failure: `[DEBUG] ✗ 0x6078 failed: readNumber(0x6078:0x00) failed: ...`

**TCP Response format updated:**
- `GET_STATUS` now returns: `STATUS:velocity,torque,source`
- Example: `STATUS:50,150,0x6078`
  - 50 RPM velocity
  - 150 ‰ torque
  - Read from 0x6078 (Current Actual)

### 2. Dashboard.py
**Added torque source tracking:**
- New field: `self.torque_source` stores which object worked
- Parses 3rd value from GET_STATUS response

**Updated display to show source:**
```
• Torque: 3.0 Nm (15.0%) [Current]
```

**Source object display names:**
- `0x6078` → "Current" (motor current, best indicator)
- `0x6074` → "Torque Demand" (controller setpoint)
- `0x6077` → "Torque Actual" (encoder feedback)
- `0x6071` → "Target Torque" (commanded value)
- `NONE` → "❌ NO DATA" (all reads failed)

## What You'll See

### Terminal Output (velocity_control.py)
When motor is running, you'll see which object works:
```
[DEBUG] ✓ Read 0x6078 (current actual): 150 ‰ (15.0%)
Sent status - Velocity: 50 RPM, Torque: 150 ‰ (from 0x6078)
```

Or if current doesn't work, it tries next:
```
[DEBUG] ✗ 0x6078 failed: readNumber(0x6078:0x00) failed: Object does not exist
[DEBUG] ✓ Read 0x6074 (torque demand): 35 ‰ (3.5%)
Sent status - Velocity: 50 RPM, Torque: 35 ‰ (from 0x6074)
```

### Dashboard Display
Now shows which object is providing the torque reading:
```
Current Status:
  • Commanded: 50 RPM DISENGAGE (↓)
  • Actual: 50 RPM ✓
  • Torque: 3.0 Nm (15.0%) [Current]      ← Shows source!
  • Distance traveled: 123.45 mm
```

If torque reads fail completely:
```
  • Torque: 0.0 Nm (0.0%) [❌ NO DATA]
```

## Testing

1. **Start velocity listener:**
   ```bash
   cd /home/icd-wmpc06/Documents/Lightsoff_Adhesive/cambots/Pressure
   python3 velocity_control.py
   ```

2. **Open Dashboard and start motor at 50-100 RPM**

3. **Watch BOTH:**
   - **Terminal**: See debug messages showing which object works
   - **Dashboard**: See torque value and source (e.g. "[Current]")

4. **Apply load to motor:**
   - Free running: Should show low torque (50-200 ‰, 1-4 Nm)
   - Hand resistance: Should show medium torque (300-500 ‰, 6-10 Nm)
   - Hard squeeze: Should show high torque (800-1000 ‰, 16-20 Nm)

## Expected Results

### Best case - Current (0x6078) works:
- Terminal: `[DEBUG] ✓ Read 0x6078 (current actual): XXX ‰`
- Dashboard: `Torque: X.X Nm (XX.X%) [Current]`
- **Torque changes in real-time as you apply load** ← THIS IS WHAT WE WANT!

### If Current doesn't work - Torque Demand (0x6074):
- Terminal: `[DEBUG] ✗ 0x6078 failed` then `[DEBUG] ✓ Read 0x6074`
- Dashboard: `Torque: X.X Nm (XX.X%) [Torque Demand]`
- May show constant value or not respond to load changes

### Worst case - Nothing works:
- Terminal: Multiple `[DEBUG] ✗ ...` then `[ERROR] All torque read methods failed`
- Dashboard: `Torque: 0.0 Nm (0.0%) [❌ NO DATA]`
- Need to investigate motor mode or CANopen configuration

## Troubleshooting

If you see `[❌ NO DATA]` in Dashboard:
1. Check terminal for debug messages showing WHY each object failed
2. Motor might need to be in specific mode (Profile Velocity mode 3)
3. May need to read as 32-bit instead of 16-bit
4. May need unsigned instead of signed conversion

## Share This Info
Please share screenshot/photo showing:
1. Dashboard display with torque line (shows source in brackets)
2. Terminal output showing the `[DEBUG]` messages

This will tell us exactly which object works on your motor!
