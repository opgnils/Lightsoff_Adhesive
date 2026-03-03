# Dashboard Adhesive Profile Selection - User Guide

## Overview

The adhesive profile execution has been redesigned to work **directly within the Dashboard** with an interactive dropdown menu, similar to how it works in App.py. No external scripts needed!

## How It Works

### Step 1: Discover Robots
1. Launch Dashboard: `python3 Dashboard.py`
2. Navigate to: **1 Connect** → Click to expand
3. Select: **Discover robots**
4. Devices will be discovered and shown in the Device panel (bottom-left)

### Step 2: Access Adhesive Control
1. Navigate to: **5 Adhesive Robot** → Click to expand
2. You'll see 4 options:
   - Manual control
   - **Run profile** ← This is what we want
   - View history
   - Emergency stop

### Step 3: Select Profile (NEW!)
1. Click on: **Run profile**
2. The menu will automatically expand to show a **dropdown list** of all available CSV profiles:
   ```
   ▼ Run profile
       ○ adh_test_profile.csv
       ○ adh_test_nonsync.csv
       ○ fast_rampUp.csv
   ```
3. The Operation View (right side) will show:
   - List of available profiles
   - Number of connected devices
   - Profile format information
   - Instructions

### Step 4: Execute Profile
1. Click on any profile name (e.g., **○ fast_rampUp.csv**)
2. Profile execution starts **immediately** and automatically:
   - ✅ Adhesive listeners are started on all devices
   - ✅ Profile CSV is loaded and validated
   - ✅ Commands are sent at scheduled times
   - ✅ Progress is shown in the Status Log (bottom-right)
   - ✅ Final safety stop (0,0,0) is sent when complete

### Step 5: Monitor Progress
Watch the **Status Log** (bottom-right panel) for real-time updates:
```
[INFO] Starting profile: fast_rampUp.csv
[SUCCESS] Listener ready on robot1
[SUCCESS] Listener ready on robot2
[SUCCESS] Loaded 12 steps
[SUCCESS] [1/12] t=0.0s -> 0,0,0 ✓
[SUCCESS] [2/12] t=2.0s -> 1000,500,500 ✓
[SUCCESS] [3/12] t=5.0s -> 1500,750,750 ✓
...
[INFO] Profile complete. Sending STOP (0,0,0)...
[SUCCESS] Profile execution completed successfully
```

The **Operation View** (right panel) shows:
- Profile name
- Number of steps
- Execution status
- "Check status log for detailed progress"

## Menu Structure

```
Dashboard
├── 1  Connect
│   ├── Discover robots
│   ├── Select robots
│   └── Update code
├── 2  Component
│   ├── Select component
│   └── Change component
├── 3  Tracking
│   └── Combined tracking
├── 4  Assembly Robot
│   ├── Engage clamps
│   └── Disengage clamps
├── 5  Adhesive Robot
│   ├── Manual control
│   ├── ▶ Run profile  ←── Click to expand
│   │   ├── ○ adh_test_profile.csv  ←── Click to run
│   │   ├── ○ adh_test_nonsync.csv
│   │   └── ○ fast_rampUp.csv
│   ├── View history
│   └── Emergency stop
└── 6  Crane
    ├── Position crane
    ├── Home position
    └── Emergency stop
```

## Features

### ✅ Integrated Dropdown
- Just like App.py's Bullet menu
- Profiles appear as submenu items
- Click to execute immediately
- No need to exit dashboard or run external scripts

### ✅ Automatic Execution
- Listener startup handled automatically
- CSV parsing and validation
- Timed command execution
- Progress monitoring in real-time
- Automatic safety stop at completion

### ✅ Full Monitoring
- Status log shows every command sent
- Timestamps on all operations
- Color-coded status (green=success, red=error, yellow=warning)
- Operation view shows execution state

### ✅ Emergency Stop Available
- Use **Emergency stop** menu item at any time
- Sends 0,0,0 command 3 times for redundancy
- Works even during profile execution

## Profile Format

CSV files in `base/programs/adhesive_profiles/` with format:

