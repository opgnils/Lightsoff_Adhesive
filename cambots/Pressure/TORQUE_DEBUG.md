# Torque Reading Investigation

## Issue
When physically clamping the motor (stalling it), torque reading shows only 0.7 Nm (3.5%), which seems too low.

## Potential Causes

### 1. Data Type Issue ✅ FIXED
The original code was reading 0x6077 as 32-bit when it's actually 16-bit.
- **Fixed**: Added `bitlen` parameter to `rnum()` function
- **Changed**: `rnum(accessor, dev_handle, OD_TORQUE_ACTUAL, signed=True, bitlen=16)`

### 2. Units Might Be Different
CANopen standard for 0x6077:
- **Standard units**: Per mille (‰) of rated torque
- **Our motor**: Rated torque = 20 Nm
- **Expected**: 1000 = 100% = 20 Nm

**But** some motors use different units:
- Motor current in mA instead of torque
- Torque in different scaling (0-10000 instead of 0-1000)
- Absolute values in mNm (milliNewton-meters)

### 3. Object Might Not Be Supported
Like with 0x606C (velocity actual), the firmware might not support 0x6077:
- Returns 0 or small fixed value
- Not implemented in this firmware version
- Needs different configuration

### 4. Alternative Objects to Try

| Object | Name | Description |
|--------|------|-------------|
| 0x6077 | Torque actual value | Standard torque feedback |
| 0x6078 | Current actual value | Motor current (can indicate load) |
| 0x2038 | Absolute current | Nanotec-specific current |
| 0x2037 | Motor load | Nanotec-specific load percentage |
| 0x6071 | Target torque | What torque is commanded |
| 0x6072 | Max torque | Maximum allowed torque |

## Testing Steps

### 1. Run test_torque.py
```bash
python3 test_torque.py
```

This will show:
- Raw value from 0x6077
- Interpreted as 16-bit signed
- Interpreted as 32-bit signed
- Try to read 0x6078 (current)

### 2. Expected Results

**If motor is stalled at 50 RPM:**
- Torque should show 500-800 ‰ (50-80%)
- Current should be high (near maximum)

**If reading 35 ‰ (3.5% = 0.7 Nm):**
- Either wrong scaling factor
- Or object not supported
- Or reading different value

### 3. Possible Fixes

**Option A: Different scaling**
```python
# If actual scale is 0-10000 instead of 0-1000
torque_nm = (raw_value / 10000.0) * 20.0
```

**Option B: Use current instead**
```python
# Read 0x6078 (current actual value)
# High current = high torque (approximate)
current_ma = read_current()
torque_estimate = (current_ma / max_current) * rated_torque
```

**Option C: Use Nanotec-specific objects**
```python
# Try 0x2037 (motor load percentage)
load_percent = read_nanotec_load()
```

## Diagnostic Questions

1. **What's the raw hex value?**
   - If it's always 0x0023 (35), might be scaled differently
   - If it changes proportionally with load, scaling is wrong

2. **Does it change when you apply load?**
   - If NO → Object not supported, try alternatives
   - If YES → Scaling factor wrong

3. **What happens at higher loads?**
   - If it maxes out at 100-200, scale is 0-10000
   - If it goes negative when reverse, sign handling works

## Next Steps

1. Run `test_torque.py` while applying different loads
2. Note the RAW values and how they change
3. Calculate correct scaling factor
4. Update conversion formula in Dashboard

## Temporary Workaround

If torque reading doesn't work, we can:
1. Remove torque display temporarily
2. Add it back when we find working object
3. Use velocity tracking as primary indicator

Or estimate torque from velocity error:
```python
# Poor man's torque estimation
vel_error = commanded_vel - actual_vel
estimated_torque = vel_error * load_coefficient
```
