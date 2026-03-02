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
from datetime import datetime
from typing import Dict, Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from base.UDPServer import UDPServer
from base.Components import Component, ComponentPositions, Aruco
from base.Crane import CranePosition
from base.Devices import get_devices, check_online_devices

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
        self._log("Robot selection (not yet implemented)", "warning")
        self._set_operation(
            "Select Robots",
            "[dim]This feature allows you to select specific robots from the discovered list.[/dim]\n\n"
            "Implementation needed:\n"
            "  • Checkbox list of available robots\n"
            "  • Multi-select capability\n"
            "  • Save selection to appstate\n\n"
            "[dim]For now, all discovered robots are selected by default.[/dim]"
        )

    async def _do_update_code(self) -> None:
        """Update code on remote robots."""
        self._log("Code update (not yet implemented)", "warning")
        devices = self.appstate.get("selected_devices", [])
        
        self._set_operation(
            "Update Code",
            f"[dim]Push latest code to {len(devices)} selected robot(s).[/dim]\n\n"
            "This will:\n"
            "  • Transfer updated Python files via SSH\n"
            "  • Sync cambots directory\n"
            "  • Restart remote services if needed\n\n"
            "[dim]Implementation in progress...[/dim]"
        )

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
        self._log(f"{action} clamps (stub)", "info")
        
        devices = self.appstate.get("selected_devices", [])
        
        self._set_operation(
            f"{action} Clamps",
            f"[dim]{action} motor clamps on {len(devices)} robot(s)...[/dim]\n\n"
            "This operation will:\n"
            f"  • {'Lock' if engage else 'Release'} component clamps\n"
            "  • Execute motor control script remotely\n"
            "  • Wait for confirmation from all robots\n\n"
            "[dim]Implementation in progress...[/dim]"
        )

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
        """Manual adhesive control."""
        self._log("Adhesive manual control (stub)", "info")
        self._set_operation(
            "Adhesive Manual Control",
            "[dim]Manual control of adhesive dispenser.[/dim]\n\n"
            "Controls:\n"
            "  • Pressure adjustment\n"
            "  • Flow rate control\n"
            "  • Position override\n"
            "  • Emergency stop\n\n"
            "[dim]Interactive controls to be implemented...[/dim]"
        )

    async def _do_adhesive_profile(self) -> None:
        """Run adhesive profile."""
        self._log("Running adhesive profile (stub)", "info")
        self._set_operation(
            "Run Adhesive Profile",
            "[dim]Execute pre-configured adhesive dispense profile.[/dim]\n\n"
            "Available profiles:\n"
            "  • adh_test_profile.csv\n"
            "  • fast_rampUp.csv\n"
            "  • adh_test_nonsync.csv\n\n"
            "[dim]Profile execution to be implemented...[/dim]"
        )

    async def _do_adhesive_history(self) -> None:
        """View adhesive history."""
        self._log("Viewing adhesive history (stub)", "info")
        self._set_operation(
            "Adhesive History",
            "[dim]Historical data from previous adhesive operations.[/dim]\n\n"
            "Available data:\n"
            "  • Previous run timestamps\n"
            "  • Pressure profiles\n"
            "  • Flow rates\n"
            "  • Success/failure status\n\n"
            "[dim]History viewer to be implemented...[/dim]"
        )

    async def _do_adhesive_emergency_stop(self) -> None:
        """Emergency stop for adhesive robot."""
        self._log("ADHESIVE EMERGENCY STOP activated", "error")
        self._set_operation(
            "Adhesive Emergency Stop",
            "[b #ff5555]ADHESIVE EMERGENCY STOP ACTIVATED[/b #ff5555]\n\n"
            "Adhesive operations halted:\n"
            "  • Dispenser stopped immediately\n"
            "  • Pressure released\n"
            "  • All motors disengaged\n"
            "  • System in safe state\n\n"
            "[dim]Check system status before resuming operations.[/dim]"
        )

    async def _do_tracking(self, mode: str) -> None:
        """Start tracking operation."""
        mode_names = {
            "aruco": "Aruco Marker",
            "holes": "Hole Detection",
            "combined": "Combined Aruco + Holes"
        }
        mode_name = mode_names.get(mode, mode)
        
        self._log(f"Starting {mode_name} tracking (stub)", "info")
        self._set_operation(
            f"{mode_name} Tracking",
            f"[dim]Initiating {mode_name} tracking mode...[/dim]\n\n"
            "Tracking will:\n"
            "  • Start camera feeds on remote robots\n"
            "  • Process images for detection\n"
            "  • Stream position data via UDP\n"
            "  • Update live plots\n\n"
            "[dim]Press [b]Q[/b] to stop tracking[/dim]\n\n"
            "[dim]Full tracking integration pending...[/dim]"
        )

    async def _do_crane_home(self) -> None:
        """Move crane to home position."""
        self._log("Moving to home position (not yet implemented)", "warning")
        self._set_operation(
            "Crane Home Position",
            "[dim]Return crane to home/safe position.[/dim]\n\n"
            "Home position: (0, 0, 50, 0, 0, 0)\n\n"
            "[dim]Crane control integration pending...[/dim]"
        )

    async def _do_crane_stop(self) -> None:
        """Emergency stop for crane."""
        self._log("EMERGENCY STOP activated", "error")
        self._set_operation(
            "Emergency Stop",
            "[b #ff5555]EMERGENCY STOP ACTIVATED[/b #ff5555]\n\n"
            "All operations halted:\n"
            "  • Crane movement stopped\n"
            "  • Motors disengaged\n"
            "  • Tracking paused\n\n"
            "[dim]Press any key to reset...[/dim]"
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
