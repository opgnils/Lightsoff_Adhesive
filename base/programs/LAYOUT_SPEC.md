# LightsOff Dashboard - Layout Specification

## Final Layout Design (Option A)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                         LightsOff Control System                             ║
╠═══════════════════╦══════════════════════════════════════════════════════════╣
║                   ║                                                          ║
║  CONTROL SYSTEM   ║               OPERATION VIEW                             ║
║                   ║                                                          ║
║  ▶ 1. Connect     ║  Welcome to LightsOff Control System                     ║
║  ▼ 2. Component   ║                                                          ║
║      • Select     ║  Select an option from the Control System menu           ║
║      • Change     ║                                                          ║
║  ▶ 3. Assembly    ║  Available operations:                                   ║
║  ▼ 4. Adhesive    ║    • Connect to remote robots                            ║
║      • Manual     ║    • Configure components for tracking                   ║
║      • Profile    ║    • Control assembly robots (motors/clamps)             ║
║      • History    ║    • Control adhesive robots                             ║
║  ▼ 5. Tracking    ║    • Run tracking operations (Aruco, Holes, Combined)    ║
║      • Aruco      ║    • Position crane                                      ║
║      • Holes      ║                                                          ║
║      • Combined   ║  Press R to refresh devices | Press Q to quit            ║
║  ▶ 6. Crane       ║                                                          ║
║                   ║                                                          ║
║  ✕ Quit           ║                                                          ║
║                   ║                                                          ║
║     30% width     ║                   70% width                              ║
║     75% height    ║                   75% height                             ║
╠═══════════════════╬══════════════════════════════════════════════════════════╣
║                   ║                                                          ║
║     DEVICES       ║                  STATUS LOG                              ║
║                   ║                                                          ║
║  ● robot1         ║  ▌ [17:23:45] Dashboard started                          ║
║    192.168.1.101  ║  ▌ [17:24:01] Loaded 3 device(s) from configuration      ║
║  ● robot2         ║  ▌ [17:24:15] Discovering devices...                     ║
║    192.168.1.102  ║  ▌ [17:24:18] Found 3 device(s) in configuration         ║
║  ○ robot3         ║  ▌ [17:24:20] Checking online status...                  ║
║    192.168.1.103  ║  ▌ [17:24:23] 2 device(s) online                         ║
║                   ║  ▌ [17:24:45] Component set to Component 0               ║
║     30% width     ║                   70% width                              ║
║     25% height    ║                   25% height                             ║
╚═══════════════════╩══════════════════════════════════════════════════════════╝
```

## Panel Dimensions

### Vertical Split
- **Top Row**: 75% of terminal height
- **Bottom Row**: 25% of terminal height

### Horizontal Split

#### Top Row
- **Control System (Left)**: 30% width
- **Operation View (Right)**: 70% width

#### Bottom Row  
- **Devices (Left)**: 30% width
- **Status Log (Right)**: 70% width

## Color Scheme

### Background
- Primary: `#1a1b26` (dark blue-gray)
- Secondary: `#16161e` (darker blue-gray for left column)

### Borders
- Border color: `#44475a` (subtle purple-gray)
- Border title: `#ff79c6` (pink/magenta)

### Status Indicators
- Online: `#50fa7b` (green) - ●
- Offline: `#6272a4` (gray) - ○

### Text Colors
- Primary text: `#a9b1d6` (light blue-gray)
- Highlighted menu: `#1a1b26` on `#ff79c6` (inverted)
- Dim text: `#6272a4` (gray)

### Log Message Colors
- Info: `#ff79c6` (pink)
- Success: `#50fa7b` (green)
- Warning: `#f1fa8c` (yellow)
- Error: `#ff5555` (red)

## Menu Structure

### Expandable Sections

```
▶ 1. Connect          (collapsed)
▼ 2. Component        (expanded)
    • Select component
    • Change component
▶ 3. Assembly Robot   (collapsed)
▶ 4. Adhesive Robot   (collapsed)
▶ 5. Tracking         (collapsed)
▶ 6. Crane            (collapsed)

✕ Quit
```

## Responsive Behavior

### Minimum Recommended Terminal Size
- Width: 120 columns
- Height: 30 rows

### Overflow Handling
- All panels have scrolling enabled
- Status log auto-scrolls to latest
- Long text wraps in operation view
- Menu items scroll if needed

## Interactive Elements

### Keyboard Navigation
- `↑/↓` or `Tab/Shift+Tab`: Navigate menu
- `Enter`: Select menu item / Expand section
- `R`: Refresh device list
- `Q`: Quit application
- `Ctrl+C`: Force quit

### Mouse Support (if enabled)
- Click on menu items to select
- Click on section headers to expand/collapse
- Scroll in any panel with mouse wheel

## State Indicators

### Device Status
```
● robot1              # Green dot = online
  192.168.1.101       # IP address shown below

○ robot3              # Gray dot = offline
  192.168.1.103
```

### Menu State
```
▶ Section             # Collapsed (arrow points right)
▼ Section             # Expanded (arrow points down)
    • Sub-item        # Indented sub-items shown when expanded
```

### Log Timestamps
```
▌ [HH:MM:SS] Message  # Pink bar indicator + timestamp + message
```

## Panel Behaviors

### Control System Panel
- Maintains scroll position when expanding/collapsing sections
- Highlights current selection
- Section headers toggle expansion on select

### Operation View Panel
- Content changes based on selected menu item
- Supports rich text formatting (bold, colors, etc.)
- Auto-scrolls for long content

### Devices Panel
- Updates in real-time when devices change
- Shows online status with color-coded dots
- Displays hostname and IP for each device

### Status Log Panel
- Auto-scrolls to show latest messages
- Retains history (scrollable)
- Color-coded by message severity
- Includes timestamps for all events
