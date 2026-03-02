# Dashboard vs App.py - Quick Reference

## Side-by-Side Comparison

| Feature | App.py (Old CLI) | Dashboard.py (New TUI) |
|---------|------------------|------------------------|
| **Layout** | Sequential screens | 4-panel split-screen |
| **Navigation** | Linear (forward/back) | Non-linear (jump anywhere) |
| **Device Status** | Hidden unless queried | Always visible in panel |
| **Status Messages** | Cleared on screen change | Persistent log with history |
| **Menu Style** | Bullet-list text menu | Expandable tree menu |
| **Context** | Lost on screen clear | All panels visible always |
| **Multi-tasking** | One operation at a time | Can monitor while operating |
| **Visual Feedback** | Text only | Color-coded + indicators |
| **Error Visibility** | Can be missed | Highlighted in log |
| **Terminal Clears** | Frequent (loses context) | Never (persistent UI) |

## Workflow Comparison

### Starting a Tracking Operation

#### App.py (Old Way)
```
1. Start app
2. [Screen] Device selection
   - Choose robots
   - Screen clears ❌
3. [Screen] Update code?
   - Make choice
   - Screen clears ❌
4. [Screen] Set component
   - Screen clears ❌
5. [Screen] Main menu
   - Select "Tracking"
   - Screen clears ❌
6. [Screen] Tracking submenu
   - Select "Combined"
   - Screen clears ❌
7. [Screen] Tracking runs
   - Can't see device status ❌
   - Can't see past events ❌
```

#### Dashboard.py (New Way)
```
1. Start dashboard
2. All panels visible ✅
   - See devices immediately ✅
   - See status log ✅
3. Click "1. Connect" → Expand
4. Click "Discover robots"
   - Results show in Operation View ✅
   - Devices panel updates ✅
   - Status log records event ✅
5. Click "5. Tracking" → Expand
6. Click "Combined tracking"
   - Tracking starts in Operation View ✅
   - Device status still visible ✅
   - All events logged ✅
   - Can switch to other menus anytime ✅
```

## Key Improvements

### 1. Persistent Context
- **Old**: Every menu selection clears the screen
- **New**: All information stays visible

### 2. Device Awareness
- **Old**: Can't see which devices are online during operations
- **New**: Device panel always shows status with ●/○ indicators

### 3. Event History
- **Old**: Print statements disappear on screen clear
- **New**: Timestamped log keeps all events

### 4. Navigation Freedom
- **Old**: Must complete operation or back out sequentially
- **New**: Jump between any sections anytime

### 5. Visual Hierarchy
- **Old**: Flat text menus
- **New**: Expandable tree menu (▶/▼)

### 6. Error Handling
- **Old**: Errors can scroll off screen
- **New**: Errors highlighted in red in status log

### 7. Multi-Operation Support
- **Old**: One thing at a time
- **New**: Monitor devices while configuring components

## When to Use Each

### Use App.py when:
- Running in extremely constrained environment
- Need absolute simplicity
- Scripting/automation (non-interactive)
- Debugging specific functions

### Use Dashboard.py when:
- Normal operations
- Need situational awareness
- Running multiple robots
- Need to see device status
- Want to review event history
- Professional presentation needed

## Feature Parity

| Feature | App.py | Dashboard.py |
|---------|--------|--------------|
| Device discovery | ✅ | ✅ |
| Device selection | ✅ | 🚧 (stub ready) |
| Code updates | ✅ | 🚧 (stub ready) |
| Component selection | ✅ | ✅ |
| Motor control | ✅ | 🚧 (stub ready) |
| Aruco tracking | ✅ | 🚧 (stub ready) |
| Hole tracking | ✅ | 🚧 (stub ready) |
| Combined tracking | ✅ | 🚧 (stub ready) |
| Adhesive control | ✅ | 🚧 (stub ready) |
| Adhesive profiles | ✅ | 🚧 (stub ready) |
| Crane positioning | ✅ | 🚧 (stub ready) |
| UDP server | ✅ | ✅ |
| Logging | ✅ | ✅ + visual log |
| Plot manager | ✅ | 🚧 (ready to embed) |

