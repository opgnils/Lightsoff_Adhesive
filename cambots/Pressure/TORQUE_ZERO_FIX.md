# Torque Reading Fix - Staying at 0.0 Issue

## Problem
Torque reading was staying at 0.0 Nm and not updating, even though the motor was running and under load.

## Root Cause
The `get_actual_torque()` function had nested try-except blocks that were catching exceptions incorrectly. The outer try-except was catching the inner exception and then trying to execute code that would fail, causing the function to return 0 every time.

**Old problematic code structure:**
```python
def get_actual_torque(...):
    try:
        # First try 0x6074
        try:
            torque = rnum(...)  # If this fails, inner exception
            return torque
        except Exception as e:
            print(f"0x6074 not available: {e}")
        
        # Fallback to 0x6077
        torque = rnum(...)  # This line is OUTSIDE the inner try!
        return torque
        
    except Exception as e:  # This catches EVERYTHING
        print(f"Failed to read torque: {e}")
        return 0
```

**Issue:** When 0x6074 fails, the code tries to execute `torque = rnum(accessor, dev_handle, OD_TORQUE_ACTUAL, ...)` which is OUTSIDE any try block but INSIDE the outer try-except. If this also fails, the outer except catches it and returns 0 immediately.

## Solution
Restructured the function to have separate try-except blocks for each read attempt:

```python
def get_actual_torque(...):
    # First try 0x6074
    try:
        torque = rnum(accessor, dev_handle, OD_TORQUE_DEMAND, signed=True, bitlen=16)
        print(f"[DEBUG] Read 0x6074 (torque demand): {torque} ‰")
        return torque
    except Exception as e:
        print(f"[DEBUG] 0x6074 failed: {e}")
    
    # Fallback to 0x6077
    try:
        torque = rnum(accessor, dev_handle, OD_TORQUE_ACTUAL, signed=True, bitlen=16)
        print(f"[DEBUG] Read 0x6077 (torque actual): {torque} ‰")
        return torque
    except Exception as e:
        print(f"[DEBUG] 0x6077 failed: {e}")
    
    # Both failed
    print(f"[ERROR] All torque read methods failed, returning 0")
    return 0
```

## Changes Made

### 1. Fixed `velocity_control.py`
- Removed nested try-except structure
- Each CANopen object read now has its own try-except
- Clear error messages for each failed read attempt
- Explicit return 0 with error message if all methods fail

### 2. Created `test_torque_simple.py`
Simple diagnostic tool that:
- Connects to motor directly
- Reads both torque objects (0x6074 and 0x6077) every second
- Displays results in real-time with velocity for context
- Shows which object works and which fails

## Testing Steps

1. **Restart velocity listener** (with the fix):
   ```bash
   cd /home/icd-wmpc06/Documents/Lightsoff_Adhesive/cambots/Pressure
   python3 velocity_control.py
   ```

2. **Watch the debug output** - you should now see messages like:
   ```
   [DEBUG] Read 0x6074 (torque demand): 150 ‰ (15.0%)
   ```
   or
   ```
   [DEBUG] 0x6074 failed: readNumber(0x6074:0x00) failed: ...
   [DEBUG] Read 0x6077 (torque actual): 35 ‰ (3.5%)
   ```

3. **Alternative: Use simple test** (doesn't require TCP listener):
   ```bash
   python3 test_torque_simple.py
   ```
   This will show torque readings every second directly from the motor.

4. **In Dashboard**, observe torque display - should now update in real-time

## What You Should See

### If working correctly:
- Free running motor: ~50-200 ‰ (1-4 Nm, 5-20%)
- Under hand resistance: ~300-500 ‰ (6-10 Nm, 30-50%)  
- Stalled/clamped: ~800-1000 ‰ (16-20 Nm, 80-100%)

### Debug messages in terminal:
The listener will print which object it's reading from:
- `[DEBUG] Read 0x6074 (torque demand): XXX ‰ (Y.Y%)` - GOOD
- `[DEBUG] 0x6074 failed: ...` followed by `[DEBUG] Read 0x6077 (torque actual): XXX ‰` - FALLBACK
- `[ERROR] All torque read methods failed, returning 0` - PROBLEM

## Why This Matters
The nested try-except was silently failing and always returning 0 because:
1. Inner try fails for 0x6074 → inner except prints message
2. Code continues to read 0x6077 (outside inner try)
3. 0x6077 read also fails → outer except catches this
4. Returns 0 immediately without proper debugging info

Now each read is independent, and we can see exactly which object works and which doesn't.

## Expected Outcome
- Torque should now update in real-time (every 1 second in Dashboard)
- Debug messages clearly show which CANopen object is being used
- If both objects fail, you'll see clear error message explaining what happened

## If Still Showing 0.0
Run the simple test script to diagnose:
```bash
python3 test_torque_simple.py
```

This will show you:
1. Whether motor is connected properly
2. Which torque objects return valid data
3. What error messages you get if reads fail
4. Actual torque values being returned

Share the output if still having issues!
