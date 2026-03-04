# Torque Reading - All Objects Test

## Problem
Torque stays at 0.0 even when motor is squeezed hard (10-20 Nm applied).

## Hypothesis
We might be reading the wrong CANopen object, or the objects we're trying (0x6074, 0x6077) don't contain real-time load data on this motor.

## Solution Implemented
Updated `get_actual_torque()` to try **ALL** possible torque-related objects in this order:

1. **0x6078 (Current Actual)** ← **TRY THIS FIRST**
   - Motor current is directly proportional to torque
   - Most likely to show real-time load
   - Works on most motors even if torque objects don't

2. **0x6074 (Torque Demand)**
   - Internal controller setpoint
   - Previously we thought this would work

3. **0x6077 (Torque Actual)**
   - Encoder-based feedback
   - May not be implemented

4. **0x6071 (Target Torque)**
   - Commanded value (last resort)

## Testing Steps

### Step 1: Restart Velocity Listener
```bash
cd /home/icd-wmpc06/Documents/Lightsoff_Adhesive/cambots/Pressure
python3 velocity_control.py
```

### Step 2: Start Motor from Dashboard
- Open Dashboard
- Go to Pressure → Velocity Control
- Set velocity to 50-100 RPM
- Watch the terminal output

### Step 3: Observe Terminal Debug Messages
You should see one of these:

**GOOD - Current works:**
```
[DEBUG] Read 0x6078 (current actual): 150 ‰ (15.0%)
```

**GOOD - Torque demand works:**
```
[DEBUG] 0x6078 failed: ...
[DEBUG] Read 0x6074 (torque demand): 150 ‰ (15.0%)
```

**BAD - All failed:**
```
[DEBUG] 0x6078 failed: ...
[DEBUG] 0x6074 failed: ...
[DEBUG] 0x6077 failed: ...
[DEBUG] 0x6071 failed: ...
[ERROR] All torque read methods failed, returning 0
```

### Step 4: Test Under Load
While motor running, try these:
1. **Free running**: Should show ~50-200 ‰ (1-4 Nm, 5-20%)
2. **Hand resistance**: Should show ~300-500 ‰ (6-10 Nm, 30-50%)
3. **Hard squeeze/clamp**: Should show ~800-1000 ‰ (16-20 Nm, 80-100%)

## Expected Results

### If Current (0x6078) Works:
- You'll see real-time load changes in the Dashboard
- Terminal will show: `[DEBUG] Read 0x6078 (current actual): XXX ‰`
- Load indicator will change color (green → yellow → red) as you apply force

### If Nothing Works:
Possible reasons:
1. Motor is in wrong mode (not Profile Velocity mode 3)
2. Objects don't exist on this motor firmware
3. Need to read as 32-bit instead of 16-bit
4. Need unsigned instead of signed conversion
5. Motor doesn't support real-time torque/current readout in velocity mode

## Alternative: Run Full Diagnostic
If you have access to the motor computer directly, run:
```bash
cd /home/icd-wmpc06/Documents/Lightsoff_Adhesive/cambots/Pressure
python3 test_torque.py
```

This will show you ALL torque objects with raw values, signed 16-bit, and signed 32-bit interpretations.

## What to Share
If still showing 0.0, please share:
1. Terminal output from velocity_control.py showing the [DEBUG] messages
2. What velocity the motor is running at
3. Whether velocity feedback works (shows actual RPM)
4. Any error messages from the terminal

This will tell us:
- Which objects exist on your motor
- Which ones return valid data
- What values they're actually returning
- Whether we need different bit lengths or signed/unsigned conversion

## Quick Reference: CANopen Objects

| Object | Name | Description | Likely to Work? |
|--------|------|-------------|-----------------|
| 0x6078 | Current Actual | Motor current (proxy for torque) | ⭐ **HIGH** |
| 0x6074 | Torque Demand | Controller internal setpoint | Medium |
| 0x6077 | Torque Actual | Encoder-based feedback | Low |
| 0x6071 | Target Torque | Commanded value | Very Low |

The current (0x6078) is the most universal - if the motor is working, it MUST have current flowing, so this object should exist and update in real-time.
