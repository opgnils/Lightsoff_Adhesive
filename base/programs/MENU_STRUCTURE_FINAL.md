# LightsOff Dashboard - Final Menu Structure

## Layout Proportions
- **Horizontal**: 20% (left) / 80% (right)
- **Vertical**: 75% (top) / 25% (bottom)

## Complete Menu Structure

### 1. Connect
```
▶ 1  Connect
    • Discover robots
    • Select robots
    • Update code
```

### 2. Component
```
▶ 2  Component
    • Select component
    • Change component
```

### 3. Tracking (MOVED UP - Now #3)
```
▶ 3  Tracking
    • Combined tracking
```
**Note**: Tracking moved before Assembly Robot for better workflow (track → assemble)

### 4. Assembly Robot (Now #4)
```
▶ 4  Assembly Robot
    • Engage clamps
    • Disengage clamps
```

### 5. Adhesive Robot (Now #5, with Emergency Stop added)
```
▶ 5  Adhesive Robot
    • Manual control
    • Run profile
    • View history
    • Emergency stop    ← ADDED
```

### 6. Crane (Remains #6)
```
▶ 6  Crane
    • Position crane
    • Home position
    • Emergency stop
```

### Quit
```
✕ Quit
```

---

## Changes Made

### ✅ Menu Reordering
- **Tracking** moved from #6 → **#3** (before Assembly Robot)
- **Assembly Robot** moved from #3 → **#4**
- **Adhesive Robot** moved from #4 → **#5**
- **Crane** moved from #5 → **#6**

### ✅ Added Emergency Stop to Adhesive Robot
New menu item added: **"Emergency stop"**

When activated:
- Stops adhesive dispenser immediately
- Releases pressure
- Disengages all motors
- System enters safe state

---

## Workflow Logic

The new order follows a more logical workflow:

1. **Connect** → Set up robot connections
2. **Component** → Select what you're working on
3. **Tracking** → Track the component position
4. **Assembly Robot** → Engage clamps to secure component
5. **Adhesive Robot** → Apply adhesive (with emergency stop)
6. **Crane** → Position and move crane

---

## Visual Layout

```
╔═════════════╦════════════════════════════════════════════════╗
║             ║                                                ║
║  ▶ 1. Con   ║         Operation View (80%)                   ║
║  ▶ 2. Com   ║                                                ║
║  ▶ 3. Tra   ║  [Large working area]                          ║
║  ▶ 4. Ass   ║                                                ║
║  ▶ 5. Adh   ║  • Shows operation details                     ║
║  ▶ 6. Cra   ║  • Interactive controls                        ║
║             ║  • Plots and data                              ║
║  ✕ Quit     ║                                                ║
║             ║  75% height                                    ║
║   20%       ║                                                ║
╠═════════════╬════════════════════════════════════════════════╣
║  Devices    ║         Status Log (80%)                       ║
║  ● robot1   ║  ▌ [17:24:01] Timestamped events               ║
║   20%       ║         25% height                             ║
╚═════════════╩════════════════════════════════════════════════╝
```

---

## Emergency Stops

The dashboard now has emergency stops in two locations:

### Adhesive Robot Emergency Stop (NEW)
- Menu: **5. Adhesive Robot → Emergency stop**
- Purpose: Immediately halt adhesive dispensing
- Actions:
  - Stop dispenser
  - Release pressure
  - Disengage motors
  - Enter safe state

### Crane Emergency Stop
- Menu: **6. Crane → Emergency stop**
- Purpose: Halt all crane operations
- Actions:
  - Stop crane movement
  - Disengage all systems
  - Emergency safety protocols

---

## Summary

✅ **Tracking** now appears early in menu (#3) - track before assembly  
✅ **Assembly Robot** moved to #4 - assemble after tracking  
✅ **Adhesive Robot** has 4 items now (including emergency stop)  
✅ **Emergency stop** available for both Adhesive Robot and Crane  
✅ **Layout remains** 20% left / 80% right, 75% top / 25% bottom  
✅ **Same clean style** - non-fancy terminal UI  

---

**All changes applied!** The dashboard is ready to use with the updated menu structure.
