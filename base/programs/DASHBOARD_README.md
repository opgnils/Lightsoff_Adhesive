# LightsOff Dashboard Interface

## Overview

The new Dashboard interface (`Dashboard.py`) provides a unified, single-window control system for managing the LightsOff robotic system. It replaces the sequential CLI workflow in `App.py` with a modern TUI (Terminal User Interface).

## Layout

```
┌──────────────────┬──────────────────────────────────────────┐
│  Control System  │                                          │
│                  │           Operation View                 │
│  [menu items]    │                                          │
│                  │                                          │
│                  │                                          │
│                  │                                          │
├──────────────────┼──────────────────────────────────────────┤
│    Devices       │           Status Log                     │
│                  │                                          │
└──────────────────┴──────────────────────────────────────────┘
```

### Panels

1. **Control System (Top-Left, 30% x 75%)**
   - Hierarchical menu with expandable sections
   - Main categories: Connect, Component, Assembly, Adhesive, Tracking, Crane
   - Click section headers to expand/collapse sub-options

2. **Operation View (Top-Right, 70% x 75%)**
   - Main working area
   - Displays context-specific information and controls
   - Shows operation status, parameters, and results

3. **Devices (Bottom-Left, 30% x 25%)**
   - Real-time device connection status
   - Green dot (●) = online
   - Gray dot (○) = offline
   - Shows hostname and IP address

4. **Status Log (Bottom-Right, 70% x 25%)**
   - Timestamped event log
   - Color-coded by severity:
     - Pink: Info messages
     - Green: Success
     - Yellow: Warnings
     - Red: Errors

## Installation

### Install Dependencies

```bash
# Install textual for the TUI interface
pip install textual

# Or if using a virtual environment:
python -m pip install textual
```

## Usage

### Running the Dashboard

```bash
# From the programs directory
cd /home/icd-wmpc06/Documents/Lightsoff_Adhesive/base/programs
python Dashboard.py
```

### Keyboard Shortcuts

- **Arrow Keys / Tab**: Navigate menu
- **Enter**: Select menu item
- **R**: Refresh device list
- **Q**: Quit application

### Menu Structure

#### 1. Connect
- **Discover robots**: Scan SSH config for available devices
- **Select robots**: Choose specific robots to use (coming soon)
- **Update code**: Push latest code to remote robots (coming soon)

#### 2. Component
- **Select component**: Choose component for tracking
- **Change component**: Switch to different component (coming soon)

#### 3. Assembly Robot
- **Engage clamps**: Lock component clamps
- **Disengage clamps**: Release component clamps
- **Position crane**: Move crane to target position

#### 4. Adhesive Robot
- **Manual control**: Interactive adhesive dispenser control
- **Run profile**: Execute pre-configured adhesive profile
- **View history**: See previous operation data

#### 5. Tracking
- **Aruco tracking**: Track Aruco markers only
- **Hole tracking**: Detect holes in components
- **Combined tracking**: Track both Aruco markers and holes

#### 6. Crane
- **Position crane**: Move to target coordinates
- **Home position**: Return to safe position
- **Emergency stop**: Halt all operations immediately

## Features

### Current Implementation
✅ Full UI layout with 4 panels  
✅ Expandable hierarchical menu  
✅ Real-time device status display  
✅ Timestamped status logging  
✅ Color-coded log messages  
✅ Device discovery and status checking  
✅ Component selection  
✅ Keyboard shortcuts  

### In Progress
🚧 Robot selection interface  
🚧 Code update functionality  
🚧 Motor control integration  
🚧 Adhesive control integration  
🚧 Tracking mode integration  
🚧 Crane control integration  
🚧 Live plot embedding  

## Comparison with App.py

### Old CLI (`App.py`)
- Sequential workflow (can't go back easily)
- Multiple terminal clears
- Bullet-style text menus
- No persistent status view
- Can't see device status during operations

### New Dashboard (`Dashboard.py`)
- Non-linear workflow (navigate freely)
- All information visible simultaneously
- Modern TUI with panels
- Persistent status log
- Real-time device monitoring
- Expandable menus reduce clutter

## Configuration

The dashboard uses the same configuration as `App.py`:

- **SSH Config**: Located in `ssh/config_lightsoff` (or your custom config)
- **Devices**: Defined in SSH config files
- **UDP Server**: Automatically started on launch
- **Logging**: Enabled by default, logs to `logs/` directory

## Troubleshooting

### Textual not installed
```
ImportError: No module named 'textual'
```
**Solution**: Run `pip install textual`

### No devices found
**Check**:
- SSH config file exists in `ssh/` directory
- Network connectivity to robots
- Robot IP addresses are correct
- SSH keys are properly configured

### UDP Server fails to start
**Check**:
- Port is not already in use
- Firewall settings allow UDP traffic
- No other instance of the app is running

## Development

### Adding New Menu Items

1. Edit `_refresh_menu()` to add section or sub-item
2. Add handler in `_handle_action()`
3. Implement action method (e.g., `_do_new_action()`)
4. Update operation view and log appropriate messages

### Adding New Panels

1. Create widget class inheriting from `Static` or other Textual widget
2. Add to `compose()` method
3. Update CSS for styling
4. Wire up reactive updates as needed

## Migration from App.py

To migrate your workflow from `App.py` to `Dashboard.py`:

1. **Startup**: Both initialize UDP server and discover devices automatically
2. **Device Selection**: Use "Connect > Discover robots" instead of initial CLI selection
3. **Operations**: Use expandable menus instead of sequential steps
4. **Monitoring**: Check Status Log panel for events (replaces print statements)
5. **Device Status**: Always visible in Devices panel (no need to refresh manually)

## Future Enhancements

- Embedded matplotlib plots in Operation View
- Real-time camera feed display
- Interactive forms for parameter input
- Progress bars for long operations
- Split-pane for simultaneous plot viewing
- Tabbed interface for multiple operations
- Export status log to file
- Device filtering and grouping
- Custom color themes
