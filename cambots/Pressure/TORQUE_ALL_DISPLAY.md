# Torque Diagnostic Display - All Objects Visible

## Changes Made

### 1. velocity_control.py
**New function `get_all_torque_values()`:**
- Reads ALL 4 torque objects every time
- Returns dict with all values (or None if failed)
- Shows ✓ or ✗ for each object in terminal

**Updated `get_actual_torque()`:**
- Now calls `get_all_torque_values()` first
- Returns best available value from the results

**Updated GET_STATUS response format:**
```
STATUS:velocity,t6078,t6074,t6077,t6071
```
- Example: `STATUS:50,150,35,X,0`
  - 50 RPM velocity
  - 0x6078 = 150 ‰ (working!)
  - 0x6074 = 35 ‰ (working!)
  - 0x6077 = X (failed)
  - 0x6071 = 0 (working)

### 2. Dashboard.py
**Display now shows ALL 4 torque values:**

```
Current Status:
  • Commanded: 50 RPM DISENGAGE (↓)
  • Actual: 50 RPM ✓
  • Distance: 123.45 mm

Torque Readings:
  • 0x6078 (Current):       3.0Nm (15.0%)    ← Green/Yellow/Red
  • 0x6074 (Demand):        0.7Nm ( 3.5%)    ← Shows all values!
  • 0x6077 (Actual):        ---              ← Failed to read
  • 0x6071 (Target):        0.0Nm ( 0.0%)    ← Zero value
```

**Color coding:**
- **Green**: < 30% load (light)
- **Yellow**: 30-70% load (medium)
- **Red**: > 70% load (high)
- **Gray "---"**: Failed to read (object doesn't exist or error)

## What You'll See

### Terminal Output (velocity_control.py)
Every time Dashboard queries status, you'll see:
```
[DEBUG] ✓ 0x6078 (Current): 150 ‰ (15.0%)
[DEBUG] ✓ 0x6074 (Torque Demand): 35 ‰ (3.5%)
[DEBUG] ✗ 0x6077 (Torque Actual): readNumber(0x6077:0x00) failed: Object does not exist
[DEBUG] ✓ 0x6071 (Target Torque): 0 ‰ (0.0%)
Sent status - Vel:50 RPM, Torques: 0x6078=150 0x6074=35 0x6077=X 0x6071=0
```

### Dashboard Display
You'll see 4 lines showing ALL torque objects:

**When motor is free-running (low load):**
```
Torque Readings:
  • 0x6078 (Current):       2.0Nm (10.0%)    [Green]
  • 0x6074 (Demand):        0.7Nm ( 3.5%)    [Green]
  • 0x6077 (Actual):        ---              [Gray]
  • 0x6071 (Target):        0.0Nm ( 0.0%)    [Green]
```

**When you squeeze the motor (high load):**
```
Torque Readings:
  • 0x6078 (Current):      16.0Nm (80.0%)    [Red]
  • 0x6074 (Demand):        0.7Nm ( 3.5%)    [Green] ← Not changing!
  • 0x6077 (Actual):        ---              [Gray]  ← Not working
  • 0x6071 (Target):        0.0Nm ( 0.0%)    [Green] ← Not changing!
```

**This will IMMEDIATELY show which object responds to load!**

## Testing Steps

1. **Restart velocity listener:**
   ```bash
   cd /home/icd-wmpc06/Documents/Lightsoff_Adhesive/cambots/Pressure
   python3 velocity_control.py
   ```

2. **Start Dashboard:**
   ```bash
   cd /home/icd-wmpc06/Documents/Lightsoff_Adhesive/base/programs
   python3 Dashboard.py
   ```

3. **Go to Pressure → Velocity Control**

4. **Set motor to 50-100 RPM**

5. **Watch the "Torque Readings" section - you should see 4 lines:**
   - Some showing values (green/yellow/red)
   - Some showing "---" (gray) if they don't work

6. **Squeeze the motor while watching:**
   - Which values change? → Those objects work!
   - Which stay constant? → Those objects don't reflect load
   - Which show "---"? → Those objects don't exist

## Expected Results

### Best Case - Current (0x6078) responds to load:
```
When squeezed:
  • 0x6078 (Current):      16.0Nm (80.0%)    [RED] ← CHANGES!
  • 0x6074 (Demand):        0.7Nm ( 3.5%)    [Green] ← stays same
  • 0x6077 (Actual):        ---              [Gray]
  • 0x6071 (Target):        0.0Nm ( 0.0%)    [Green] ← stays same
```
→ **Use 0x6078 for torque monitoring!**

### If nothing responds to load:
All values stay constant even when squeezing:
```
  • 0x6078 (Current):       2.0Nm (10.0%)    [Green] ← NO CHANGE
  • 0x6074 (Demand):        0.7Nm ( 3.5%)    [Green] ← NO CHANGE
  • 0x6077 (Actual):        ---              [Gray]
  • 0x6071 (Target):        0.0Nm ( 0.0%)    [Green] ← NO CHANGE
```
→ Need different approach (maybe wrong mode, wrong bit length, etc.)

## Advantages of This Display

1. **See all objects at once** - no guessing which one works
2. **Real-time visual feedback** - colors change as values change
3. **Clear failure indication** - "---" shows what doesn't work
4. **Side-by-side comparison** - immediately see which value responds to load
5. **Terminal debug** - still shows why each object succeeded or failed

## What to Share

Please share:
1. **Screenshot of Dashboard** showing the 4 torque lines
2. **Tell us:** Which line changes when you squeeze the motor?
3. **Terminal output** showing the [DEBUG] messages

This will definitively show which CANopen object works for torque monitoring!

## Quick Reference

| Object | Name | What it measures | Updates with load? |
|--------|------|------------------|-------------------|
| 0x6078 | Current | Motor winding current | Should: Yes ⭐ |
| 0x6074 | Demand | Controller internal setpoint | Maybe |
| 0x6077 | Actual | Encoder-based torque | Rarely |
| 0x6071 | Target | Commanded torque limit | No (we don't set it) |

The one that **changes** when you squeeze is the one we should use!
