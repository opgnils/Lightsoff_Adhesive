# Current/Torque Object Fix - Added Nanotec-Specific Objects

## Problem
- 0x6078 showed "---" (not working)
- Only one torque value changed slightly (0.4 to 0.7 Nm)
- Values not visible in Dashboard status bar

## Root Cause
**0x6078 is NOT actual current in DS402!**
- 0x6078 = **Rated Current** (configuration parameter, doesn't change)
- We need Nanotec-specific current objects

## Solution - Added Nanotec Objects

### New Objects Added:
1. **0x221C** - Nanotec Actual Current (mA) ⭐ **MOST LIKELY**
2. **0x2030** - Nanotec Motor Current (mA) ⭐ **LIKELY**
3. **0x6078** - DS402 Current (may be rated, not actual)
4. **0x6074** - Torque Demand (‰)
5. **0x6077** - Torque Actual (‰)
6. **0x6071** - Target Torque (‰)

### Priority Order:
```
1. 0x221C (Nanotec Current in mA) ← Try FIRST
2. 0x2030 (Motor Current in mA)   ← Try SECOND
3. 0x6078 (DS402 Current)
4. 0x6074 (Torque Demand)
5. 0x6077 (Torque Actual)
6. 0x6071 (Target Torque)
```

## New Dashboard Display

### Operation View shows 6 values:

```
Current Status:
  • Commanded: 100 RPM DISENGAGE (↓)
  • Actual: 100 RPM ✓
  • Distance: 123.45 mm

Current Readings (mA):
  • 0x221C (Nanotec):       500mA (~5.0Nm)    ← Should change with load!
  • 0x2030 (Motor):         450mA (~4.5Nm)    ← Should change with load!

Torque Readings (‰):
  • 0x6078 (DS402):         ---               ← May not work
  • 0x6074 (Demand):        0.7Nm (3.5%)      ← Probably constant
  • 0x6077 (Actual):        ---               ← Doesn't exist
  • 0x6071 (Target):        0.0Nm (0.0%)      ← Zero
```

### Status Bar (bottom of screen):
```
Vel: 100RPM | Current: 500mA | Dist: 123.5mm
```

## Color Coding

### Current (mA):
- **Green**: < 600 mA (light load)
- **Yellow**: 600-1200 mA (medium load)
- **Red**: > 1200 mA (high load)
- **Gray "---"**: Object doesn't exist/failed

### Torque (‰):
- **Green**: < 30% (0-6 Nm)
- **Yellow**: 30-70% (6-14 Nm)
- **Red**: > 70% (14-20 Nm)

## Testing Steps

1. **Restart velocity listener:**
   ```bash
   cd /home/icd-wmpc06/Documents/Lightsoff_Adhesive/cambots/Pressure
   python3 velocity_control.py
   ```

2. **Restart Dashboard:**
   ```bash
   cd /home/icd-wmpc06/Documents/Lightsoff_Adhesive/base/programs
   python3 Dashboard.py
   ```

3. **Go to Pressure → Velocity Control**

4. **Set motor to 100 RPM**

5. **Watch for:**
   - **Current Readings section** - Should show mA values
   - **Status bar at bottom** - Should show current/torque
   - **Terminal** - Should show which objects work

6. **Squeeze motor and observe:**
   - Which current value increases? → That's the one!
   - Free running: ~200-400 mA
   - Hand resistance: ~600-1000 mA
   - Hard squeeze: ~1200-2000 mA

## Expected Terminal Output

```
[DEBUG] ✗ 0x6078 (Current DS402): Object does not exist
[DEBUG] ✓ 0x221C (Nanotec Current): 350 mA (350mA)     ← WORKING!
[DEBUG] ✓ 0x2030 (Motor Current): 320 mA               ← WORKING!
[DEBUG] ✓ 0x6074 (Torque Demand): 35 ‰ (3.5%)
[DEBUG] ✗ 0x6077 (Torque Actual): Object does not exist
[DEBUG] ✓ 0x6071 (Target Torque): 0 ‰ (0.0%)
Sent status - Vel:100 RPM | 0x6078=X 0x221C=350 0x2030=320 0x6074=35 0x6077=X 0x6071=0
```

## What to Look For

### 1. In Dashboard - Current Readings:
- **0x221C or 0x2030 should show mA values** (not "---")
- **Values should CHANGE when you squeeze**
- **Free running**: 200-400 mA
- **Squeezed**: 1000-2000 mA

### 2. In Dashboard - Status Bar (bottom):
Look for: `Vel: 100RPM | Current: 350mA | Dist: 123.5mm`

### 3. In Terminal:
- See which objects have ✓ (working)
- See which objects have ✗ (failed)
- Values printed after "Sent status"

## If Current Values Work

When you squeeze the motor:
```
Before squeeze:
  • 0x221C (Nanotec):       250mA (~2.5Nm)    [Green]

During squeeze:
  • 0x221C (Nanotec):      1500mA (~15.0Nm)   [RED]    ← CHANGES!
```

**→ This is the object to use for torque monitoring!**

## If Still Nothing Works

Possible reasons:
1. Motor not in correct operating mode
2. Current limiting is active (motor can't draw more current)
3. Objects are read-only configuration values
4. Need different CANopen profile objects

**Next step:** Check Nanotec motor manual for actual current monitoring object

## Quick Reference: Nanotec Objects

According to Nanotec documentation, these objects are common:
- **0x221C**: Actual current value (most motors)
- **0x2030**: Motor current (some models)
- **0x230A**: Temperature (for diagnostics)
- **0x2310**: Supply voltage (for diagnostics)

We're now trying the actual current objects - one of these should work!
