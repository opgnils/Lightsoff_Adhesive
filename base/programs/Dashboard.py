"""Dashboard-style TUI entrypoint for LightsOff.

Multi-pane terminal dashboard:
  ┌───────────┬──────────────────────────────────────────────────┐
  │  Control  │                                                  │
  │  System   │           Operation View                         │
  │           │                                                  │
  │  [menu]   │                                                  │
  │           │                                                  │
  │           │                                                  │
  │           │                                                  │
  │           │                                                  │
  ├───────────┼──────────────────────────────────────────────────┤
  │  Devices  │           Status Log                             │
  └───────────┴──────────────────────────────────────────────────┘
  
Layout: 20% left column, 80% right column
        75% top row, 25% bottom row

Reuses the same APPSTATE shape as App.py.
"""

import os
import sys
import socket
import csv
import time
import subprocess
import threading
from datetime import datetime
from typing import Dict, Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from base.UDPServer import UDPServer
from base.Components import Component, ComponentPositions, Aruco
from base.Crane import CranePosition
from base.Devices import (
    get_devices, 
    check_online_devices, 
    launch_remote_file, 
    run_updates,
    cleanup_remote_python_processes,
    ensure_adhesive_listener_running
)

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, Container
    from textual.widgets import Static, ListView, ListItem, Label, RichLog
    from textual.reactive import reactive
except ImportError as e:
    raise SystemExit(
        "Textual is not installed. Install it with:\n"
        "  python -m pip install textual\n"
    ) from e


# ─── Widgets ──────────────────────────────────────────────────────────────────


class DevicePanel(Static):
    """Bottom-left panel: connected devices list with status indicators."""

    devices_data: reactive[list] = reactive([])

    def watch_devices_data(self, devices: list) -> None:
        """React to device data changes."""
        self.update_display(devices)

    def update_display(self, devices: list) -> None:
        """Update the device list display."""
        lines: list[str] = []
        if not devices:
            lines.append("  [dim](no devices found)[/dim]")
        else:
            for d in devices:
                host = d.get("Host", "?")
                hostname = d.get("HostName", "?")
                # Check if device is online (you can add online status to device dict)
                online = d.get("online", True)
                indicator = "[#50fa7b]●[/#50fa7b]" if online else "[dim]○[/dim]"
                lines.append(f"  {indicator} [b]{host}[/b]")
                lines.append(f"      [dim]{hostname}[/dim]")
        self.update("\n".join(lines))

    def update_from_state(self, appstate: Dict[str, Any]) -> None:
        """Update from application state."""
        devices = appstate.get("selected_devices", []) or []
        self.devices_data = devices


class OperationView(Static):
    """Right main panel: shows the current operation context."""

    def show(self, title: str, body: str) -> None:
        """Update the operation view with title and body content."""
        self.update(f"[b #ff79c6]{title}[/b #ff79c6]\n\n{body}")