```csv
# time, motor1_rpm, motor2_ul_s, motor3_ul_s
0.0,  0,    0,    0      # Start at rest
2.0,  1000, 500,  500    # Ramp up at 2 seconds
10.0, 2000, 1000, 1000   # Full speed at 10 seconds
15.0, 0,    0,    0      # Stop at 15 seconds
```

## Comparison: Old vs New

### OLD Way (External Script)
1. Open Dashboard
2. Navigate to Run profile
3. See list of profiles
4. **Exit dashboard**
5. Run: `python3 run_adhesive_profile.py adhesive_profiles/profile.csv`
6. Monitor in separate terminal
7. Re-open dashboard when done

### NEW Way (Integrated Dropdown) ✅
1. Open Dashboard
2. Navigate to Run profile (menu expands automatically)
3. **Click on profile name from dropdown**
4. **Execution starts immediately**
5. Monitor in Status Log panel
6. Stay in dashboard throughout

## Technical Details

### What Happens When You Click a Profile:

1. **Menu Selection** → `profile:adhesive:filename.csv` event triggered
2. **Handler** → `_do_run_profile(profile_name)` method called
3. **Background Thread** → Profile execution starts in daemon thread
4. **Listener Check** → `ensure_adhesive_listener_running()` for each device
5. **CSV Loading** → Parse profile, validate format, sort by time
6. **Execution Loop**:
   - For each step: wait until scheduled time
   - Send TCP command: `motor1,motor2,motor3` to port 5001
   - Log result in Status Log
7. **Completion** → Send 0,0,0 three times, log success

### Thread Safety
- Background execution in daemon thread
- UI updates via `call_from_thread()`
- Non-blocking operation (dashboard remains responsive)
- Can start other operations or emergency stop while profile runs

### Error Handling
- Missing profile: Error logged, operation view shows error
- Listener failure: Logged per device, execution aborts
- CSV parsing error: Logged, execution aborts
- TCP send failure: Logged per command, execution continues

## Example Session

```
Terminal 1:
$ cd /home/icd-wmpc06/Documents/Lightsoff_Adhesive/base/programs
$ python3 Dashboard.py

Dashboard:
┌─────────────┬──────────────────────────────────────┐
│ ▼ 5 Adhesive│ Executing: fast_rampUp.csv          │
│   • Manual  │                                      │
│   ▼ Run pro │ Profile: fast_rampUp.csv             │
│     ○ adh_  │ Steps: 12                            │
│     ○ fast_ │ Devices: 2                           │
│   • View    │                                      │
│   • Emerg   │ [✓] Executing...                     │
├─────────────┼──────────────────────────────────────┤
│ Devices:    │ Status Log:                          │
│ ● robot1    │ [12:34:56] [INFO] Starting profile   │
│ ● robot2    │ [12:34:57] [SUCCESS] Listener ready  │
└─────────────┴──────────────────────────────────────┘
```

## Troubleshooting

### Profiles Don't Appear in Dropdown
- **Cause**: No CSV files in `adhesive_profiles/` directory
- **Fix**: Add profile files to `base/programs/adhesive_profiles/`
- Click "Run profile" again to refresh

### Execution Doesn't Start
- **Check**: Status Log for error messages
- **Verify**: Devices are discovered and online (green ● in Device panel)
- **Try**: Discover robots again

### Commands Not Reaching Devices
- **Check**: Listener status in logs
- **Verify**: TCP port 5001 is accessible: `nc -zv hostname 5001`
- **Try**: Emergency stop, then retry profile

### Profile Stops Mid-Execution
- **Check**: Status Log for TCP errors
- **Cause**: Network issue or listener crash
- **Fix**: Restart listeners, run profile again

## Summary

The new adhesive profile interface:
- ✅ **Integrated dropdown menu** (like App.py)
- ✅ **One-click execution** (no external scripts)
- ✅ **Real-time monitoring** (Status Log)
- ✅ **Fully automatic** (listeners, execution, safety stop)
- ✅ **Dashboard stays responsive** (background threading)
- ✅ **Emergency stop ready** (anytime)

This is now the **primary way** to run adhesive profiles! The external script (`run_adhesive_profile.py`) is still available for standalone use but is no longer needed when using the Dashboard.