## Migration Path

### Phase 1: Test Layout ✅ (DONE)
- Install textual
- Run dashboard
- Test navigation
- Verify device discovery

### Phase 2: Wire Core Operations
- Connect motor control handlers
- Integrate tracking functions
- Add device selection UI
- Test with real robots

### Phase 3: Enhanced Features
- Embed matplotlib plots
- Add progress indicators
- Real-time device monitoring
- Code update functionality

### Phase 4: Full Replacement
- Move all App.py functions
- Add missing features
- Performance tuning
- Documentation updates

## Quick Start Guide

### For First-Time Users

```bash
# 1. Navigate to programs directory
cd base/programs

# 2. Run the setup script
./run_dashboard.sh

# 3. Use keyboard to navigate
#    - Arrow keys or Tab to move
#    - Enter to select
#    - R to refresh devices
#    - Q to quit

# 4. Try these operations:
#    a. Expand "1. Connect"
#    b. Select "Discover robots"
#    c. Watch Device panel update
#    d. Check Status Log for events
#    e. Expand "2. Component"
#    f. Select "Select component"
```

### For App.py Users

If you're familiar with `App.py`:

1. **Same startup**: UDP server starts automatically
2. **Same devices**: Uses your SSH config files
3. **Same operations**: All menu items match App.py
4. **New UI**: 4-panel layout instead of sequential screens
5. **Better visibility**: See everything at once

## Keyboard Shortcuts Quick Reference

| Key | Action | Old App.py Equivalent |
|-----|--------|----------------------|
| `↑/↓` | Navigate menu | Arrow keys in bullet menu |
| `Enter` | Select item | Enter/Space in bullet menu |
| `Tab` | Next item | Tab (sometimes) |
| `R` | Refresh devices | Select "Refresh" from menu |
| `Q` | Quit | Select "Quit" from menu |
| `Ctrl+C` | Force quit | Ctrl+C |

## UI Element Guide

### Menu Indicators
```
▶ Section         = Collapsed (click to expand)
▼ Section         = Expanded (click to collapse)
    • Item        = Indented sub-item (clickable action)
✕ Quit            = Special quit action
```

### Device Status
```
● robot1          = Online (green dot)
  192.168.1.101   = IP address (indented)

○ robot3          = Offline (gray dot)
  192.168.1.103   = IP address
```

### Log Messages
```
▌ [17:24:01] Message   = Pink bar + timestamp + text
▌ [17:24:15] Success   = Green text for success
▌ [17:24:30] Warning   = Yellow text for warning
▌ [17:25:00] Error     = Red text for errors
```

## Tips & Tricks

### Efficient Navigation
- Use Tab key for quick menu traversal
- Expand only the section you need
- Watch Status Log for confirmation
- Check Device panel before operations

### Monitoring Operations
- Leave dashboard open while robots work
- Status Log shows real-time events
- Device panel shows connectivity
- Operation View shows current state

### Troubleshooting
- Check Status Log first for errors
- Verify devices are online (● green)
- Use "R" to refresh device list
- Red errors are always logged

## Future Enhancements

The dashboard is designed for growth:

### Short Term
- [ ] Wire up remaining operations
- [ ] Add device selection checkboxes
- [ ] Embed matplotlib in Operation View
- [ ] Add progress bars for long ops

### Medium Term
- [ ] Real-time plot updates
- [ ] Camera feed display
- [ ] Interactive parameter forms
- [ ] Log export to file

### Long Term
- [ ] Multiple operation tabs
- [ ] 3D crane visualization
- [ ] Remote shell access
- [ ] Operation recording/playback

---

**Recommendation**: Use Dashboard.py for all normal operations. Keep App.py as a fallback or for scripting scenarios.