class StatusLog(RichLog):
    """Bottom-right panel: timestamped status log."""

    def log_message(self, msg: str, level: str = "info") -> None:
        """Add a timestamped message to the log.
        
        Args:
            msg: The message to log
            level: Log level (info, success, warning, error)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Color-code based on level
        color_map = {
            "info": "#ff79c6",
            "success": "#50fa7b",
            "warning": "#f1fa8c",
            "error": "#ff5555",
        }
        color = color_map.get(level, "#ff79c6")
        
        self.write(f"[{color}]▌[/{color}] [{timestamp}] {msg}")


class MainMenu(ListView):
    """Sidebar menu with expandable sections."""

    def __init__(self) -> None:
        super().__init__(id="menu")


# ─── App ──────────────────────────────────────────────────────────────────────


class LightsOffDashboard(App):
    """LightsOff multi-pane TUI dashboard."""

    TITLE = "LightsOff Control System"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh_devices", "Refresh Devices"),
    ]

    CSS = """
    /* ── Global ──────────────────────────────────── */
    Screen {
        background: #1a1b26;
        color: #a9b1d6;
    }

    /* ── Layout containers ───────────────────────── */
    #top-row {
        height: 75%;
    }

    #bottom-row {
        height: 25%;
    }

    /* ── Left column ─────────────────────────────── */
    #left-col {
        width: 20%;
        background: #16161e;
    }

    #menu-box {
        height: 100%;
        border: round #44475a;
        border-title-color: #ff79c6;
        border-title-style: bold;
        padding: 0 1;
    }

    #device-box {
        height: 100%;
        border: round #44475a;
        border-title-color: #ff79c6;
        border-title-style: bold;
        padding: 0 1;
        overflow-y: auto;
    }

    /* Menu list styling */
    #menu {
        height: 1fr;
        padding: 0;
    }

    #menu > ListItem {
        padding: 0 1;
        height: auto;
    }

    #menu > ListItem.--highlight {
        background: #ff79c6;
        color: #1a1b26;
    }

    /* ── Right column ────────────────────────────── */
    #right-col {
        width: 80%;
    }

    #operation-box {
        height: 100%;
        border: round #44475a;
        border-title-color: #ff79c6;
        border-title-style: bold;
        padding: 1 2;
        overflow-y: auto;
    }

    #status-box {
        height: 100%;
        border: round #44475a;
        border-title-color: #ff79c6;
        border-title-style: bold;
        padding: 0 1;
    }

    /* RichLog inside status box */
    #status-log {
        height: 1fr;
    }
    """

    def __init__(self, appstate: Dict[str, Any]) -> None:
        super().__init__()
        self.appstate = appstate
        self._expanded_section: str | None = None

    def compose(self) -> ComposeResult:
        # Top row: Control System | Operation View
        with Horizontal(id="top-row"):
            # ── Left column ──
            with Vertical(id="left-col"):
                with Container(id="menu-box") as menu_box:
                    menu_box.border_title = "Control System"
                    yield MainMenu()

            # ── Right column ──
            with Vertical(id="right-col"):
                with Container(id="operation-box") as op_box:
                    op_box.border_title = "Operation View"
                    yield OperationView(id="operation")

        # Bottom row: Devices | Status Log
        with Horizontal(id="bottom-row"):
            with Vertical(id="left-col"):
                with Container(id="device-box") as dev_box:
                    dev_box.border_title = "Devices"
                    yield DevicePanel(id="devices")

            with Vertical(id="right-col"):
                with Container(id="status-box") as st_box:
                    st_box.border_title = "Status Log"
                    yield StatusLog(id="status-log", markup=True)

    # ─── Actions ──────────────────────────────────────────────────────────────

    def action_quit(self) -> None:
        """Handle quit action."""
        self._log("Shutting down...", "info")
        server = self.appstate.get("server")
        if isinstance(server, UDPServer):
            try:
                server.close_server()
                self._log("UDP server closed", "success")
            except Exception as e:
                self._log(f"Error closing server: {e}", "error")
        self.exit()

    def action_refresh_devices(self) -> None:
        """Refresh device list."""
        self._log("Refreshing device list...", "info")
        try:
            devices = get_devices()
            # Check online status
            online_devices = check_online_devices(devices)
            # Mark online status in device dict
            for d in devices:
                d["online"] = d in online_devices
            
            self.appstate["selected_devices"] = devices
            self.query_one("#devices", DevicePanel).update_from_state(self.appstate)
            self._log(f"Found {len(devices)} device(s), {len(online_devices)} online", "success")
        except Exception as e:
            self._log(f"Error refreshing devices: {e}", "error")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Initialize the dashboard on mount."""
        self._refresh_menu()
        menu = self.query_one("#menu", MainMenu)
        if len(menu.children) > 0:
            menu.index = 0

        self.query_one("#devices", DevicePanel).update_from_state(self.appstate)

        self.query_one("#operation", OperationView).show(
            "Welcome to LightsOff Control System",
            "[dim]Select an option from the Control System menu on the left.[/dim]\n\n"
            "Available operations:\n"
            "  • Connect to remote robots\n"
            "  • Configure components for tracking\n"
            "  • Run combined tracking operations\n"
            "  • Control assembly robots (engage/disengage clamps)\n"
            "  • Control adhesive robots\n"
            "  • Position and control crane\n\n"
            "[dim]Press [b]R[/b] to refresh devices | Press [b]Q[/b] to quit[/dim]"
        )

        # Initial log message
        self._log("Dashboard started", "success")
        devices = self.appstate.get("selected_devices", [])
        if devices:
            self._log(f"Loaded {len(devices)} device(s) from configuration", "info")

    # ── Menu builder ──────────────────────────────────────────────────────────

    def _refresh_menu(self) -> None:
        """Rebuild menu items; expanded section shows indented sub-items."""
        menu = self.query_one("#menu", MainMenu)

        sections = [
            ("connect", "1  Connect", [
                "Discover robots",
                "Select robots", 
                "Update code"
            ]),
            ("component", "2  Component", [
                "Select component",
                "Change component"
            ]),
            ("tracking", "3  Tracking", [
                "Combined tracking"
            ]),
            ("assembly", "4  Assembly Robot", [
                "Engage clamps",
                "Disengage clamps"
            ]),
            ("adhesive", "5  Adhesive Robot", [
                "Manual control",
                "Run profile",
                "View history",
                "Emergency stop"
            ]),
            ("crane", "6  Crane", [
                "Position crane",
                "Home position",
                "Emergency stop"
            ]),
        ]

        items: list[ListItem] = []
        for key, label, subs in sections:
            arrow = "▼" if self._expanded_section == key else "▶"
            items.append(ListItem(Label(f"{arrow} {label}"), name=f"section:{key}"))
            if self._expanded_section == key:
                for sub in subs:
                    items.append(ListItem(Label(f"    • {sub}"), name=f"action:{key}:{sub}"))

        items.append(ListItem(Label(""), name="separator"))
        items.append(ListItem(Label("✕  Quit"), name="action:quit"))

        menu.clear()
        for it in items:
            menu.append(it)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, msg: str, level: str = "info") -> None:
        """Append a line to the status log panel."""
        log = self.query_one("#status-log", StatusLog)
        log.log_message(msg, level)

    def _set_operation(self, title: str, body: str) -> None:
        """Update the operation view."""
        self.query_one("#operation", OperationView).show(title, body)

    # ── Event handling ────────────────────────────────────────────────────────

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle menu selection events."""
        name = event.item.name or ""

        # Section headers toggle expansion
        if name.startswith("section:"):
            key = name.split(":", 1)[1]
            self._expanded_section = None if self._expanded_section == key else key
            self._refresh_menu()
            return

        # Handle separator
        if name == "separator":
            return

        # Sub-actions
        if name.startswith("action:"):
            parts = name.split(":", 2)
            if len(parts) == 3:
                section, action = parts[1], parts[2]
                await self._handle_action(section, action)
            elif name == "action:quit":
                self.action_quit()

    async def _handle_action(self, section: str, action: str) -> None:
        """Route actions to appropriate handlers."""
        
        # ── Connect actions ──
        if section == "connect":
            if action == "Discover robots":
                await self._do_discover_robots()
            elif action == "Select robots":
                await self._do_select_robots()
            elif action == "Update code":
                await self._do_update_code()

        # ── Component actions ──
        elif section == "component":
            if action == "Select component":
                await self._do_select_component()
            elif action == "Change component":
                await self._do_change_component()

        # ── Tracking actions ──
        elif section == "tracking":
            if action == "Combined tracking":
                await self._do_tracking("combined")

        # ── Assembly Robot actions ──
        elif section == "assembly":
            if action == "Engage clamps":
                await self._do_motor_action(engage=True)
            elif action == "Disengage clamps":
                await self._do_motor_action(engage=False)

        # ── Adhesive Robot actions ──
        elif section == "adhesive":
            if action == "Manual control":
                await self._do_adhesive_manual()
            elif action == "Run profile":
                await self._do_adhesive_profile()
            elif action == "View history":
                await self._do_adhesive_history()
            elif action == "Emergency stop":
                await self._do_adhesive_emergency_stop()

        # ── Crane actions ──
        elif section == "crane":
            if action == "Position crane":
                await self._do_position_crane()
            elif action == "Home position":
                await self._do_crane_home()
            elif action == "Emergency stop":
                await self._do_crane_stop()

    # ── Menu action implementations ───────────────────────────────────────────

    async def _do_discover_robots(self) -> None:
        """Discover available robots from SSH config."""
        self._log("Discovering devices...", "info")
        self._set_operation(
            "Discover Robots",
            "[dim]Scanning SSH configuration for available robots...[/dim]"
        )
        
        try:
            devices = get_devices()
            self._log(f"Found {len(devices)} device(s) in configuration", "success")
            
            # Check online status
            self._log("Checking online status...", "info")
            online_devices = check_online_devices(devices)
            
            # Mark online status
            for d in devices:
                d["online"] = d in online_devices
            
            self.appstate["selected_devices"] = devices
            self.query_one("#devices", DevicePanel).update_from_state(self.appstate)
            
            self._log(f"{len(online_devices)} device(s) online", "success")
            
            # Update operation view
            device_list = "\n".join([
                f"  {'●' if d.get('online') else '○'} {d.get('Host', '?')} - {d.get('HostName', '?')}"
                for d in devices
            ])
            
            self._set_operation(
                "Device Discovery Complete",
                f"Found [b]{len(devices)}[/b] device(s), [b #50fa7b]{len(online_devices)}[/b] online:\n\n"
                f"{device_list}\n\n"
                "[dim]Next steps:[/dim]\n"
                "  • Select specific robots to use\n"
                "  • Update code on selected robots\n"
                "  • Begin tracking operations"
            )
            
        except Exception as e:
            self._log(f"Error discovering devices: {e}", "error")
            self._set_operation(
                "Discovery Failed",
                f"[#ff5555]Error:[/#ff5555] {e}\n\n"
                "Please check:\n"
                "  • SSH configuration files\n"
                "  • Network connectivity\n"
                "  • Device availability"
            )

    async def _do_select_robots(self) -> None:
        """Select specific robots to use."""
        self._log("Robot selection interface", "info")
        
        devices = self.appstate.get("selected_devices", [])
        if not devices:
            self._log("No devices found. Run 'Discover robots' first.", "warning")
            self._set_operation(
                "Select Robots",
                "[#ff5555]No devices available.[/#ff5555]\n\n"
                "Please run [b]Discover robots[/b] first to find available devices."
            )
            return
        
        # For now, show all devices and mark them as selected
        # TODO: Add interactive checkbox selection in future
        device_list = "\n".join([
            f"  {'✓' if d.get('online') else '✗'} {d.get('Host', '?')} - {d.get('HostName', '?')}"
            for d in devices
        ])
        
        self._log(f"All {len(devices)} discovered device(s) are selected", "info")
        self._set_operation(
            "Select Robots",
            f"[b]Currently selected devices:[/b]\n\n"
            f"{device_list}\n\n"
            "[dim]All discovered robots are automatically selected.[/dim]\n"
            "[dim]Interactive selection will be added in a future update.[/dim]"
        )

    async def _do_update_code(self) -> None:
        """Update code on remote robots."""
        devices = self.appstate.get("selected_devices", [])
        
        if not devices:
            self._log("No devices selected", "warning")
            self._set_operation(
                "Update Code",
                "[#ff5555]No devices selected.[/#ff5555]\n\n"
                "Please run [b]Discover robots[/b] first."
            )
            return
        
        self._log(f"Starting code update on {len(devices)} device(s)...", "info")
        self._set_operation(
            "Update Code",
            f"[b]Updating code on {len(devices)} device(s)...[/b]\n\n"
            "[dim]This will:\n"
            "  • Transfer updated Python files via deploy.sh\n"
            "  • Sync cambots directory\n"
            "  • Update dependencies if needed[/dim]\n\n"
            "Please wait..."
        )
        
        # Run updates in background to keep UI responsive
        def update_task():
            try:
                config = self.appstate.get("config", "config_lightsoff")
                run_updates(devices, config=config)
                self._log(f"Code update completed on {len(devices)} device(s)", "success")
                # Update operation view with results
                self.call_from_thread(self._set_operation,
                    "Update Code Complete",
                    f"[#50fa7b]✓[/#50fa7b] Successfully updated code on {len(devices)} device(s).\n\n"
                    "Changes deployed:\n"
                    "  • Python scripts synced\n"
                    "  • Cambots directory updated\n"
                    "  • Ready for operations"
                )
            except Exception as e:
                self._log(f"Code update failed: {e}", "error")
                self.call_from_thread(self._set_operation,
                    "Update Code Failed",
                    f"[#ff5555]Error updating code:[/#ff5555]\n\n{e}\n\n"
                    "Please check:\n"
                    "  • Network connectivity\n"
                    "  • SSH access to devices\n"
                    "  • deploy.sh script exists"
                )
        
        thread = threading.Thread(target=update_task, daemon=True)
        thread.start()

    async def _do_select_component(self) -> None:
        """Select a component for tracking."""
        # Hardcoded for now - matches App.py behavior
        comp = Component(
            ComponentPositions(
                coarse=CranePosition(0, 0, 10, 0, 0, 0),
                intermediate=CranePosition(0, 0, 5, 0, 0, 0),
                fine=CranePosition(0, 0, 1, 0, 0, 0),
                target=CranePosition(0, 0, 0, 0, 0, 0),
            ),
            Aruco(id=0, position=CranePosition(1, 1, 0, 0, 0, 0)),
        )
        self.appstate["selected_component"] = comp
        self._log("Component set to Component 0", "success")
        
        self._set_operation(
            "Component Selected",
            "Selected component: [b]Component 0[/b]\n\n"
            "Details:\n"
            "  • Aruco ID: [b]0[/b]\n"
            "  • Target position: (0, 0, 0, 0, 0, 0)\n"
            "  • Coarse position: (0, 0, 10, 0, 0, 0)\n"
            "  • Intermediate: (0, 0, 5, 0, 0, 0)\n"
            "  • Fine position: (0, 0, 1, 0, 0, 0)\n\n"
            "[dim]Note: Component selection is currently hardcoded.[/dim]"
        )

    async def _do_change_component(self) -> None:
        """Change the selected component."""
        self._log("Change component (not yet implemented)", "warning")
        self._set_operation(
            "Change Component",
            "[dim]Select a different component for tracking operations.[/dim]\n\n"
            "Available components:\n"
            "  • Component 0 (Aruco ID: 0)\n"
            "  • Component 1 (Aruco ID: 1)\n"
            "  • Component 2 (Aruco ID: 2)\n\n"
            "[dim]Implementation needed: Interactive component selector[/dim]"
        )

    async def _do_motor_action(self, engage: bool) -> None:
        """Engage or disengage motor clamps."""
        action = "Engaging" if engage else "Disengaging"
        motor_direction = False if engage else True  # False = engage, True = release
        
        devices = self.appstate.get("selected_devices", [])
        
        if not devices:
            self._log("No devices selected", "warning")
            self._set_operation(
                f"{action} Clamps",
                "[#ff5555]No devices selected.[/#ff5555]\n\n"
                "Please run [b]Discover robots[/b] first."
            )
            return
        
        self._log(f"{action} clamps on {len(devices)} device(s)...", "info")
        self._set_operation(
            f"{action} Clamps",
            f"[b]{action} motor clamps on {len(devices)} robot(s)...[/b]\n\n"
            f"[dim]Operation: {'Lock' if engage else 'Release'} component clamps[/dim]\n"
            "[dim]Duration: ~30 seconds[/dim]\n\n"
            "Please wait..."
        )
        
        # Run motor control in background
        def motor_task():
            try:
                threads = []
                all_success = True
                
                for d in devices:
                    self._log(f"Launching motor control on {d['Host']}...", "info")
                    success, thread = launch_remote_file(
                        device=d,
                        remote_python_file="~/Documents/LightsOff_Project/cambots/AssemblyRobot/MotorControl.py",
                        arguments=f"{str(motor_direction)} 2000 30",
                    )
                    if success:
                        threads.append(thread)
                    else:
                        all_success = False
                        self._log(f"Failed to start motor control on {d['Host']}", "error")
                
                # Wait for completion
                time.sleep(32)
                
                for t in threads:
                    if t and hasattr(t, 'join'):
                        t.join(timeout=5)
                
                if all_success:
                    self._log(f"Motors {'engaged' if engage else 'disengaged'} successfully", "success")
                    self.call_from_thread(self._set_operation,
                        f"{action} Complete",
                        f"[#50fa7b]✓[/#50fa7b] Successfully {'engaged' if engage else 'disengaged'} clamps on {len(devices)} robot(s).\n\n"
                        f"Status: Component clamps are now {'LOCKED' if engage else 'RELEASED'}\n\n"
                        "[dim]Ready for next operation.[/dim]"
                    )
                else:
                    self._log(f"Motor action completed with errors", "warning")
                    self.call_from_thread(self._set_operation,
                        f"{action} Completed with Errors",
                        f"[#f1fa8c]⚠[/#f1fa8c] Motor action completed but some devices failed.\n\n"
                        "Check status log for details."
                    )
                    
            except Exception as e:
                self._log(f"Motor control failed: {e}", "error")
                self.call_from_thread(self._set_operation,
                    f"{action} Failed",
                    f"[#ff5555]Error:[/#ff5555] {e}\n\n"
                    "Please check:\n"
                    "  • Device connectivity\n"
                    "  • Motor control script exists\n"
                    "  • Hardware connections"
                )
        
        thread = threading.Thread(target=motor_task, daemon=True)
        thread.start()

    async def _do_position_crane(self) -> None:
        """Position the crane."""
        self._log("Crane positioning (not yet implemented)", "warning")
        self._set_operation(
            "Position Crane",
            "[dim]Move crane to target position.[/dim]\n\n"
            "Positioning sequence:\n"
            "  1. Move to coarse position\n"
            "  2. Move to intermediate position\n"
            "  3. Move to fine position\n"
            "  4. Reach target position\n\n"
            "[dim]Crane control integration pending...[/dim]"
        )

    async def _do_adhesive_manual(self) -> None:
        """Manual adhesive control with TCP commands."""
        devices = self.appstate.get("selected_devices", [])
        
        if not devices:
            self._log("No devices selected", "warning")
            self._set_operation(
                "Adhesive Manual Control",
                "[#ff5555]No devices selected.[/#ff5555]\n\n"
                "Please run [b]Discover robots[/b] first."
            )
            return
        
        self._log("Starting adhesive manual control", "info")
        
        # Ensure listeners are running in background
        def ensure_listeners():
            for d in devices:
                try:
                    ensure_adhesive_listener_running(d)
                    self.call_from_thread(self._log, f"Adhesive listener ready on {d['Host']}", "success")
                except Exception as e:
                    self.call_from_thread(self._log, f"Failed to start listener on {d['Host']}: {e}", "error")
        
        thread = threading.Thread(target=ensure_listeners, daemon=True)
        thread.start()
        
        # Display control interface
        self._set_operation(
            "Adhesive Manual Control",
            "[b]Adhesive Manual Control[/b]\n\n"
            f"Controlling {len(devices)} device(s)\n\n"
            "[#50fa7b]Motor Configuration:[/#50fa7b]\n"
            "  • Motor 1: RPM (max: ±6000)\n"
            "  • Motor 2: Flowrate A in µL/s (max: ±1150)\n"
            "  • Motor 3: Flowrate B in µL/s (max: ±1150)\n\n"
            "[b]Control Method:[/b]\n"
            "Send commands via TCP in format: [b]motor1,motor2,motor3[/b]\n\n"
            "[#f1fa8c]Examples:[/#f1fa8c]\n"
            "  • Start: [b]1000,500,500[/b] (Motor1=1000 RPM, Motors 2&3=500 µL/s)\n"
            "  • Stop: [b]0,0,0[/b] (all motors stopped)\n"
            "  • Adjust: [b]2000,750,750[/b]\n\n"
            "[dim]To send commands:[/dim]\n"
            "1. Use external TCP client (e.g., netcat, Python script)\n"
            "2. Connect to device hostname:5001\n"
            "3. Send command string (e.g., \"1000,500,500\")\n\n"
            "[b]Quick Actions:[/b]\n"
            "  • Use [b]Emergency Stop[/b] menu item to send 0,0,0 immediately\n"
            "  • Or use [b]Run profile[/b] for automated control sequences\n\n"
            "[dim]Listeners are running. Commands will be processed in real-time.[/dim]\n"
            "[dim]Check status log for command confirmations.[/dim]"
        )

    async def _do_adhesive_profile(self) -> None:
        """Run adhesive profile from CSV."""
        devices = self.appstate.get("selected_devices", [])
        
        if not devices:
            self._log("No devices selected", "warning")
            self._set_operation(
                "Run Adhesive Profile",
                "[#ff5555]No devices selected.[/#ff5555]\n\n"
                "Please run [b]Discover robots[/b] first."
            )
            return
        
        # List available profiles
        base_dir = os.path.dirname(os.path.abspath(__file__))
        profiles_dir = os.path.join(base_dir, "adhesive_profiles")
        
        if not os.path.isdir(profiles_dir):
            self._log(f"Profiles directory not found: {profiles_dir}", "error")
            self._set_operation(
                "Run Adhesive Profile",
                f"[#ff5555]Profile directory not found:[/#ff5555]\n\n"
                f"{profiles_dir}\n\n"
                "Expected location: base/programs/adhesive_profiles/"
            )
            return
        
        profiles = [f for f in os.listdir(profiles_dir) if f.lower().endswith(".csv")]
        
        if not profiles:
            self._log("No CSV profiles found", "warning")
            self._set_operation(
                "Run Adhesive Profile",
                f"[#f1fa8c]No profiles found in:[/#f1fa8c]\n\n"
                f"{profiles_dir}\n\n"
                "Please add CSV profile files with format:\n"
                "  time, motor1, motor2, motor3"
            )
            return
        
        # Display available profiles with instructions
        profile_list = "\n".join([f"  [{i+1}] {p}" for i, p in enumerate(profiles)])
        
        self._log(f"Found {len(profiles)} adhesive profile(s)", "info")
        self._set_operation(
            "Run Adhesive Profile",
            f"[b]Available Adhesive Profiles ({len(profiles)})[/b]\n\n"
            f"{profile_list}\n\n"
            f"Connected to {len(devices)} device(s)\n\n"
            "[b]To run a profile:[/b]\n\n"
            "[#50fa7b]Use the profile runner script:[/#50fa7b]\n"
            f"  cd {base_dir}\n"
            f"  python3 run_adhesive_profile.py adhesive_profiles/PROFILE_NAME.csv\n\n"
            "[#50fa7b]Or run manually:[/#50fa7b]\n"
            "1. Ensure adhesive listeners are running (5001/tcp)\n"
            "2. Send commands: echo 'motor1,motor2,motor3' | nc HOSTNAME 5001\n"
            "3. Follow CSV timing (time,m1,m2,m3)\n\n"
            "[#f1fa8c]Profile Format:[/#f1fa8c]\n"
            "  • Column 1: Time in seconds (e.g., 0, 5.5, 10)\n"
            "  • Column 2: Motor 1 RPM (±6000 max)\n"
            "  • Column 3: Motor 2 µL/s (±1150 max)\n"
            "  • Column 4: Motor 3 µL/s (±1150 max)\n\n"
            "[#f1fa8c]Example Profile:[/#f1fa8c]\n"
            "  0.0,  0,    0,    0     # Start at rest\n"
            "  2.0,  1000, 500,  500   # Ramp up\n"
            "  10.0, 2000, 1000, 1000  # Full speed\n"
            "  15.0, 0,    0,    0     # Stop\n\n"
            "[dim]The script handles:[/dim]\n"
            "  • Listener startup checks\n"
            "  • Timed TCP command sending\n"
            "  • Emergency stop (press 'q' during execution)\n"
            "  • Final safety stop (0,0,0)\n\n"
            "[b]Press ESC to return to menu[/b]"
        )
        
        # For now, just show profiles. Full execution would require:
        # 1. Profile selection UI (modal dialog)
        # 2. Background thread with timed TCP sends
        # 3. Progress monitoring
        # 4. Emergency stop handling during execution
        # This is complex for TUI and better done via separate script or future enhancement

    async def _do_adhesive_history(self) -> None:
        """View adhesive history."""
        self._log("Viewing adhesive history", "info")
        
        # Check for log files
        base_dir = os.path.dirname(os.path.abspath(__file__))
        logs_dir = os.path.join(base_dir, "logs")
        
        if not os.path.isdir(logs_dir):
            self._set_operation(
                "Adhesive History",
                "[dim]No history logs found.[/dim]\n\n"
                "History will be available after running adhesive operations."
            )
            return
        
        log_files = [f for f in os.listdir(logs_dir) if f.endswith(".jsonl")]
        
        if not log_files:
            self._set_operation(
                "Adhesive History",
                "[dim]No log files found.[/dim]\n\n"
                "Logs will be created during operations."
            )
            return
        
        # Show most recent logs
        log_files.sort(reverse=True)
        recent_logs = log_files[:5]
        log_list = "\n".join([f"  • {log}" for log in recent_logs])
        
        self._set_operation(
            "Adhesive History",
            f"[b]Recent Operation Logs[/b]\n\n"
            f"{log_list}\n\n"
            f"Total logs: {len(log_files)}\n"
            f"Location: {logs_dir}\n\n"
            "[dim]Log viewer interface will be added to analyze historical data.[/dim]"
        )

    async def _do_adhesive_emergency_stop(self) -> None:
        """Emergency stop for adhesive robot."""
        devices = self.appstate.get("selected_devices", [])
        
        self._log("ADHESIVE EMERGENCY STOP activated", "error")
        
        if not devices:
            self._set_operation(
                "Adhesive Emergency Stop",
                "[b #ff5555]EMERGENCY STOP[/b #ff5555]\n\n"
                "[#ff5555]No devices connected to stop.[/#ff5555]\n\n"
                "Emergency stop requires connected devices."
            )
            return
        
        self._set_operation(
            "Adhesive Emergency Stop",
            "[b #ff5555]ADHESIVE EMERGENCY STOP ACTIVATED[/b #ff5555]\n\n"
            f"Stopping adhesive operations on {len(devices)} device(s)...\n\n"
            "Commands sent:\n"
            "  • Stop all motors (0,0,0)\n"
            "  • Release pressure\n"
            "  • Enter safe state\n\n"
            "[dim]Sending emergency stop commands...[/dim]"
        )
        
        # Send emergency stop commands
        def emergency_stop_task():
            try:
                stopped_count = 0
                for d in devices:
                    try:
                        # Send stop command via TCP (0,0,0 = stop all motors)
                        host = d.get("HostName")
                        port = 5001
                        with socket.create_connection((host, port), timeout=2.0) as sock:
                            sock.sendall("0,0,0".encode("utf-8"))
                        stopped_count += 1
                        self._log(f"Emergency stop sent to {d['Host']}", "success")
                    except Exception as e:
                        self._log(f"Failed to stop {d['Host']}: {e}", "error")
                
                self.call_from_thread(self._set_operation,
                    "Adhesive Emergency Stop",
                    f"[b #ff5555]EMERGENCY STOP COMPLETED[/b #ff5555]\n\n"
                    f"Stopped {stopped_count}/{len(devices)} device(s)\n\n"
                    "System status: SAFE STATE\n\n"
                    "[dim]Check all devices before resuming operations.[/dim]\n"
                    "[dim]Verify all motors are stopped and pressure is released.[/dim]"
                )
            except Exception as e:
                self._log(f"Emergency stop failed: {e}", "error")
                self.call_from_thread(self._set_operation,
                    "Adhesive Emergency Stop",
                    f"[b #ff5555]EMERGENCY STOP ERROR[/b #ff5555]\n\n"
                    f"Error: {e}\n\n"
                    "[#ff5555]Manually verify all devices are stopped![/#ff5555]"
                )
        
        thread = threading.Thread(target=emergency_stop_task, daemon=True)
        thread.start()

    async def _do_tracking(self, mode: str) -> None:
        """Start tracking operation."""
        mode_names = {
            "aruco": "Aruco Marker",
            "holes": "Hole Detection",
            "combined": "Combined Aruco + Holes"
        }
        mode_name = mode_names.get(mode, mode)
        
        devices = self.appstate.get("selected_devices", [])
        component = self.appstate.get("selected_component")
        
        if not devices:
            self._log("No devices selected", "warning")
            self._set_operation(
                f"{mode_name} Tracking",
                "[#ff5555]No devices selected.[/#ff5555]\n\n"
                "Please run [b]Discover robots[/b] first."
            )
            return
        
        if not component:
            self._log("No component selected", "warning")
            self._set_operation(
                f"{mode_name} Tracking",
                "[#ff5555]No component selected.[/#ff5555]\n\n"
                "Please select a component first from [b]Component[/b] menu."
            )
            return
        
        self._log(f"Starting {mode_name} tracking on {len(devices)} device(s)...", "info")
        self._set_operation(
            f"{mode_name} Tracking",
            f"[b]Starting {mode_name} Tracking[/b]\n\n"
            f"Devices: {len(devices)}\n"
            f"Component: {component.aruco.id}\n\n"
            "[dim]Launching tracking on remote devices...[/dim]\n\n"
            "This will:\n"
            "  • Start camera feeds on remote robots\n"
            "  • Process images for detection\n"
            "  • Stream position data via UDP\n"
            "  • Display live data\n\n"
            "[dim]Tracking operation in progress...[/dim]"
        )
        
        # Run tracking in background
        def tracking_task():
            try:
                server = self.appstate.get("server")
                aruco = component.aruco
                
                # Clear old messages and start logging
                if server:
                    server.clear()
                    if self.appstate.get("logging"):
                        log_prefix = self.appstate.get("log_prefix", "LogTesting")
                        server.start_logging(f"{log_prefix}_Combined")
                    
                    # Configure filters for aruco data
                    server.add_filter(tag="aruco", keys=("data", aruco.id, "distance"), delta_threshold=0.75)
                    server.add_filter(tag="aruco", keys=("data", aruco.id, "tvec"), delta_threshold=0.5)
                    server.add_filter(tag="aruco", keys=("data", aruco.id, "rvec"), delta_threshold=0.2)
                
                # Launch tracking on all devices
                threads = []
                all_success = True
                
                for d in devices:
                    self._log(f"Launching tracking on {d['Host']}...", "info")
                    success, thread = launch_remote_file(
                        device=d,
                        remote_python_file="~/Documents/LightsOff_Project/cambots/CameraTracking/track_both.py"
                    )
                    if success:
                        threads.append(thread)
                    else:
                        all_success = False
                        self._log(f"Failed to start tracking on {d['Host']}", "error")
                
                time.sleep(2)  # Wait for startup
                
                if all_success:
                    self._log("Tracking started successfully on all devices", "success")
                    self.call_from_thread(self._set_operation,
                        f"{mode_name} Tracking - Active",
                        f"[#50fa7b]✓[/#50fa7b] Tracking active on {len(devices)} device(s)\n\n"
                        f"Component Aruco ID: {aruco.id}\n"
                        "Status: RUNNING\n\n"
                        "[dim]Data is being collected and filtered via UDP.[/dim]\n"
                        "[dim]Check status log for tracking updates.[/dim]\n\n"
                        "[b]Note:[/b] Use the dashboard to monitor. Press Q to quit dashboard when done.\n"
                        "[dim]To stop tracking, restart the dashboard or manually stop remote processes.[/dim]"
                    )
                else:
                    self._log("Tracking started with errors", "warning")
                    self.call_from_thread(self._set_operation,
                        f"{mode_name} Tracking - Partial",
                        f"[#f1fa8c]⚠[/#f1fa8c] Tracking started on some devices\n\n"
                        "Check status log for details on failed devices.\n\n"
                        "[dim]Some robots may not be tracking properly.[/dim]"
                    )
                    
            except Exception as e:
                self._log(f"Tracking failed: {e}", "error")
                self.call_from_thread(self._set_operation,
                    f"{mode_name} Tracking Failed",
                    f"[#ff5555]Error:[/#ff5555] {e}\n\n"
                    "Please check:\n"
                    "  • Device connectivity\n"
                    "  • Camera availability\n"
                    "  • Tracking scripts exist"
                )
        
        thread = threading.Thread(target=tracking_task, daemon=True)
        thread.start()

    async def _do_position_crane(self) -> None:
        """Position the crane."""
        self._log("Crane positioning", "info")
        
        component = self.appstate.get("selected_component")
        
        if not component:
            self._set_operation(
                "Position Crane",
                "[#ff5555]No component selected.[/#ff5555]\n\n"
                "Please select a component first from [b]Component[/b] menu."
            )
            return
        
        positions = component.positions
        
        self._set_operation(
            "Position Crane",
            "[b]Crane Positioning[/b]\n\n"
            "Target positions for current component:\n\n"
            f"  • Coarse: {positions.coarse}\n"
            f"  • Intermediate: {positions.intermediate}\n"
            f"  • Fine: {positions.fine}\n"
            f"  • Target: {positions.target}\n\n"
            "[dim]Positioning sequence:[/dim]\n"
            "  1. Move to coarse position\n"
            "  2. Move to intermediate position\n"
            "  3. Move to fine position\n"
            "  4. Reach target position\n\n"
            "[dim]Crane control integration in progress...[/dim]"
        )

    async def _do_crane_home(self) -> None:
        """Move crane to home position."""
        self._log("Moving to home position", "info")
        self._set_operation(
            "Crane Home Position",
            "[b]Crane Home Position[/b]\n\n"
            "Home position: (0, 0, 50, 0, 0, 0)\n\n"
            "Moving crane to safe home position...\n\n"
            "[dim]This will:[/dim]\n"
            "  • Move crane to predefined home coordinates\n"
            "  • Ensure safe clearance from obstacles\n"
            "  • Ready for next operation\n\n"
            "[dim]Crane control integration in progress...[/dim]"
        )

    async def _do_crane_stop(self) -> None:
        """Emergency stop for crane."""
        self._log("CRANE EMERGENCY STOP activated", "error")
        self._set_operation(
            "Crane Emergency Stop",
            "[b #ff5555]CRANE EMERGENCY STOP ACTIVATED[/b #ff5555]\n\n"
            "All crane operations halted immediately:\n"
            "  • Crane movement STOPPED\n"
            "  • All motors DISENGAGED\n"
            "  • Tracking PAUSED\n"
            "  • System in SAFE STATE\n\n"
            "[#ff5555]⚠ EMERGENCY STOP ACTIVE ⚠[/#ff5555]\n\n"
            "[dim]Reset required before resuming operations.[/dim]\n"
            "[dim]Verify crane position and surroundings before restarting.[/dim]"
        )


# ─── Bootstrap ────────────────────────────────────────────────────────────────


def build_initial_appstate() -> Dict[str, Any]:
    """Build initial application state."""
    try:
        devices = get_devices()
    except Exception:
        devices = []

    # Initialize UDP server
    server = UDPServer()
    try:
        server.start_server()
    except Exception as e:
        print(f"Warning: Could not start UDP server: {e}")

    return {
        "logging": True,
        "log_prefix": "LogTesting",
        "server": server,
        "crane": None,
        "selected_component": None,
        "selected_devices": devices,
        "last_event": (
            f"Found {len(devices)} device(s) on startup."
            if devices
            else "No devices found on startup."
        ),
    }


def main():
    """Main entry point."""
    appstate = build_initial_appstate()
    app = LightsOffDashboard(appstate)
    app.run()


if __name__ == "__main__":
    main()
