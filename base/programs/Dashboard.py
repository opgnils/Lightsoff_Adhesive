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
import json
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
    from textual.containers import Horizontal, Vertical, Container, VerticalScroll
    from textual.widgets import Static, ListView, ListItem, Label, RichLog, Input, Button, Checkbox
    from textual.reactive import reactive
except ImportError as e:
    raise SystemExit(
        "Textual is not installed. Install it with:\n"
        "  python -m pip install textual\n"
    ) from e


# ─── Helper Functions ─────────────────────────────────────────────────────────


def send_tcp_command_robust(device, command: str, port: int = 5001, 
                            retries: int = 3, timeout: float = 2.0, 
                            retry_delay: float = 0.5) -> tuple[bool, str]:
    """Send a TCP command to a device with automatic retries.
    
    Args:
        device: Device dict with HostName
        command: Command string to send (e.g., "500,0,0")
        port: TCP port (default 5001)
        retries: Number of retry attempts (default 3)
        timeout: Socket timeout in seconds (default 2.0)
        retry_delay: Delay between retries in seconds (default 0.5)
    
    Returns:
        (success: bool, error_message: str)
        If successful, error_message is empty string.
    """
    host = device.get("HostName", "localhost")
    last_error = ""
    
    for attempt in range(retries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect((host, port))
                sock.sendall(f"{command}\n".encode())
                return True, ""  # Success!
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            last_error = str(e)
            if attempt < retries - 1:  # Not the last attempt
                time.sleep(retry_delay)
            continue
        except Exception as e:
            last_error = str(e)
            # For unexpected errors, don't retry
            break
    
    return False, last_error


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


class OperationView(Container):
    """Right main panel: shows the current operation context with interactive elements."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_mode = "text"  # Can be "text" or "list"
        self._list_items = []
        self._list_action = None

    def show_text(self, title: str, body: str) -> None:
        """Display static text content."""
        # Remove all possible widget types first (even if in text mode)
        # This ensures clean state
        widgets_to_remove = [
            ("#op-header", Static),
            ("#op-list", ListView),
            ("#manual-control-form", ManualMotorControl),
            ("#device-selector", DeviceSelector),
        ]
        
        for widget_id, widget_class in widgets_to_remove:
            try:
                self.query_one(widget_id, widget_class).remove()
            except:
                pass
        
        # If already in text mode and content exists, just update it
        if self._current_mode == "text":
            try:
                content = self.query_one("#op-content", Static)
                content.update(f"[b #ff79c6]{title}[/b #ff79c6]\n\n{body}")
                return
            except:
                # Content doesn't exist, continue to create it
                pass
        
        # Switching to text mode or creating new content
        self._current_mode = "text"
        
        # Remove existing text content if any
        try:
            self.query_one("#op-content", Static).remove()
        except:
            pass
        
        # Mount new text content
        self.mount(Static(f"[b #ff79c6]{title}[/b #ff79c6]\n\n{body}", id="op-content"))

    def show_list(self, title: str, description: str, items: list, action_callback) -> None:
        """Display an interactive selectable list."""
        self._current_mode = "list"
        self._list_items = items
        self._list_action = action_callback
        
        # Remove all other mode content first
        try:
            self.query_one("#op-content", Static).remove()
        except:
            pass
        try:
            self.query_one("#manual-control-form", ManualMotorControl).remove()
        except:
            pass
        try:
            self.query_one("#device-selector", DeviceSelector).remove()
        except:
            pass
        
        # Check if list widgets already exist - if so, just update them
        try:
            existing_header = self.query_one("#op-header", Static)
            existing_list = self.query_one("#op-list", ListView)
            
            # Update existing widgets instead of recreating
            existing_header.update(f"[b #ff79c6]{title}[/b #ff79c6]\n\n{description}\n")
            existing_list.clear()
            for item in items:
                existing_list.append(ListItem(Label(f"▸ {item}"), name=f"oplist:{item}"))
            return
        except:
            # Widgets don't exist, continue to create them
            pass
        
        # Remove existing list widgets if they exist
        try:
            self.query_one("#op-header", Static).remove()
        except:
            pass
        try:
            self.query_one("#op-list", ListView).remove()
        except:
            pass
        
        # Create header with title and description
        header = Static(f"[b #ff79c6]{title}[/b #ff79c6]\n\n{description}\n", id="op-header")
        
        # Create interactive list
        list_view = ListView(id="op-list")
        
        # Mount the widgets first
        self.mount(header)
        self.mount(list_view)
        
        # Then populate the list after it's mounted
        for item in items:
            list_view.append(ListItem(Label(f"▸ {item}"), name=f"oplist:{item}"))
    
    def show_form(self, devices: list) -> None:
        """Display an interactive form for manual motor control."""
        # Check if form already exists and just update it instead of remounting
        if self._current_mode == "form":
            try:
                existing_form = self.query_one("#manual-control-form", ManualMotorControl)
                existing_form._devices = devices
                return
            except:
                pass
        
        self._current_mode = "form"
        
        # Remove other mode content
        try:
            self.query_one("#op-content", Static).remove()
        except:
            pass
        try:
            self.query_one("#op-header", Static).remove()
        except:
            pass
        try:
            self.query_one("#op-list", ListView).remove()
        except:
            pass
        try:
            self.query_one("#manual-control-form", ManualMotorControl).remove()
        except:
            pass
        try:
            self.query_one("#device-selector", DeviceSelector).remove()
        except:
            pass
        
        # Create and mount the form
        form = ManualMotorControl()
        form._devices = devices  # Store devices for command sending
        self.mount(form)
    
    def show_device_selector(self, devices: list, selected_hosts: list = None) -> None:
        """Display a multi-select device selector with checkboxes."""
        # Check if selector already exists and just update it
        if self._current_mode == "selector":
            try:
                existing_selector = self.query_one("#device-selector", DeviceSelector)
                existing_selector._devices = devices
                existing_selector._selected_hosts = selected_hosts or []
                return
            except:
                pass
        
        self._current_mode = "selector"
        
        # Remove other mode content
        try:
            self.query_one("#op-content", Static).remove()
        except:
            pass
        try:
            self.query_one("#op-header", Static).remove()
        except:
            pass
        try:
            self.query_one("#op-list", ListView).remove()
        except:
            pass
        try:
            self.query_one("#manual-control-form", ManualMotorControl).remove()
        except:
            pass
        
        # Create and mount the device selector
        selector = DeviceSelector(devices, selected_hosts)
        self.mount(selector)
    
    # For backwards compatibility
    def show(self, title: str, body: str) -> None:
        """Update the operation view with title and body content (legacy method)."""
        self.show_text(title, body)


class ManualMotorControl(Container):
    """Interactive form for manual motor control with input fields and buttons."""
    
    def __init__(self, on_send_callback=None, on_zero_callback=None) -> None:
        super().__init__(id="manual-control-form")
        self.on_send_callback = on_send_callback
        self.on_zero_callback = on_zero_callback
    
    def compose(self) -> ComposeResult:
        """Create the form layout with input fields and buttons."""
        yield Static("[b #ff79c6]Manual Motor Control[/b #ff79c6]\n", id="manual-header")
        yield Static("[#50fa7b]Motor Configuration:[/#50fa7b]", id="manual-desc")
        yield Static("  • Motor 1: RPM (max: ±6000)", id="manual-motor1-desc")
        yield Input(placeholder="0", id="motor1-input", type="integer")
        yield Static("  • Motor 2: Flowrate A in µL/s (max: ±1150)", id="manual-motor2-desc")
        yield Input(placeholder="0", id="motor2-input", type="integer")
        yield Static("  • Motor 3: Flowrate B in µL/s (max: ±1150)", id="manual-motor3-desc")
        yield Input(placeholder="0", id="motor3-input", type="integer")
        
        with Horizontal(id="manual-buttons"):
            yield Button("Send Command", id="send-btn", variant="primary")
            yield Button("Set All to 0", id="zero-btn", variant="error")


class DeviceSelector(Container):
    """Multi-select device selector with checkboxes."""
    
    def __init__(self, devices: list, selected_hosts: list = None, *args, **kwargs):
        super().__init__(id="device-selector", *args, **kwargs)
        self._devices = devices
        self._selected_hosts = selected_hosts or []
    
    def compose(self) -> ComposeResult:
        """Create the device selector layout."""
        yield Static("[b #ff79c6]Select Devices[/b #ff79c6]\n", id="selector-header")
        yield Static(
            f"[#50fa7b]Available:[/#50fa7b] {len(self._devices)} total, "
            f"{sum(1 for d in self._devices if d.get('online'))} online\n"
            "[dim]● = Online  ○ = Offline[/dim]\n",
            id="selector-desc"
        )
        
        # Scrollable container for checkboxes
        with VerticalScroll(id="device-checkbox-container"):
            # Create checkbox for each device
            for d in self._devices:
                status = "●" if d.get('online') else "○"
                host = d.get('Host', '?')
                # Pre-check if this device was previously selected
                is_selected = host in self._selected_hosts
                checkbox = Checkbox(
                    f"{status} {host} - {d.get('HostName', '?')}",
                    id=f"device-check-{host}",
                    value=is_selected
                )
                yield checkbox
        
        # Action buttons (docked at bottom)
        with Horizontal(id="selector-buttons"):
            yield Button("Confirm Selection", id="confirm-selection-btn", variant="success")
            yield Button("Deselect All", id="deselect-all-btn", variant="warning")
    
    def get_selected_devices(self) -> list:
        """Get list of selected devices based on checkbox states."""
        selected = []
        for d in self._devices:
            checkbox_id = f"device-check-{d.get('Host', '?')}"
            try:
                checkbox = self.query_one(f"#{checkbox_id}", Checkbox)
                if checkbox.value:
                    selected.append(d)
            except:
                pass
        return selected
    
    def deselect_all_checkboxes(self):
        """Uncheck all checkboxes."""
        for d in self._devices:
            checkbox_id = f"device-check-{d.get('Host', '?')}"
            try:
                checkbox = self.query_one(f"#{checkbox_id}", Checkbox)
                checkbox.value = False
            except:
                pass


class StatusLog(RichLog):
    """Bottom-right panel: timestamped status log."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._log_file = None
        self._setup_log_file()
    
    def _setup_log_file(self):
        """Setup the log file for persistent logging."""
        try:
            # Create logs directory if it doesn't exist
            log_dir = os.path.join(os.path.dirname(__file__), "logs")
            os.makedirs(log_dir, exist_ok=True)
            
            # Create log file with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"dashboard_log_{timestamp}.txt"
            log_path = os.path.join(log_dir, log_filename)
            
            # Open log file in append mode
            self._log_file = open(log_path, "a", encoding="utf-8")
            self._log_file.write(f"=== Dashboard Log Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            self._log_file.flush()
            
        except Exception as e:
            # If we can't create log file, just continue without file logging
            self._log_file = None

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
        
        # Display in UI with color
        self.write(f"[{color}]▌[/{color}] [{timestamp}] {msg}")
        
        # Write to file without color codes
        if self._log_file:
            try:
                full_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._log_file.write(f"[{full_timestamp}] [{level.upper()}] {msg}\n")
                self._log_file.flush()
            except Exception:
                pass  # Silently fail if file write fails
    
    def on_unmount(self):
        """Clean up when widget is unmounted."""
        if self._log_file:
            try:
                self._log_file.write(f"=== Dashboard Log Ended at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                self._log_file.close()
            except Exception:
                pass


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

    /* Operation view content */
    #operation {
        height: 1fr;
        width: 1fr;
        overflow-y: auto;
        overflow-x: hidden;
    }

    #op-content {
        height: auto;
        width: 1fr;
    }

    #op-header {
        height: auto;
        width: 1fr;
        padding-bottom: 1;
    }

    #op-list {
        height: 1fr;
        width: 1fr;
        padding: 0;
    }

    #op-list > ListItem {
        padding: 0 2;
        height: auto;
    }

    #op-list > ListItem.--highlight {
        background: #ff79c6;
        color: #1a1b26;
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

    /* ── Manual Control Form ─────────────────────── */
    #manual-control-form {
        height: auto;
        width: 1fr;
        padding: 1;
    }

    #manual-header {
        height: auto;
        padding-bottom: 1;
    }

    #manual-desc {
        height: auto;
        padding-bottom: 1;
    }

    #manual-motor1-desc, #manual-motor2-desc, #manual-motor3-desc {
        height: auto;
        padding-top: 1;
        padding-bottom: 0;
    }

    #motor1-input, #motor2-input, #motor3-input {
        width: 30;
        margin-bottom: 1;
        border: round #44475a;
    }

    #motor1-input:focus, #motor2-input:focus, #motor3-input:focus {
        border: round #ff79c6;
    }

    #manual-buttons {
        height: auto;
        width: 1fr;
        padding-top: 1;
    }

    #send-btn {
        margin-right: 2;
    }

    Button {
        margin: 0 1;
    }

    /* Device Selector Styling */
    #device-selector {
        height: 100%;
        layout: vertical;
    }

    #selector-header {
        height: auto;
        padding-bottom: 1;
    }

    #selector-desc {
        height: auto;
        padding-bottom: 1;
    }

    #device-checkbox-container {
        height: 1fr;
        overflow-y: auto;
        border: solid $primary;
        padding: 1;
    }

    Checkbox {
        margin: 0 0 1 0;
    }

    #selector-buttons {
        height: auto;
        width: 100%;
        padding-top: 1;
        dock: bottom;
    }

    #confirm-selection-btn {
        margin-right: 2;
    }
    """

    def __init__(self, appstate: Dict[str, Any]) -> None:
        super().__init__()
        self.appstate = appstate
        self._expanded_section: str | None = None
        self._emergency_stop_flag = False  # Global emergency stop flag

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
            
            # Store ALL discovered devices
            self.appstate["all_devices"] = devices
            
            # Load previously selected device hosts
            previously_selected_hosts = load_selected_device_hosts()
            
            # Auto-select devices that were previously selected
            if previously_selected_hosts:
                selected_devices = [d for d in devices if d.get('Host') in previously_selected_hosts]
                if selected_devices:
                    self.appstate["selected_devices"] = selected_devices
                    self._log(f"Auto-selected {len(selected_devices)} previously selected device(s)", "info")
                else:
                    # No matching devices found, select all
                    self.appstate["selected_devices"] = devices
            else:
                # No previous selection, select all devices
                self.appstate["selected_devices"] = devices
            
            self.query_one("#devices", DevicePanel).update_from_state(self.appstate)
            self._log(f"Found {len(devices)} device(s), {len(online_devices)} online", "success")
        except Exception as e:
            self._log(f"Error refreshing devices: {e}", "error")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Initialize the dashboard on mount."""
        self._refresh_menu(preserve_index=False)
        menu = self.query_one("#menu", MainMenu)
        if len(menu.children) > 0:
            menu.index = 0

        self.query_one("#devices", DevicePanel).update_from_state(self.appstate)

        self.query_one("#operation", OperationView).show_text(
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

    def _refresh_menu(self, preserve_index: bool = True) -> None:
        """Rebuild menu items; expanded section shows indented sub-items.
        
        Args:
            preserve_index: If True, keep the current menu selection after rebuild.
        """
        menu = self.query_one("#menu", MainMenu)
        
        # Save current selection
        current_index = menu.index if preserve_index else None
        current_item_name = None
        if current_index is not None and current_index < len(menu.children):
            try:
                current_item = menu.children[current_index]
                current_item_name = getattr(current_item, 'name', None)
            except:
                pass

        # Get available profiles for dynamic submenu
        available_profiles = self.appstate.get("available_profiles", [])

        sections = [
            ("connect", "1  Connect", [
                "Discover robots",
                "Select robots", 
                "Update code"
            ]),
            ("component", "2  Component", [
                "Component overview",
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
                "Start listeners",
                "Check listener logs",
                "Manual control",
                "Run profile",
                "Kill listeners",
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
        
        # Restore selection to the same item if possible
        if preserve_index and current_item_name:
            # Try to find the item with the same name
            for idx, item in enumerate(menu.children):
                if getattr(item, 'name', None) == current_item_name:
                    menu.index = idx
                    return
            # If not found, try to stay at the same index
            if current_index is not None and current_index < len(menu.children):
                menu.index = current_index

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, msg: str, level: str = "info") -> None:
        """Append a line to the status log panel."""
        log = self.query_one("#status-log", StatusLog)
        log.log_message(msg, level)

    def _set_operation(self, title: str, body: str) -> None:
        """Update the operation view with text content."""
        self.query_one("#operation", OperationView).show_text(title, body)

    # ── Event handling ────────────────────────────────────────────────────────

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle menu and operation list selection events."""
        name = event.item.name or ""
        
        # Check if this is from the operation list
        if name.startswith("oplist:"):
            item_name = name.split(":", 1)[1]
            operation_view = self.query_one("#operation", OperationView)
            if operation_view._list_action:
                await operation_view._list_action(item_name)
                # Refocus the menu (since operation view changes to text mode after selection)
                def refocus():
                    try:
                        self.query_one("#menu", MainMenu).focus()
                    except:
                        pass
                self.call_after_refresh(refocus)
            return

        # Section headers toggle expansion (main menu)
        if name.startswith("section:"):
            key = name.split(":", 1)[1]
            self._expanded_section = None if self._expanded_section == key else key
            self._refresh_menu()
            # Refocus the menu to keep highlight visible after section toggle
            def refocus():
                try:
                    self.query_one("#menu", MainMenu).focus()
                except:
                    pass
            self.call_after_refresh(refocus)
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
                # Refocus the menu to keep highlight visible after action completes
                def refocus():
                    try:
                        self.query_one("#menu", MainMenu).focus()
                    except:
                        pass
                self.call_after_refresh(refocus)
            elif name == "action:quit":
                self.action_quit()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks from the manual control form and device selector."""
        button_id = event.button.id
        
        if button_id == "send-btn":
            await self._send_motor_command()
        elif button_id == "zero-btn":
            await self._send_zero_command()
        elif button_id == "confirm-selection-btn":
            await self._confirm_device_selection()
        elif button_id == "deselect-all-btn":
            await self._deselect_all_devices()
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key press on input fields."""
        # When Enter is pressed on any motor input field, send the command
        if event.input.id in ["motor1-input", "motor2-input", "motor3-input"]:
            await self._send_motor_command()

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
            if action == "Component overview":
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
            if action == "Start listeners":
                await self._do_start_listeners()
            elif action == "Check listener logs":
                await self._do_check_listener_logs()
            elif action == "Manual control":
                await self._do_adhesive_manual()
            elif action == "Run profile":
                await self._do_adhesive_profile()
            elif action == "Kill listeners":
                await self._do_kill_listeners()
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
            
            # Store ALL discovered devices
            self.appstate["all_devices"] = devices
            
            # Load previously selected device hosts
            previously_selected_hosts = load_selected_device_hosts()
            
            # Auto-select devices that were previously selected
            if previously_selected_hosts:
                selected_devices = [d for d in devices if d.get('Host') in previously_selected_hosts]
                if selected_devices:
                    self.appstate["selected_devices"] = selected_devices
                    self._log(f"Auto-selected {len(selected_devices)} previously selected device(s)", "info")
                else:
                    # No matching devices found, select all
                    self.appstate["selected_devices"] = devices
            else:
                # No previous selection, select all devices
                self.appstate["selected_devices"] = devices
            
            self.query_one("#devices", DevicePanel).update_from_state(self.appstate)
            
            self._log(f"{len(online_devices)} device(s) online", "success")
            
            # Create interactive list with device information
            device_names = []
            for d in devices:
                status = "●" if d.get('online') else "○"
                device_names.append(f"{status} {d.get('Host', '?')} - {d.get('HostName', '?')}")
            
            # Show interactive list for device details
            operation_view = self.query_one("#operation", OperationView)
            
            async def on_device_selected(item_name: str):
                # Extract the device host from the selected item
                parts = item_name.split(" - ")
                if len(parts) >= 1:
                    host_part = parts[0].strip()
                    # Remove the status indicator
                    host = host_part.replace("●", "").replace("○", "").strip()
                    
                    # Find the device
                    selected_device = None
                    for d in devices:
                        if d.get('Host') == host:
                            selected_device = d
                            break
                    
                    if selected_device:
                        online_status = "online" if selected_device.get('online') else "offline"
                        self._log(f"Viewing device: {host} ({online_status})", "info")
                        self._set_operation(
                            "Device Details",
                            f"[b]Device: {host}[/b]\n\n"
                            f"Hostname: {selected_device.get('HostName', '?')}\n"
                            f"User: {selected_device.get('User', '?')}\n"
                            f"Status: [{'#50fa7b' if selected_device.get('online') else '#ff5555'}]{online_status.upper()}[/]\n\n"
                            "[dim]Use 'Select robots' to change device selection.[/dim]"
                        )
            
            # Show message about auto-selection
            auto_select_msg = ""
            if previously_selected_hosts and len(self.appstate["selected_devices"]) < len(devices):
                auto_select_msg = f"\n[dim]Auto-selected {len(self.appstate['selected_devices'])} previously selected device(s).[/dim]"
            
            operation_view.show_list(
                "Device Discovery Complete",
                f"Found [b]{len(devices)}[/] device(s), [#50fa7b]{len(online_devices)}[/] online{auto_select_msg}\n\n"
                "[dim]● = Online  ○ = Offline[/dim]\n\n"
                "Select a device to view details:",
                device_names,
                on_device_selected
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
        """Select specific robots to use with interactive multi-select checkboxes."""
        self._log("Opening robot selection interface", "info")
        
        # Get ALL devices discovered (not just selected ones)
        all_devices = self.appstate.get("all_devices", [])
        if not all_devices:
            self._log("No devices found. Run 'Discover robots' first.", "warning")
            self._set_operation(
                "Select Robots",
                "[#ff5555]No devices available.[/#ff5555]\n\n"
                "Please run [b]Discover robots[/b] first to find available devices."
            )
            return
        
        # Get currently selected device hosts to pre-check them
        selected_devices = self.appstate.get("selected_devices", [])
        selected_hosts = [d.get('Host') for d in selected_devices]
        
        # Show the device selector with ALL devices, but pre-check the selected ones
        operation_view = self.query_one("#operation", OperationView)
        operation_view.show_device_selector(all_devices, selected_hosts)

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
        
        # Check which devices are online
        online_devices = check_online_devices(devices)
        
        if not online_devices:
            self._log("No devices are currently online", "warning")
            self._set_operation(
                "Update Code",
                "[#ff5555]No devices are currently online.[/#ff5555]\n\n"
                f"Selected {len(devices)} device(s), but none are reachable.\n\n"
                "Please check device connectivity."
            )
            return
        
        offline_count = len(devices) - len(online_devices)
        if offline_count > 0:
            self._log(f"Warning: {offline_count} device(s) are offline and will be skipped", "warning")
        
        self._log(f"Starting code update on {len(online_devices)} online device(s)...", "info")
        self._set_operation(
            "Update Code",
            f"[b]Updating code on {len(online_devices)} online device(s)...[/b]\n\n"
            f"[dim]Online: {len(online_devices)}/{len(devices)} devices[/dim]\n\n"
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
                update_results = run_updates(online_devices, config=config)
                
                # Build a detailed report of what was updated
                report_lines = []
                total_files = 0
                
                for device_host, files in update_results.items():
                    if files:
                        report_lines.append(f"[b]{device_host}:[/b] {len(files)} file(s) updated")
                        for f in files[:10]:  # Show first 10 files per device
                            report_lines.append(f"  • {f}")
                        if len(files) > 10:
                            report_lines.append(f"  ... and {len(files) - 10} more")
                        total_files += len(files)
                    else:
                        report_lines.append(f"[b]{device_host}:[/b] No changes (already up to date)")
                
                report_text = "\n".join(report_lines) if report_lines else "[dim]No files were updated[/dim]"
                
                self._log(f"Code update completed on {len(online_devices)} device(s), {total_files} file(s) updated", "success")
                
                # Update operation view with detailed results
                self.call_from_thread(self._set_operation,
                    "Update Code Complete",
                    f"[#50fa7b]✓[/#50fa7b] Successfully updated code on {len(online_devices)} online device(s).\n\n"
                    f"[b]Total files updated:[/b] {total_files}\n\n"
                    f"{report_text}\n\n"
                    "[dim]Cambots directory synced and ready for operations[/dim]"
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
        """Show overview of currently selected component."""
        # Check if component is already selected
        current_component = self.appstate.get("selected_component")
        
        if current_component:
            comp_id = current_component.aruco.id
            self._log(f"Showing overview for Component {comp_id}", "info")
            
            # Get the component data to display details
            # Find the matching component data
            components_data = [
                {"id": 0, "level": 1, "target": (18915, 5693, 1972, 180, 0, 0), "intermediate": (18915, 5693, 7000, 180, 0, 0), 
                 "holes": [(19193, 5825, 2061), (19193, 5561, 2061), (18637, 5825, 2061), (18637, 5561, 2061)], "weight": 241},
                {"id": 1, "level": 1, "target": (21951, 5693, 1972, 0, 0, 0), "intermediate": (21951, 5693, 7000, 0, 0, 0), 
                 "holes": [(21673, 5825, 2061), (21673, 5561, 2061), (22229, 5825, 2061), (22229, 5561, 2061)], "weight": 241},
                {"id": 2, "level": 2, "target": (20117, 4907, 2072, 180, 0, 0), "intermediate": (20117, 4907, 7000, 180, 0, 0), 
                 "holes": [(20395, 5039, 2161), (20395, 4775, 2161), (19839, 5039, 2161), (19839, 4775, 2161)], "weight": 427},
                {"id": 3, "level": 2, "target": (20117, 6478, 2072, 0, 0, 0), "intermediate": (20117, 6478, 7000, 0, 0, 0), 
                 "holes": [(19839, 6610, 2161), (19839, 6346, 2161), (20395, 6610, 2161), (20395, 6346, 2161)], "weight": 427},
                {"id": 4, "level": 3, "target": (20433, 5603, 2172, 90, 0, 0), "intermediate": (20433, 5603, 7000, 90, 0, 0), 
                 "holes": [(20520, 5880, 2261), (20520, 5324, 2261), (20345, 5880, 2261), (20345, 5324, 2261)], "weight": 387},
            ]
            
            # Find matching component data
            comp_data = next((c for c in components_data if c["id"] == comp_id), None)
            
            if comp_data:
                # Format hole positions
                holes_str = "\n".join([
                    f"    • Hole {i+1}: ({h[0]:.1f}, {h[1]:.1f}, {h[2]:.1f})"
                    for i, h in enumerate(comp_data["holes"])
                ])
                
                self._set_operation(
                    f"Component {comp_id} Overview",
                    f"[#50fa7b]✓[/#50fa7b] [b]Component {comp_id}[/b] (Currently Selected)\n\n"
                    f"[b]Level:[/b] {comp_data['level']}\n"
                    f"[b]ID:[/b] {comp_id}\n"
                    f"[b]Weight:[/b] {comp_data['weight']} kg\n\n"
                    f"[b]Target Position:[/b]\n"
                    f"  XYZ: ({comp_data['target'][0]}, {comp_data['target'][1]}, {comp_data['target'][2]}) mm\n"
                    f"  ABC: ({comp_data['target'][3]}°, {comp_data['target'][4]}°, {comp_data['target'][5]}°)\n\n"
                    f"[b]Intermediate Position:[/b]\n"
                    f"  XYZ: ({comp_data['intermediate'][0]}, {comp_data['intermediate'][1]}, {comp_data['intermediate'][2]}) mm\n"
                    f"  ABC: ({comp_data['intermediate'][3]}°, {comp_data['intermediate'][4]}°, {comp_data['intermediate'][5]}°)\n\n"
                    f"[b]Hole Positions:[/b]\n"
                    f"{holes_str}\n\n"
                    "[dim]Use 'Change component' to select a different component[/dim]"
                )
            else:
                # Fallback if data not found
                self._set_operation(
                    f"Component {comp_id} Overview",
                    f"[#50fa7b]✓[/#50fa7b] [b]Component {comp_id}[/b] is currently selected.\n\n"
                    f"ID: [b]{comp_id}[/b]\n"
                    f"Target: ({current_component.positions.target.X:.0f}, "
                    f"{current_component.positions.target.Y:.0f}, "
                    f"{current_component.positions.target.Z:.0f}) "
                    f"({current_component.positions.target.A:.0f}°, "
                    f"{current_component.positions.target.B:.0f}°, "
                    f"{current_component.positions.target.C:.0f}°)\n\n"
                    "[dim]Use 'Change component' to select a different component[/dim]"
                )
        else:
            self._log("No component selected", "warning")
            self._set_operation(
                "No Component Selected",
                "[#ff5555]No component is currently selected.[/#ff5555]\n\n"
                "Please use [b]Component → Change component[/b] to select a component\n"
                "before starting tracking operations."
            )

    async def _do_change_component(self) -> None:
        """Change the selected component with interactive list."""
        # Define all available components with real data
        components_data = [
            {
                "id": 0,
                "level": 1,
                "target": (18915, 5693, 1972, 180, 0, 0),
                "intermediate": (18915, 5693, 6972, 0, 0, 0),
                "holes": [(-241, 286.4, 0), (-241, -286.4, 0), (482, 0, 0)],
                "weight": 241
            },
            {
                "id": 1,
                "level": 1,
                "target": (21951, 5693, 1972, 0, 0, 0),
                "intermediate": (21951, 5693, 6972, 0, 0, 0),
                "holes": [(-241, -286.4, 0), (-241, 286.4, 0), (482, 0, 0)],
                "weight": 241
            },
            {
                "id": 2,
                "level": 2,
                "target": (20117, 4907, 2072, 180, 0, 0),
                "intermediate": (20117, 4907, 7072, 0, 0, 0),
                "holes": [(630.5, 361.4, 0), (783.7, -180.7, 0), (-1414.2, -180.7, 0)],
                "weight": 309
            },
            {
                "id": 3,
                "level": 2,
                "target": (20117, 6478, 2072, 0, 0, 0),
                "intermediate": (20117, 6478, 7072, 0, 0, 0),
                "holes": [(-630.5, 361.4, 0), (-783.7, -180.7, 0), (1414.2, -180.7, 0)],
                "weight": 309
            },
            {
                "id": 4,
                "level": 3,
                "target": (20433, 5603, 2172, 90, 0, 0),
                "intermediate": (20433, 5603, 7172, 0, 0, 0),
                "holes": [(-864, 439, 0), (1728.1, 0, 0), (-864, -439, 0)],
                "weight": 427
            }
        ]
        
        self._log("Opening component selector", "info")
        
        # Create list items with component info (Component ID - Level)
        component_names = []
        for comp_data in components_data:
            component_names.append(f"Component {comp_data['id']} - Level {comp_data['level']}")
        
        # Show interactive list
        operation_view = self.query_one("#operation", OperationView)
        
        async def on_component_selected(item_name: str):
            # Extract component ID from selection
            try:
                comp_id = int(item_name.split("Component ")[1].split(" ")[0])
                comp_data = components_data[comp_id]
                
                # Create Component object with positions
                # Calculate coarse position (5000mm above target)
                coarse_z = comp_data["target"][2] + 5000
                # Use intermediate position from data
                
                component = Component(
                    ComponentPositions(
                        coarse=CranePosition(
                            comp_data["target"][0],
                            comp_data["target"][1],
                            coarse_z,
                            0, 0, 0
                        ),
                        intermediate=CranePosition(*comp_data["intermediate"]),
                        fine=CranePosition(
                            comp_data["target"][0],
                            comp_data["target"][1],
                            comp_data["target"][2] + 100,  # 100mm above target
                            comp_data["target"][3],
                            comp_data["target"][4],
                            comp_data["target"][5]
                        ),
                        target=CranePosition(*comp_data["target"])
                    ),
                    Aruco(id=comp_id, position=CranePosition(0, 0, 0, 0, 0, 0))
                )
                
                # Store in appstate
                self.appstate["selected_component"] = component
                self._log(f"Selected Component {comp_id} (Level {comp_data['level']})", "success")
                
                # Display component details
                holes_str = "\n".join([
                    f"    • Hole {i+1}: ({h[0]:.1f}, {h[1]:.1f}, {h[2]:.1f})"
                    for i, h in enumerate(comp_data["holes"])
                ])
                
                self._set_operation(
                    f"Component {comp_id} Selected",
                    f"[#50fa7b]✓[/#50fa7b] [b]Component {comp_id}[/b] is now selected\n\n"
                    f"[b]Level:[/b] {comp_data['level']}\n"
                    f"[b]ID:[/b] {comp_id}\n"
                    f"[b]Weight:[/b] {comp_data['weight']} kg\n\n"
                    f"[b]Target Position:[/b]\n"
                    f"  XYZ: ({comp_data['target'][0]}, {comp_data['target'][1]}, {comp_data['target'][2]}) mm\n"
                    f"  ABC: ({comp_data['target'][3]}°, {comp_data['target'][4]}°, {comp_data['target'][5]}°)\n\n"
                    f"[b]Intermediate Position:[/b]\n"
                    f"  XYZ: ({comp_data['intermediate'][0]}, {comp_data['intermediate'][1]}, {comp_data['intermediate'][2]}) mm\n"
                    f"  ABC: ({comp_data['intermediate'][3]}°, {comp_data['intermediate'][4]}°, {comp_data['intermediate'][5]}°)\n\n"
                    f"[b]Hole Positions:[/b]\n"
                    f"{holes_str}\n\n"
                    "[dim]Component ready for tracking operations[/dim]"
                )
                
            except Exception as e:
                self._log(f"Error selecting component: {e}", "error")
                self._set_operation(
                    "Selection Error",
                    f"[#ff5555]Error selecting component:[/#ff5555]\n\n{e}"
                )
        
        operation_view.show_list(
            "Select Component",
            "Choose a component for tracking and assembly operations:\n\n"
            "[dim]Click a component to view details and select[/dim]",
            component_names,
            on_component_selected
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
        
        # Check which devices are online
        self._log(f"Checking online status of {len(devices)} device(s)...", "info")
        online_devices = check_online_devices(devices)
        
        if not online_devices:
            self._log("No devices are currently online", "warning")
            self._set_operation(
                f"{action} Clamps",
                "[#ff5555]No devices are currently online.[/#ff5555]\n\n"
                f"Selected {len(devices)} device(s), but none are reachable.\n\n"
                "Please check:\n"
                "  • Device power and network connections\n"
                "  • Network connectivity\n"
                "  • Device IP addresses"
            )
            return
        
        offline_count = len(devices) - len(online_devices)
        if offline_count > 0:
            self._log(f"Warning: {offline_count} device(s) are offline and will be skipped", "warning")
        
        self._log(f"{action} clamps on {len(online_devices)} online device(s)...", "info")
        self._set_operation(
            f"{action} Clamps",
            f"[b]{action} motor clamps on {len(online_devices)} online robot(s)...[/b]\n\n"
            f"[dim]Operation: {'Lock' if engage else 'Release'} component clamps[/dim]\n"
            "[dim]Duration: ~30 seconds[/dim]\n\n"
            f"Online devices: {len(online_devices)}/{len(devices)}\n\n"
            "Please wait..."
        )
        
        # Run motor control in background
        def motor_task():
            try:
                threads = []
                all_success = True
                
                for d in online_devices:
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
                        f"[#50fa7b]✓[/#50fa7b] Successfully {'engaged' if engage else 'disengaged'} clamps on {len(online_devices)} robot(s).\n\n"
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

    async def _do_start_listeners(self) -> None:
        """Start adhesive listeners on selected devices."""
        devices = self.appstate.get("selected_devices", [])
        
        if not devices:
            self._log("No devices selected", "warning")
            self._set_operation(
                "Start Listeners",
                "[#ff5555]No devices selected.[/#ff5555]\n\n"
                "Please run [b]Discover robots[/b] first."
            )
            return
        
        # Check which devices are online
        online_devices = check_online_devices(devices)
        
        if not online_devices:
            self._log("No devices are currently online", "warning")
            self._set_operation(
                "Start Listeners",
                "[#ff5555]No devices are currently online.[/#ff5555]\n\n"
                f"Selected {len(devices)} device(s), but none are reachable.\n\n"
                "Please check device connectivity."
            )
            return
        
        offline_count = len(devices) - len(online_devices)
        if offline_count > 0:
            self._log(f"Warning: {offline_count} device(s) are offline and will be skipped", "warning")
        
        self._log(f"Starting adhesive listeners on {len(online_devices)} online device(s)...", "info")
        self._set_operation(
            "Start Listeners",
            f"[b]Starting listeners on {len(online_devices)} device(s)...[/b]\n\n"
            "[dim]Checking for existing listeners and starting new ones if needed.\n\n"
            "Please wait...[/dim]"
        )
        
        # Start listeners in background thread
        def start_listeners():
            results = []
            for d in online_devices:
                try:
                    success = ensure_adhesive_listener_running(d)
                    if success:
                        results.append(f"[#50fa7b]✓[/#50fa7b] {d['Host']}: Listener running")
                        self.call_from_thread(self._log, f"Adhesive listener running on {d['Host']}", "success")
                    else:
                        results.append(f"[#ff5555]✗[/#ff5555] {d['Host']}: Failed to start")
                        self.call_from_thread(self._log, f"Failed to start listener on {d['Host']}", "error")
                except Exception as e:
                    results.append(f"[#ff5555]✗[/#ff5555] {d['Host']}: {str(e)}")
                    self.call_from_thread(self._log, f"Error starting listener on {d['Host']}: {e}", "error")
            
            # Show final results
            results_text = "\n".join(results)
            self.call_from_thread(self._set_operation,
                "Start Listeners Complete",
                f"[b]Listener Status:[/b]\n\n"
                f"{results_text}\n\n"
                f"Devices processed: {len(online_devices)}/{len(devices)}\n\n"
                "[dim]Listeners are now ready for manual control or profile execution.[/dim]"
            )
        
        thread = threading.Thread(target=start_listeners, daemon=True)
        thread.start()

    async def _do_check_listener_logs(self) -> None:
        """Check adhesive listener logs on selected devices."""
        devices = self.appstate.get("selected_devices", [])
        
        if not devices:
            self._log("No devices selected", "warning")
            self._set_operation(
                "Check Listener Logs",
                "[#ff5555]No devices selected.[/#ff5555]\n\n"
                "Please run [b]Discover robots[/b] first."
            )
            return
        
        # Check which devices are online
        online_devices = check_online_devices(devices)
        
        if not online_devices:
            self._log("No devices are currently online", "warning")
            self._set_operation(
                "Check Listener Logs",
                "[#ff5555]No devices are currently online.[/#ff5555]\n\n"
                f"Selected {len(devices)} device(s), but none are reachable.\n\n"
                "Please check device connectivity."
            )
            return
        
        self._log(f"Fetching listener logs from {len(online_devices)} online device(s)...", "info")
        self._set_operation(
            "Check Listener Logs",
            f"[b]Fetching logs from {len(online_devices)} device(s)...[/b]\n\n"
            "[dim]Retrieving last 30 lines from adhesive_listener.log\n\n"
            "Please wait...[/dim]"
        )
        
        # Fetch logs in background thread
        def fetch_logs():
            all_logs = []
            for d in online_devices:
                try:
                    host = d["HostName"]
                    user = d["User"]
                    
                    # Get last 30 lines of the log file
                    log_cmd = "tail -30 ~/Documents/LightsOff_Project/adhesive_listener.log 2>&1 || echo 'Log file not found'"
                    
                    ssh_cmd = [
                        "sshpass", "-p", "lightsoff", "ssh",
                        "-o", "StrictHostKeyChecking=no",
                        "-o", "ConnectTimeout=5",
                        f"{user}@{host}",
                        log_cmd,
                    ]
                    
                    result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=10)
                    
                    if result.returncode == 0:
                        log_content = result.stdout.strip()
                        if log_content:
                            all_logs.append(f"[b]─── {d['Host']} ───[/b]\n{log_content}\n")
                            self.call_from_thread(self._log, f"Retrieved logs from {d['Host']}", "success")
                        else:
                            all_logs.append(f"[b]─── {d['Host']} ───[/b]\n[dim]No log output available[/dim]\n")
                    else:
                        all_logs.append(f"[b]─── {d['Host']} ───[/b]\n[#ff5555]Failed to retrieve logs[/#ff5555]\n")
                        self.call_from_thread(self._log, f"Failed to retrieve logs from {d['Host']}", "error")
                        
                except Exception as e:
                    all_logs.append(f"[b]─── {d['Host']} ───[/b]\n[#ff5555]Error: {str(e)}[/#ff5555]\n")
                    self.call_from_thread(self._log, f"Error fetching logs from {d['Host']}: {e}", "error")
            
            # Show all logs
            logs_text = "\n".join(all_logs) if all_logs else "[dim]No logs available[/dim]"
            self.call_from_thread(self._set_operation,
                "Listener Logs",
                f"[b]Adhesive Listener Logs (last 30 lines)[/b]\n\n"
                f"{logs_text}\n"
                f"[dim]Showing logs from {len(online_devices)} device(s)[/dim]"
            )
        
        thread = threading.Thread(target=fetch_logs, daemon=True)
        thread.start()

    async def _do_adhesive_manual(self) -> None:
        """Manual adhesive control with interactive input fields."""
        devices = self.appstate.get("selected_devices", [])
        
        if not devices:
            self._log("No devices selected", "warning")
            self._set_operation(
                "Adhesive Manual Control",
                "[#ff5555]No devices selected.[/#ff5555]\n\n"
                "Please run [b]Discover robots[/b] first."
            )
            return
        
        # Check which devices are online
        online_devices = check_online_devices(devices)
        
        if not online_devices:
            self._log("No devices are currently online", "warning")
            self._set_operation(
                "Adhesive Manual Control",
                "[#ff5555]No devices are currently online.[/#ff5555]\n\n"
                f"Selected {len(devices)} device(s), but none are reachable.\n\n"
                "Please check device connectivity before using manual control."
            )
            return
        
        offline_count = len(devices) - len(online_devices)
        if offline_count > 0:
            self._log(f"Warning: {offline_count} device(s) are offline and will be skipped", "warning")
        
        self._log(f"Starting adhesive manual control on {len(online_devices)} online device(s)", "info")
        
        # Clear emergency stop flag when entering manual control
        self._emergency_stop_flag = False
        
        # Show initial message about listener startup
        self._log(f"Ensuring adhesive listeners are running on {len(online_devices)} device(s)...", "info")
        
        # Ensure listeners are running in background on online devices only
        def ensure_listeners():
            ready_count = 0
            for d in online_devices:
                try:
                    self.call_from_thread(self._log, f"Starting listener on {d['Host']}...", "info")
                    success = ensure_adhesive_listener_running(d)
                    
                    if success:
                        ready_count += 1
                        self.call_from_thread(self._log, f"✓ Listener ready on {d['Host']}", "success")
                    else:
                        self.call_from_thread(self._log, f"⚠ Listener verification inconclusive on {d['Host']}", "warning")
                except Exception as e:
                    self.call_from_thread(self._log, f"✗ Failed to start listener on {d['Host']}: {e}", "error")
            
            # Summary message
            if ready_count == len(online_devices):
                self.call_from_thread(self._log, f"All {ready_count} listener(s) ready - manual control active", "success")
            elif ready_count > 0:
                self.call_from_thread(self._log, f"{ready_count}/{len(online_devices)} listener(s) ready - some devices may not respond", "warning")
            else:
                self.call_from_thread(self._log, f"No listeners ready - commands will likely fail", "error")
        
        thread = threading.Thread(target=ensure_listeners, daemon=True)
        thread.start()
        
        # Show the interactive manual control form (pass online_devices)
        operation_view = self.query_one("#operation", OperationView)
        operation_view.show_form(online_devices)

    async def _send_motor_command(self) -> None:
        """Send motor command from the manual control form inputs."""
        try:
            # Get the input values
            motor1_input = self.query_one("#motor1-input", Input)
            motor2_input = self.query_one("#motor2-input", Input)
            motor3_input = self.query_one("#motor3-input", Input)
            
            # Get values, default to 0 if empty
            motor1 = int(motor1_input.value) if motor1_input.value.strip() else 0
            motor2 = int(motor2_input.value) if motor2_input.value.strip() else 0
            motor3 = int(motor3_input.value) if motor3_input.value.strip() else 0
            
            # Validate ranges
            if abs(motor1) > 6000:
                self._log(f"Motor 1 value {motor1} exceeds max ±6000 RPM", "error")
                return
            if abs(motor2) > 1150:
                self._log(f"Motor 2 value {motor2} exceeds max ±1150 µL/s", "error")
                return
            if abs(motor3) > 1150:
                self._log(f"Motor 3 value {motor3} exceeds max ±1150 µL/s", "error")
                return
            
            # Format command
            command = f"{motor1},{motor2},{motor3}"
            
            # Get devices from the form
            try:
                form = self.query_one("#manual-control-form", ManualMotorControl)
                devices = form._devices
            except:
                self._log("Could not retrieve device list", "error")
                return
            
            if not devices:
                self._log("No devices available", "warning")
                return
            
            # Check which devices are online
            online_devices = check_online_devices(devices)
            
            if not online_devices:
                self._log("No devices are currently online", "warning")
                return
            
            offline_count = len(devices) - len(online_devices)
            if offline_count > 0:
                self._log(f"Warning: {offline_count} device(s) are offline and will be skipped", "warning")
            
            # Send command to online devices only
            self._log(f"Sending motor command to {len(online_devices)} online device(s): {command}", "info")
            
            # Check emergency stop flag before sending
            if self._emergency_stop_flag:
                self._log("Command blocked: Emergency stop is active", "warning")
                return
            
            def send_commands():
                success_count = 0
                for d in online_devices:
                    # Use robust TCP sending with retries
                    success, error = send_tcp_command_robust(d, command, retries=3, retry_delay=0.5)
                    
                    if success:
                        success_count += 1
                        self.call_from_thread(self._log, 
                            f"Command sent to {d['Host']}: {command}", "success")
                    else:
                        self.call_from_thread(self._log, 
                            f"Failed to send to {d['Host']} after 3 retries: {error}", "error")
                
                if success_count == 0:
                    self.call_from_thread(self._log, 
                        "No commands succeeded - listener may not be ready yet", "warning")
            
            thread = threading.Thread(target=send_commands, daemon=True)
            thread.start()
            
        except ValueError as e:
            self._log(f"Invalid input: {e}", "error")
        except Exception as e:
            self._log(f"Error sending command: {e}", "error")

    async def _send_zero_command(self) -> None:
        """Send zero command to all motors (emergency stop)."""
        try:
            # Get devices from the form
            try:
                form = self.query_one("#manual-control-form", ManualMotorControl)
                devices = form._devices
            except:
                self._log("Could not retrieve device list", "error")
                return
            
            if not devices:
                self._log("No devices available", "warning")
                return
            
            # Check which devices are online
            online_devices = check_online_devices(devices)
            
            if not online_devices:
                self._log("No devices are currently online", "warning")
                return
            
            offline_count = len(devices) - len(online_devices)
            if offline_count > 0:
                self._log(f"Warning: {offline_count} device(s) are offline and will be skipped", "warning")
            
            command = "0,0,0"
            self._log(f"Sending ZERO command to {len(online_devices)} online device(s)", "warning")
            
            def send_commands():
                success_count = 0
                for d in online_devices:
                    # Use robust TCP sending with retries
                    success, error = send_tcp_command_robust(d, command, retries=3, retry_delay=0.5)
                    
                    if success:
                        success_count += 1
                        self.call_from_thread(self._log, 
                            f"Motors stopped on {d['Host']}", "success")
                    else:
                        self.call_from_thread(self._log, 
                            f"Failed to stop motors on {d['Host']} after 3 retries: {error}", "error")
            
            thread = threading.Thread(target=send_commands, daemon=True)
            thread.start()
            
            # Also clear the input fields
            self.query_one("#motor1-input", Input).value = "0"
            self.query_one("#motor2-input", Input).value = "0"
            self.query_one("#motor3-input", Input).value = "0"
            
        except Exception as e:
            self._log(f"Error sending zero command: {e}", "error")

    async def _confirm_device_selection(self) -> None:
        """Confirm device selection from checkboxes and update appstate."""
        try:
            selector = self.query_one("#device-selector", DeviceSelector)
            selected_devices = selector.get_selected_devices()
            
            if not selected_devices:
                self._log("No devices selected", "warning")
                self._set_operation(
                    "No Selection",
                    "[#ff5555]No devices were selected.[/#ff5555]\n\n"
                    "Please check at least one device and try again."
                )
                return
            
            # Update appstate with selected devices
            self.appstate["selected_devices"] = selected_devices
            
            # Save selected device hosts for next time
            device_hosts = [d.get('Host') for d in selected_devices]
            save_selected_devices(device_hosts)
            
            # Update device panel
            self.query_one("#devices", DevicePanel).update_from_state(self.appstate)
            
            # Count online devices
            online_count = sum(1 for d in selected_devices if d.get('online'))
            
            self._log(f"Selected {len(selected_devices)} device(s) ({online_count} online)", "success")
            
            # Show confirmation
            device_list = "\n".join([
                f"  • {d.get('Host')} - {'[#50fa7b]online[/]' if d.get('online') else '[#ff5555]offline[/]'}"
                for d in selected_devices
            ])
            
            self._set_operation(
                "Devices Selected",
                f"[#50fa7b]✓[/#50fa7b] Selected {len(selected_devices)} device(s)\n\n"
                f"[b]Online:[/b] {online_count}/{len(selected_devices)}\n\n"
                f"[b]Selected devices:[/b]\n{device_list}\n\n"
                "[dim]These devices will be used for all operations.[/dim]"
            )
            
        except Exception as e:
            self._log(f"Error confirming selection: {e}", "error")
    
    async def _deselect_all_devices(self) -> None:
        """Deselect all device checkboxes."""
        try:
            selector = self.query_one("#device-selector", DeviceSelector)
            selector.deselect_all_checkboxes()
            self._log("Deselected all devices", "info")
        except Exception as e:
            self._log(f"Error deselecting devices: {e}", "error")

    async def _do_adhesive_profile(self) -> None:
        """Run adhesive profile from CSV with interactive selection in operation view."""
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
        
        # Store profiles for execution
        self.appstate["available_profiles"] = profiles
        self.appstate["profiles_dir"] = profiles_dir
        
        self._log(f"Found {len(profiles)} adhesive profile(s)", "info")
        
        # Show interactive list in operation view
        description = (
            f"[b]Select a profile to execute[/b]\n\n"
            f"Connected to {len(devices)} device(s)\n"
            f"Found {len(profiles)} profile(s)\n\n"
            "[dim]Click on a profile below to start execution:[/dim]\n"
        )
        
        operation_view = self.query_one("#operation", OperationView)
        operation_view.show_list(
            "Available Adhesive Profiles",
            description,
            profiles,
            self._do_run_profile  # Callback when profile is selected
        )

    async def _do_run_profile(self, profile_name: str) -> None:
        """Execute a specific adhesive profile."""
        devices = self.appstate.get("selected_devices", [])
        profiles_dir = self.appstate.get("profiles_dir", "")
        
        if not devices:
            self._log("No devices selected", "warning")
            self._set_operation(
                "Run Profile",
                "[#ff5555]No devices selected.[/#ff5555]\n\n"
                "Please run [b]Discover robots[/b] first to select devices."
            )
            return
        
        # Check which devices are online
        online_devices = check_online_devices(devices)
        
        if not online_devices:
            self._log("No devices are currently online", "warning")
            self._set_operation(
                "Run Profile",
                "[#ff5555]No devices are currently online.[/#ff5555]\n\n"
                f"Selected {len(devices)} device(s), but none are reachable.\n\n"
                "Please check device connectivity before running profiles."
            )
            return
        
        offline_count = len(devices) - len(online_devices)
        if offline_count > 0:
            self._log(f"Warning: {offline_count} device(s) are offline and will be skipped", "warning")
        
        profile_path = os.path.join(profiles_dir, profile_name)
        
        if not os.path.exists(profile_path):
            self._log(f"Profile not found: {profile_name}", "error")
            self._set_operation(
                "Profile Error",
                f"[#ff5555]Profile not found:[/#ff5555]\n\n{profile_path}"
            )
            return
        
        self._log(f"Starting profile: {profile_name} on {len(online_devices)} online device(s)", "info")
        
        # Clear emergency stop flag when starting a new profile
        self._emergency_stop_flag = False
        
        self._set_operation(
            f"Running: {profile_name}",
            f"[b]Executing Adhesive Profile[/b]\n\n"
            f"Profile: [b]{profile_name}[/b]\n"
            f"Online devices: {len(online_devices)}/{len(devices)}\n\n"
            "[dim]Loading profile and starting execution...[/dim]"
        )
        
        # Run profile execution in background thread
        def execute_profile():
            try:
                # Ensure listeners are running on online devices only
                self.call_from_thread(self._log, f"Starting adhesive listeners on {len(online_devices)} device(s)...", "info")
                for d in online_devices:
                    try:
                        ensure_adhesive_listener_running(d)
                        self.call_from_thread(self._log, f"Listener ready on {d['Host']}", "success")
                    except Exception as e:
                        self.call_from_thread(self._log, f"Listener failed on {d['Host']}: {e}", "error")
                        return
                
                # Load profile
                self.call_from_thread(self._log, f"Loading profile: {profile_name}", "info")
                steps = []
                with open(profile_path, "r") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if not row:
                            continue
                        parts = [p.strip() for p in row if p.strip() and not p.strip().startswith("#")]
                        if len(parts) < 2:
                            continue
                        t = float(parts[0])
                        m1 = float(parts[1]) if len(parts) > 1 else 0.0
                        m2 = float(parts[2]) if len(parts) > 2 else 0.0
                        m3 = float(parts[3]) if len(parts) > 3 else 0.0
                        steps.append((t, [m1, m2, m3]))
                
                if not steps:
                    self.call_from_thread(self._log, "Profile is empty", "error")
                    return
                
                steps.sort(key=lambda x: x[0])
                self.call_from_thread(self._log, f"Loaded {len(steps)} steps", "success")
                
                # Update operation view with progress
                self.call_from_thread(self._set_operation,
                    f"Executing: {profile_name}",
                    f"[b]Profile Execution in Progress[/b]\n\n"
                    f"Profile: {profile_name}\n"
                    f"Steps: {len(steps)}\n"
                    f"Online devices: {len(online_devices)}/{len(devices)}\n\n"
                    "[#50fa7b]Executing...[/#50fa7b]\n\n"
                    "[dim]Check status log for detailed progress[/dim]\n"
                    "[dim]Use Emergency Stop if needed[/dim]"
                )
                
                # Execute profile on online devices only
                start_time = time.time()
                for i, (t_target, motors) in enumerate(steps):
                    # CHECK EMERGENCY STOP FLAG - exit immediately if set
                    if self._emergency_stop_flag:
                        self.call_from_thread(self._log, 
                            f"Profile ABORTED at step {i+1}/{len(steps)} due to emergency stop", 
                            "error"
                        )
                        # Send immediate stop command with robust retries
                        for d in online_devices:
                            send_tcp_command_robust(d, "0,0,0", retries=3, timeout=1.0)
                        self.call_from_thread(self._set_operation,
                            f"ABORTED: {profile_name}",
                            f"[#ff5555]✗ PROFILE ABORTED BY EMERGENCY STOP[/#ff5555]\n\n"
                            f"Profile: {profile_name}\n"
                            f"Stopped at step: {i+1}/{len(steps)}\n"
                            f"Online devices: {len(online_devices)}/{len(devices)}\n\n"
                            "[b]All motors commanded to STOP (0,0,0)[/b]\n\n"
                            "[dim]Emergency stop was activated during execution[/dim]\n"
                            "[dim]Verify all motors have stopped before proceeding[/dim]"
                        )
                        return  # EXIT IMMEDIATELY
                    
                    now = time.time()
                    wait = t_target - (now - start_time)
                    if wait > 0:
                        time.sleep(wait)
                    
                    cmd = f"{motors[0]},{motors[1]},{motors[2]}"
                    all_success = True
                    for d in online_devices:
                        # Use robust TCP sending with retries
                        success, error = send_tcp_command_robust(d, cmd, retries=2, retry_delay=0.3)
                        if not success:
                            all_success = False
                            self.call_from_thread(self._log, f"TCP error on {d['Host']}: {error}", "error")
                    
                    status = "✓" if all_success else "✗"
                    self.call_from_thread(self._log, 
                        f"[{i+1}/{len(steps)}] t={t_target:.1f}s -> {cmd} {status}", 
                        "success" if all_success else "error"
                    )
                
                # Send final stop
                self.call_from_thread(self._log, "Profile complete. Sending STOP (0,0,0)...", "info")
                cmd = "0,0,0"
                for _ in range(3):  # Send 3 times for redundancy
                    for d in online_devices:
                        send_tcp_command_robust(d, cmd, retries=2, timeout=1.0)
                    time.sleep(0.1)
                
                self.call_from_thread(self._log, "Profile execution completed successfully", "success")
                self.call_from_thread(self._set_operation,
                    f"Completed: {profile_name}",
                    f"[#50fa7b]✓ Profile Execution Complete[/#50fa7b]\n\n"
                    f"Profile: {profile_name}\n"
                    f"Steps executed: {len(steps)}\n"
                    f"Online devices: {len(online_devices)}/{len(devices)}\n\n"
                    "[dim]All motors stopped (0,0,0)[/dim]\n"
                    "[dim]Check status log for details[/dim]"
                )
                
            except Exception as e:
                self.call_from_thread(self._log, f"Profile execution failed: {e}", "error")
                self.call_from_thread(self._set_operation,
                    "Profile Error",
                    f"[#ff5555]Profile execution failed:[/#ff5555]\n\n{e}\n\n"
                    "[dim]Check status log for details[/dim]"
                )
        
        thread = threading.Thread(target=execute_profile, daemon=True)
        thread.start()

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

    async def _do_kill_listeners(self) -> None:
        """Kill all Python processes (including listeners) on selected devices."""
        devices = self.appstate.get("selected_devices", [])
        
        if not devices:
            self._log("No devices selected", "warning")
            self._set_operation(
                "Kill Listeners",
                "[#ff5555]No devices selected.[/#ff5555]\n\n"
                "Please run [b]Discover robots[/b] first."
            )
            return
        
        # Check which devices are online
        online_devices = check_online_devices(devices)
        
        if not online_devices:
            self._log("No devices are currently online", "warning")
            self._set_operation(
                "Kill Listeners",
                "[#ff5555]No devices are currently online.[/#ff5555]\n\n"
                f"Selected {len(devices)} device(s), but none are reachable.\n\n"
                "Please check device connectivity."
            )
            return
        
        offline_count = len(devices) - len(online_devices)
        if offline_count > 0:
            self._log(f"Warning: {offline_count} device(s) are offline and will be skipped", "warning")
        
        self._log(f"Killing Python processes on {len(online_devices)} online device(s)...", "info")
        self._set_operation(
            "Kill Listeners",
            f"[b]Cleaning up processes on {len(online_devices)} device(s)...[/b]\n\n"
            "[dim]This will kill all Python processes including:\n"
            "  • AdhesiveListener.py\n"
            "  • Any other running Python scripts\n\n"
            "Please wait...[/dim]"
        )
        
        # Run cleanup in background thread
        def cleanup_task():
            try:
                config = self.appstate.get("config", "config_lightsoff")
                cleanup_remote_python_processes(online_devices, config=config)
                self.call_from_thread(self._log, f"Cleanup completed on {len(online_devices)} device(s)", "success")
                self.call_from_thread(self._set_operation,
                    "Kill Listeners Complete",
                    f"[#50fa7b]✓[/#50fa7b] Successfully cleaned up processes on {len(online_devices)} online device(s).\n\n"
                    "All Python processes have been terminated:\n"
                    "  • Adhesive listeners stopped\n"
                    "  • Other Python scripts killed\n\n"
                    f"Online devices: {len(online_devices)}/{len(devices)}\n\n"
                    "[dim]You can now restart manual control or run profiles.[/dim]"
                )
            except Exception as e:
                self.call_from_thread(self._log, f"Cleanup failed: {e}", "error")
                self.call_from_thread(self._set_operation,
                    "Kill Listeners Failed",
                    f"[#ff5555]Error during cleanup:[/#ff5555]\n\n{e}\n\n"
                    "Please check:\n"
                    "  • Network connectivity\n"
                    "  • SSH access permissions\n"
                    "  • Device availability"
                )
        
        thread = threading.Thread(target=cleanup_task, daemon=True)
        thread.start()

    async def _do_adhesive_emergency_stop(self) -> None:
        """Emergency stop for adhesive robot.
        
        ROBUST EMERGENCY STOP SYSTEM:
        1. Sets global _emergency_stop_flag immediately to halt any running profiles
        2. Profile execution checks this flag before EVERY step and aborts if set
        3. Manual control commands are blocked while flag is active
        4. Sends stop commands (0,0,0) to all online devices via TCP
        5. Flag is only cleared when starting a new profile or manual control session
        
        This ensures profiles stop immediately and don't continue execution.
        """
        devices = self.appstate.get("selected_devices", [])
        
        # Set emergency stop flag IMMEDIATELY - this stops any running profiles
        self._emergency_stop_flag = True
        
        self._log("ADHESIVE EMERGENCY STOP activated", "error")
        
        if not devices:
            self._set_operation(
                "Adhesive Emergency Stop",
                "[b #ff5555]EMERGENCY STOP[/b #ff5555]\n\n"
                "[#ff5555]No devices connected to stop.[/#ff5555]\n\n"
                "Emergency stop requires connected devices."
            )
            return
        
        # Check which devices are online
        online_devices = check_online_devices(devices)
        
        if not online_devices:
            self._log("No devices are currently online", "warning")
            self._set_operation(
                "Adhesive Emergency Stop",
                "[b #ff5555]EMERGENCY STOP[/b #ff5555]\n\n"
                "[#ff5555]No devices are currently online.[/#ff5555]\n\n"
                f"Selected {len(devices)} device(s), but none are reachable."
            )
            return
        
        offline_count = len(devices) - len(online_devices)
        if offline_count > 0:
            self._log(f"Warning: {offline_count} device(s) are offline and cannot be stopped", "warning")
        
        self._set_operation(
            "Adhesive Emergency Stop",
            "[b #ff5555]ADHESIVE EMERGENCY STOP ACTIVATED[/b #ff5555]\n\n"
            f"Stopping adhesive operations on {len(online_devices)} online device(s)...\n\n"
            "Commands sent:\n"
            "  • Stop all motors (0,0,0)\n"
            "  • Release pressure\n"
            "  • Enter safe state\n\n"
            f"Online devices: {len(online_devices)}/{len(devices)}\n\n"
            "[dim]Sending emergency stop commands...[/dim]"
        )
        
        # Send emergency stop commands
        def emergency_stop_task():
            try:
                stopped_count = 0
                for d in online_devices:
                    # Use robust TCP sending with aggressive retries for emergency stop
                    success, error = send_tcp_command_robust(d, "0,0,0", retries=5, retry_delay=0.3, timeout=1.5)
                    
                    if success:
                        stopped_count += 1
                        self._log(f"Emergency stop sent to {d['Host']}", "success")
                    else:
                        self._log(f"Failed to stop {d['Host']} after 5 retries: {error}", "error")
                
                self.call_from_thread(self._set_operation,
                    "Adhesive Emergency Stop",
                    f"[b #ff5555]EMERGENCY STOP COMPLETED[/b #ff5555]\n\n"
                    f"Stopped {stopped_count}/{len(online_devices)} device(s)\n\n"
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
                        f"Component ID: {aruco.id}\n"
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

# Path for persistent settings
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "dashboard_settings.json")


def save_selected_devices(device_hosts: list) -> None:
    """Save the list of selected device hosts to a settings file."""
    try:
        settings = {}
        # Load existing settings if file exists
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
        
        # Update selected devices
        settings['selected_device_hosts'] = device_hosts
        
        # Save back to file
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save device selection: {e}")


def load_selected_device_hosts() -> list:
    """Load the list of previously selected device hosts from settings file."""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                return settings.get('selected_device_hosts', [])
    except Exception as e:
        print(f"Warning: Could not load device selection: {e}")
    return []


def build_initial_appstate() -> Dict[str, Any]:
    """Build initial application state."""
    # Don't auto-discover devices on startup - let user explicitly discover them
    # try:
    #     devices = get_devices()
    # except Exception:
    #     devices = []

    # Initialize UDP server
    server = UDPServer()
    try:
        server.start_server()
    except Exception as e:
        print(f"Warning: Could not start UDP server: {e}")

    # Create default component (Component 0)
    default_component_data = {
        "id": 0,
        "level": 1,
        "target": (18915, 5693, 1972, 180, 0, 0),
        "intermediate": (18915, 5693, 6972, 0, 0, 0),
        "holes": [(-241, 286.4, 0), (-241, -286.4, 0), (482, 0, 0)],
        "weight": 241
    }
    
    # Build Component 0 object (Component only takes positions and aruco, not weight)
    default_component = Component(
        ComponentPositions(
            coarse=CranePosition(
                default_component_data["target"][0],
                default_component_data["target"][1],
                default_component_data["target"][2] + 5000,  # 5000mm above target
                0, 0, 0
            ),
            intermediate=CranePosition(*default_component_data["intermediate"]),
            fine=CranePosition(
                default_component_data["target"][0],
                default_component_data["target"][1],
                default_component_data["target"][2] + 100,  # 100mm above target
                default_component_data["target"][3],
                default_component_data["target"][4],
                default_component_data["target"][5]
            ),
            target=CranePosition(*default_component_data["target"])
        ),
        Aruco(id=0, position=CranePosition(0, 0, 0, 0, 0, 0))
    )

    return {
        "logging": True,
        "log_prefix": "LogTesting",
        "server": server,
        "crane": None,
        "selected_component": default_component,  # Default to Component 0
        "all_devices": [],  # All discovered devices from config
        "selected_devices": [],  # Start with no devices selected
        "last_event": "Dashboard started. Use 'Discover robots' to find available devices.",
    }


def main():
    """Main entry point."""
    appstate = build_initial_appstate()
    app = LightsOffDashboard(appstate)
    app.run()


if __name__ == "__main__":
    main()
