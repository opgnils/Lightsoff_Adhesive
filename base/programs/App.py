"""
Main CLI application for the LightsOff project.

This script provides a command-line interface to orchestrate the distributed system for detecting Aruco markers and holes in wooden components during automated crane construction.
It manages user interactions for robot discovery, selection, code updates, component configuration, motor control, and real-time tracking modes (Aruco, holes, or combined).
The app integrates with remote robots via SSH, coordinates data via UDP messaging, and visualizes results using matplotlib plots.
It ensures a linear workflow in a nonlinear distributed system, handling concurrency with threads and user interrupts.
"""

import sys
import os
import subprocess
import threading
import time
import socket
import csv
import select
import termios
import tty
from bullet import Check, Bullet
from pynput.keyboard import Key, Listener, KeyCode

# Add the parent directory to the Python path to access base modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from base.UDPServer import UDPServer
from base.Devices import *
from base.Crane import *
from base.Components import *
from base.Plots import *
from base.PlotManager import *

# Global flag for keyboard interrupt to stop tracking gracefully across threads
q_pressed = False

def on_press(key):
    """Handle key press events for interrupting tracking.

    Args:
        key: The key pressed, checked for 'q' to stop tracking.
    """
    global q_pressed
    if key == KeyCode.from_char('q'):
        print("\n[Q pressed - stopping tracking...]")
        q_pressed = True
        return False

def start_keyboard_listener():
    """Start the keyboard listener for 'q' key to allow graceful interruption of tracking."""
    global q_pressed
    q_pressed = False
    listener = Listener(on_press=on_press)
    listener.start()
    return listener

def cli_select_devices(config = None):
    """Select and optionally update remote robots via CLI.

    Guides the user through discovering online robots, selecting them, and choosing to update code remotely.
    This ensures the distributed system is ready before proceeding to tracking.

    Args:
        config (str, optional): SSH config file name for robot connections. Defaults to None which corresponds with config_lightsoff.
    """
    # Retrieve configured robots to check their online status
    devices = get_devices(config = config)

    # Loop to ensure at least one robot is online before allowing selection
    while True:
    
        # Check which robots are reachable via SSH
        online_devices = check_online_devices(devices)
    
        if not online_devices:
            print("\nNo robots are online!")  
            
            cli_0 = Bullet(
                prompt = "",
                choices = ["Refresh Robot List"],
                margin = 2
            )
            
            choice_0 = cli_0.launch()


        else:

            cli_1 = Bullet(
                prompt = "\nSelect an option:",
                choices = ["Select Robots", "Refresh Robot List"],
                margin = 2
            )
            choice_1 = cli_1.launch()

            if choice_1 == "Select Robots": break

    # Allow user to select from online robots
    selected_devices_names = []
    while True:
        print("\033c", end="")

        choices = [device['Host'] for device in online_devices]

        cli_device_selection = Check(
            prompt = "\nUse [SPACE] to Select Robots",
            choices = choices,
            check = "√",
            margin = 2
        )

        selected_devices_names = cli_device_selection.launch()
        if len(selected_devices_names) > 0:
            break

        print("\nYou must select at least 1 robot")

    selected_devices = [d for d in online_devices if d['Host'] in selected_devices_names]

    cli_update = Bullet(
        prompt = "\nUpdate Code on Remote Robots?:",
        choices = ["Continue", "Update and Continue"],
        margin = 2
    )
    update_choice = cli_update.launch()

    if update_choice == "Update and Continue":
        run_updates(selected_devices, config=config)


    return selected_devices

def cli_select_component():
    """Select a component to track via CLI.

    Allows user to choose from predefined components, which define Aruco markers and positions for crane operations.
    Currently hardcoded for demonstration; integrates with Component class for future expansion.

    Returns:
        Component: The selected component object with positions and Aruco data.
    """
    print("\033c", end="")

    cli_component = Bullet(
        prompt = "\nSelect a component:",
        choices = ["Component 0", "Component 1", "Component 2"],
        margin = 2
    )
    selected_component = cli_component.launch()
    print(f"\nSelected Component: {selected_component}")

    # Extract component index from user selection for Aruco ID
    idx = int(selected_component[-1])

    print("WARNING TODO this component is hard coded")
    comp = Component(ComponentPositions(
        coarse=CranePosition(0,0,10,0,0,0),
        intermediate=CranePosition(0,0,5,0,0,0),
        fine=CranePosition(0,0,1,0,0,0),
        target=CranePosition(0,0,0,0,0,0)
        ),
        Aruco(
            id = idx,
            position=CranePosition(1,1,0,0,0,0)            
        )
    )

    return comp

def cli_position_crane(crane:Crane, target_position:CranePosition):
    """Position the crane to a target location via CLI.

    Handles crane movement with user confirmation and retry logic for failed operations.
    Ensures safe and controlled crane positioning in the automated system.

    Args:
        crane (Crane): The crane object for hardware control.
        target_position (CranePosition): The desired crane position.
    """
    print("\033c", end="")

    cli_ready = Bullet(
        prompt="\nReady For Positioning:",
        choices=["Go", "Exit"],
        margin=2
    )
    ready_choice = cli_ready.launch()
    if ready_choice == "Exit": exit(1)

    # Loop for crane positioning attempts with retry on failure
    while True:
        print("\033c", end="")
        success = crane.position_crane(target_position)
        
        if success:
            cli_continue = Bullet(
                prompt="\nPositioning Complete",
                choices=["Continue", "Reposition", "Exit"],
                margin=2
            )
            continue_choice = cli_continue.launch()
            if continue_choice == "Continue": break
            elif continue_choice == "Exit": exit(1)

        else:
            cli_tryagain = Bullet(
                prompt="\nPositioning Failed: Try Again?",
                choices=["Reposition", "Exit"],
                margin=2
            )
            tryagain_choice = cli_tryagain.launch()
            if tryagain_choice == "Exit" : exit(1)

def cli_motor_control(appstate:dict):
    """Control motor clamps on selected robots via CLI.

    Allows engaging or releasing motor clamps with confirmation and threading for concurrent operations.
    Critical for securing components during crane operations in the distributed system.

    Args:
        appstate (dict): Application state containing selected robots and server.
    """
    
    devices = appstate["selected_devices"]  # List of selected remote robots for motor control
    server:UDPServer = appstate["server"]  # UDP server for coordinating messages

    motor_direction: bool = False  # False for engage clamps, True for release

    # Launch the Python File on All Devices
    while True:
        print("\033c", end="")
        cli_ready = Bullet(
            prompt="\nMotors Ready:",
            choices=["Engage", "Release", "Skip", "Back"],
            margin=2,
        )
        ready_choice = cli_ready.launch()
        if ready_choice == "Back":
            # Return to caller instead of exiting the entire app
            return
        elif ready_choice == "Engage":
            motor_direction = False
        elif ready_choice == "Release":
            motor_direction = True
        elif ready_choice == "Skip":
            break

        print("\033c", end="")

        threads = []  # List to track concurrent motor control threads
        all_success = True
        for d in devices:
            success, thread = launch_remote_file(
                device=d,
                remote_python_file="~/Documents/LightsOff_Project/cambots/AssemblyRobot/MotorControl.py",
                arguments=f"{str(motor_direction)} 2000 30",
            )
            threads.append(thread)
            if not success:
                all_success = False
                break

        with yaspin(text=f"{"dis" if motor_direction else ""}engaging motors", color="light_green") as spinner:
            time.sleep(32)

        if all_success:
            cli_continue = Bullet(
                prompt="\nMotor Setting Complete",
                choices=["Continue", "Repeat", "Back"],
                margin=2,
            )
            continue_choice = cli_continue.launch()
            if continue_choice == "Continue":
                break
            elif continue_choice == "Back":
                return
        else:
            cli_tryagain = Bullet(
                prompt="\nMotor Setting Failed: Try Again?",
                choices=["Repeat", "Back"],
                margin=2,
            )
            tryagain_choice = cli_tryagain.launch()
            if tryagain_choice == "Back":
                return


def _cli_motor_action(appstate: dict, motor_direction: bool):
    """Helper for assembly robot menu to engage/disengage clamps once.

    Args:
        appstate (dict): Shared application state.
        motor_direction (bool): False = engage, True = release.
    """

    devices = appstate["selected_devices"]
    server: UDPServer = appstate["server"]

    if not devices:
        print("\nNo robots selected. Use the Connect menu to discover/select first.")
        time.sleep(2)
        return

    print("\033c", end="")

    threads = []
    all_success = True
    for d in devices:
        success, thread = launch_remote_file(
            device=d,
            remote_python_file="~/Documents/LightsOff_Project/cambots/AssemblyRobot/MotorControl.py",
            arguments=f"{str(motor_direction)} 2000 30",
        )
        threads.append(thread)
        if not success:
            all_success = False
            break

    with yaspin(text=f"{"dis" if motor_direction else ""}engaging motors", color="light_green") as spinner:
        time.sleep(32)

    for t in threads:
        t.join()

    Bullet(
        prompt="\nMotor action complete" if all_success else "\nMotor action failed",
        choices=["Back"],
        margin=2,
    ).launch()

def cli_aruco_tracking(appstate:dict, plotter:PlotManager):
    """Run Aruco marker tracking on selected devices with real-time plotting.

    Launches remote Aruco detection scripts, sets up data filters for smoothing, and visualizes results via plots.
    Manages concurrency, user interrupts, timeouts, and logging to ensure robust tracking in the distributed system.

    Args:
        appstate (dict): Application state with devices, component, server, and logging settings.
        plotter (PlotManager): Manager for real-time matplotlib plots.
    """

    devices = appstate["selected_devices"]  # Selected remote devices for Aruco tracking
    aruco:Aruco = appstate["selected_component"].aruco  # Aruco marker data from selected component
    server:UDPServer = appstate["server"]  # UDP server for messaging and data filtering
  
    print("\033c", end="")
    print(f"\n{aruco}")

    cli_ready = Bullet(
        prompt="\nReady for Arcuo Detection:",
        choices=["Go", "Exit"],
        margin=2
    )
    ready_choice = cli_ready.launch()
    if ready_choice == "Exit": exit(1)    

    plotter.add_plot_function('aruco', aruco_plot)    

    # Launch the Aruco Python File on All Devices
    while True:
        # clear old messages
        appstate['server'].clear()  
        if appstate['logging']: server.start_logging(f"{appstate['log_prefix']}_Aruco")      

        # Configure filters for aruco data
        server.add_filter(tag="aruco", keys=("data", aruco.id, "distance"), delta_threshold=0.75)  # Distance with minimum 1cm change
        server.add_filter(tag="aruco", keys=("data", aruco.id, "tvec"), delta_threshold=0.5)  # Translation vector with minimum 5mm change
        server.add_filter(tag="aruco", keys=("data", aruco.id, "rvec"), delta_threshold=0.2)  # Rotation vector with minimum ~1 degree change        
        
        print("\033c", end="")

        # open the plot
        plotter.open_plot('aruco')
        
        threads = []
        all_success = True
        for d in devices:
            success, thread = launch_remote_file(
                device=d,
                remote_python_file= "~/Documents/LightsOff_Project/cambots/CameraTracking/track_aruco.py"
                )
            threads.append(thread)
            if not success: 
                all_success = False
                break
        print("Checking for Start Codes")
        time.sleep(2)        
        print(server.get_message_by_tag(tag = "start"))

        ### Listen ###        
        # Start keyboard listener and set timeout
        print("\nListening for messages... (Press 'q' to stop)")
        listener = start_keyboard_listener()
        start_time = time.time()

        max_time = 600
        
        try:
            while True:
                current_time = time.time()
                elapsed = current_time - start_time
                
                # Check if 'q' was pressed
                if q_pressed:
                    print("\nStopping due to 'q' key press...")
                    break
                
                # Check for timeout (10 minutes)
                if elapsed >= max_time:
                    print(f"\n10 minutes elapsed. Continue tracking?")
                    cli_continue = Bullet(
                        prompt="Continue or stop?",
                        choices=["Continue (+10 min)", "Stop"],
                        margin=2
                    )
                    choice = cli_continue.launch()
                    
                    if choice == "Continue (+10 min)":
                        max_time += 600  # Add another 10 minutes
                        print(f"Extended tracking time by 600 seconds")
                    else:
                        print("Stopping tracking...")
                        break
                
                plt.pause(0.15)
                
        finally:
            # Always stop the listener
            listener.stop()
        
        # Stop remote code
        server.send_simple_message(devices, 'stop')
        for thread in threads: thread.join()
        print("all threads joined")

        # stop logging
        server.stop_logging()


        # Recieve stop messages
        time.sleep(0.1)
        messages = server.get_message_by_tag(tag='stop')  # Adjust tag as needed            
        if messages:
            print("Checking For Stop Codes:")
            for cambot_id, msg_list in messages.items():
                for msg in msg_list:
                    print(f"  From {cambot_id}: {msg}")

        ### Done Listening ###

        plotter.close_plot('aruco')

        if all_success:
            cli_continue = Bullet(
                prompt="\nTracking Complete",
                choices=["Continue", "Repeat Tracking", "Exit"],
                margin=2
            )
            continue_choice = cli_continue.launch()
            if continue_choice == "Continue": break
            elif continue_choice == "Exit": exit(1)

        else:
            cli_tryagain = Bullet(
                prompt="\nTracking Failed: Try Again?",
                choices=["Repeat Tracking", "Exit"],
                margin=2
            )
            tryagain_choice = cli_tryagain.launch()
            if tryagain_choice == "Exit" : exit(1)

def cli_hole_tracking(appstate:dict, plotter:PlotManager):
    """Run hole detection tracking on selected devices with real-time plotting.

    Launches remote hole detection scripts, sets up data filters, and visualizes results.
    Manages concurrency, user interrupts, timeouts, and logging for the tracking session.

    Args:
        appstate (dict): Application state with devices, server, and logging settings.
        plotter (PlotManager): Manager for real-time matplotlib plots.
    """

    devices = appstate["selected_devices"]  # Selected remote devices for hole tracking
    server:UDPServer = appstate["server"]  # UDP server for messaging and data filtering
  
    print("\033c", end="")

    cli_ready = Bullet(
        prompt="\nReady for Hole Tracking:",
        choices=["Go", "Exit"],
        margin=2
    )
    ready_choice = cli_ready.launch()
    if ready_choice == "Exit": exit(1)    

    plotter.add_plot_function('holes', holes_plot)

    # Configure filters for hole data (TODO: implement specific filters)
    # server.add_filter(tag="hole", keys=("data", "bbox"), delta_threshold=0.75)

    # Launch the Python File on All Devices
    while True:
        # Clear old messages from previous sessions
        appstate['server'].clear()
        if appstate['logging']: server.start_logging(f"{appstate['log_prefix']}_Holes")
        
        print("\033c", end="")

        # Open the plot for real-time visualization
        plotter.open_plot('holes')
        
        threads = []  # Track threads for remote script execution
        all_success = True
        for d in devices:
            success, thread = launch_remote_file(
                device=d,
                remote_python_file = "~/Documents/LightsOff_Project/cambots/CameraTracking/track_holes.py"
            )
            
            threads.append(thread)
            if not success: 
                all_success = False
                break
        print("Checking for Start Codes")
        time.sleep(2)        
        print(server.get_message_by_tag(tag = "start"))

        ### Listen for tracking data with interrupt and timeout handling ###
        # Start keyboard listener for graceful interruption
        print("\nListening for messages... (Press 'q' to stop)")
        listener = start_keyboard_listener()
        start_time = time.time()
        max_time = 600  # 10-minute timeout for safety
        
        try:
            while True:
                current_time = time.time()
                elapsed = current_time - start_time
                
                # Check for user interrupt
                if q_pressed:
                    print("\nStopping due to 'q' key press...")
                    break
                
                # Check for timeout and prompt user to extend
                if elapsed >= max_time:
                    print(f"\n10 minutes elapsed. Continue tracking?")
                    cli_continue = Bullet(
                        prompt="Continue or stop?",
                        choices=["Continue (+10 min)", "Stop"],
                        margin=2
                    )
                    choice = cli_continue.launch()
                    
                    if choice == "Continue (+10 min)":
                        max_time += 600  # Extend by 10 minutes
                        print(f"Extended tracking time by 600 seconds")
                    else:
                        print("Stopping tracking...")
                        break
                
                # Update plots in real-time
                plt.pause(0.15)
                
        finally:
            # Ensure listener is stopped
            listener.stop()
        
        # Stop remote scripts and clean up
        print("Sending Stop Message")
        server.send_simple_message(devices, 'stop')
        for thread in threads: thread.join()
        print("all threads joined")
        
        # Stop logging if enabled
        if appstate['logging'] :server.stop_logging()

        # Receive and log stop messages for confirmation
        time.sleep(2)
        messages = server.get_message_by_tag(tag='stop')            
        if messages:
            print("Checking For Stop Codes:")
            for cambot_id, msg_list in messages.items():
                for msg in msg_list:
                    print(f"  From {cambot_id}: {msg}")

        ### Done Listening ###

        plotter.close_plot('holes')

        if all_success:
            cli_continue = Bullet(
                prompt="\nTracking Complete",
                choices=["Continue", "Repeat Tracking", "Exit"],
                margin=2
            )
            continue_choice = cli_continue.launch()
            if continue_choice == "Continue": break
            elif continue_choice == "Exit": exit(1)

        else:
            cli_tryagain = Bullet(
                prompt="\nTracking Failed: Try Again?",
                choices=["Repeat Tracking", "Exit"],
                margin=2
            )
            tryagain_choice = cli_tryagain.launch()
            if tryagain_choice == "Exit" : exit(1)

def cli_both_tracking(appstate:dict, plotter:PlotManager):
    """Run combined Aruco and hole tracking on selected devices with real-time plotting.

    Launches remote combined tracking scripts, sets up data filters, and visualizes both data types.
    Handles concurrency, interrupts, timeouts, and logging for the integrated tracking session.

    Args:
        appstate (dict): Application state with devices, component, server, and logging settings.
        plotter (PlotManager): Manager for real-time matplotlib plots.
    """
    devices = appstate["selected_devices"]  # Selected remote devices for combined tracking
    aruco:Aruco = appstate["selected_component"].aruco  # Aruco marker data from component
    server:UDPServer = appstate["server"]  # UDP server for messaging and filtering
  
    print("\033c", end="")
    print(f"\n{aruco}")

    cli_ready = Bullet(
        prompt="\nReady for Combined Tracking:",
        choices=["Go", "Exit"],
        margin=2
    )
    ready_choice = cli_ready.launch()
    if ready_choice == "Exit": exit(1)    

    plotter.add_plot_function('aruco', aruco_plot)    
    plotter.add_plot_function('holes', holes_plot)

    # Launch the Combined Python File on All Devices
    while True:
        # clear old messages
        appstate['server'].clear()  
        if appstate['logging']: server.start_logging(f"{appstate['log_prefix']}_Both")      

        # Configure filters for aruco data
        server.add_filter(tag="aruco", keys=("data", aruco.id, "distance"), delta_threshold=0.75)  # Distance with minimum 1cm change
        server.add_filter(tag="aruco", keys=("data", aruco.id, "tvec"), delta_threshold=0.5)  # Translation vector with minimum 5mm change
        server.add_filter(tag="aruco", keys=("data", aruco.id, "rvec"), delta_threshold=0.2)  # Rotation vector with minimum ~1 degree change        
        
        print("\033c", end="")

        # open the plots
        plotter.open_plot('aruco')
        plotter.open_plot('holes')
        
        threads = []
        all_success = True
        for d in devices:
            success, thread = launch_remote_file(
                device=d,
                remote_python_file= "~/Documents/LightsOff_Project/cambots/CameraTracking/track_both.py"
                )
            threads.append(thread)
            if not success: 
                all_success = False
                break
        print("Checking for Start Codes")
        time.sleep(2)        
        print(server.get_message_by_tag(tag = "start"))

        ### Listen ###        
        # Start keyboard listener and set timeout
        print("\nListening for messages... (Press 'q' to stop)")
        listener = start_keyboard_listener()
        start_time = time.time()

        max_time = 600
        
        try:
            while True:
                current_time = time.time()
                elapsed = current_time - start_time
                
                # Check if 'q' was pressed
                if q_pressed:
                    print("\nStopping due to 'q' key press...")
                    break
                
                # Check for timeout (10 minutes)
                if elapsed >= max_time:
                    print(f"\n10 minutes elapsed. Continue tracking?")
                    cli_continue = Bullet(
                        prompt="Continue or stop?",
                        choices=["Continue (+10 min)", "Stop"],
                        margin=2
                    )
                    choice = cli_continue.launch()
                    
                    if choice == "Continue (+10 min)":
                        max_time += 600  # Add another 10 minutes
                        print(f"Extended tracking time by 600 seconds")
                    else:
                        print("Stopping tracking...")
                        break
                
                # Update plots without printing messages
                plt.pause(0.15)
                
        finally:
            # Always stop the listener
            listener.stop()
        
        # Stop remote code
        server.send_simple_message(devices, 'stop')
        for thread in threads: thread.join()
        print("all threads joined")

        # stop logging
        server.stop_logging()

        # Recieve stop messages
        time.sleep(0.1)
        messages = server.get_message_by_tag(tag='stop')  # Adjust tag as needed            
        if messages:
            print("Checking For Stop Codes:")
            for cambot_id, msg_list in messages.items():
                for msg in msg_list:
                    print(f"  From {cambot_id}: {msg}")

        ### Done Listening ###

        plotter.close_plot('aruco')
        plotter.close_plot('holes')

        if all_success:
            cli_continue = Bullet(
                prompt="\nTracking Complete",
                choices=["Continue", "Repeat Tracking", "Exit"],
                margin=2
            )
            continue_choice = cli_continue.launch()
            if continue_choice == "Continue": break
            elif continue_choice == "Exit": exit(1)

        else:
            cli_tryagain = Bullet(
                prompt="\nTracking Failed: Try Again?",
                choices=["Repeat Tracking", "Exit"],
                margin=2
            )
            tryagain_choice = cli_tryagain.launch()
            if tryagain_choice == "Exit" : exit(1)


def cli_menu_devices(appstate: dict, config: str):
    """Connect submenu: discover robots and update code.

    This menu allows rediscovering robots and pushing code updates
    without leaving the main application.
    """

    while True:
        print("\033c", end="")
        cli = Bullet(
            prompt="\nConnect:",
            choices=[
                "a. Discover robots",
                "b. Update code on selected robots",
                "Back",
            ],
            margin=2,
        )
        choice = cli.launch()

        if choice.startswith("a."):
            appstate["selected_devices"] = cli_select_devices(config=config)
        elif choice.startswith("b."):
            if not appstate["selected_devices"]:
                print("\nNo robots selected yet. Run Discover first.")
                time.sleep(2)
                continue
            run_updates(appstate["selected_devices"], config=config)
        elif choice == "Back":
            return


def cli_menu_component(appstate: dict):
    """Component submenu: select or change the current component."""

    while True:
        print("\033c", end="")
        cli = Bullet(
            prompt="\nComponent:",
            choices=[
                "Select / change component",
                "Back",
            ],
            margin=2,
        )
        choice = cli.launch()

        if choice.startswith("Select"):
            appstate["selected_component"] = cli_select_component()
        elif choice == "Back":
            return


def cli_menu_assembly_robot(appstate: dict):
    """Assembly robot submenu: engage or disengage clamps."""

    while True:
        print("\033c", end="")
        cli = Bullet(
            prompt="\nAssembly Robot:",
            choices=[
                "a. Engage clamps",
                "b. Disengage clamps",
                "Back",
            ],
            margin=2,
        )
        choice = cli.launch()

        if choice.startswith("a."):
            _cli_motor_action(appstate, motor_direction=False)
        elif choice.startswith("b."):
            _cli_motor_action(appstate, motor_direction=True)
        elif choice == "Back":
            return


def _send_adhesive_command_tcp(device, cmd: str, port: int = 5001, timeout: float = 2.0):
    """Send a single adhesive command to the Jetson listener over TCP.

    Args:
        device (dict): Device info with HostName.
        cmd (str): Command string like "0,200,0".
        port (int): TCP port where AdhesiveListener is running.
        timeout (float): Socket timeout in seconds.
    """
    host = device["HostName"]
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(cmd.encode("utf-8"))
        return True
    except Exception as e:
        print(f"[Adhesive TCP] Error sending to {device['Host']} ({host}:{port}): {e}")
        return False


def _run_adhesive_profile(appstate: dict):
    """Load and execute an adhesive profile CSV over time.

    CSV format: time, motor1, motor2, motor3 (one row per step).
    Values are sent as a triple "m1,m2,m3" to the adhesive listener.
    """
    devices = appstate["selected_devices"]
    if not devices:
        print("\nNo robots selected. Use the Connect menu to discover/select first.")
        time.sleep(2)
        return

    # List available profiles
    base_dir = os.path.dirname(os.path.abspath(__file__))
    profiles_dir = os.path.join(base_dir, "adhesive_profiles")

    if not os.path.isdir(profiles_dir):
        print(f"No adhesive_profiles folder found at {profiles_dir}")
        time.sleep(2)
        return

    profiles = [f for f in os.listdir(profiles_dir) if f.lower().endswith(".csv")]
    if not profiles:
        print("No CSV profiles found in adhesive_profiles.")
        time.sleep(2)
        return

    print("\033c", end="")
    cli = Bullet(
        prompt="\nSelect an adhesive profile:",
        choices=profiles + ["Back"],
        margin=2,
    )
    choice = cli.launch()
    if choice == "Back":
        return

    profile_path = os.path.join(profiles_dir, choice)

    # Load profile
    steps = []  # list of (time, [m1,m2,m3])
    try:
        with open(profile_path, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                # Skip empty lines
                if not row:
                    continue
                # Strip spaces and ignore comments
                parts = [p.strip() for p in row if p.strip() and not p.strip().startswith("#")]
                if len(parts) < 2:
                    continue
                t = float(parts[0])
                # Fill missing motors with 0 if needed
                m1 = float(parts[1]) if len(parts) > 1 else 0.0
                m2 = float(parts[2]) if len(parts) > 2 else 0.0
                m3 = float(parts[3]) if len(parts) > 3 else 0.0
                steps.append((t, [m1, m2, m3]))
    except Exception as e:
        print(f"Failed to load profile {choice}: {e}")
        time.sleep(2)
        return

    if not steps:
        print("Profile is empty.")
        time.sleep(2)
        return

    # Sort by time in case
    steps.sort(key=lambda x: x[0])

    print("\033c", end="")
    print(f"Running adhesive profile: {choice}")
    print("Press 'q' or ESC to EMERGENCY STOP (sends 0,0,0 and aborts). Ctrl+C also aborts.")

    start_time = time.time()

    def _send_stop_all():
        """Send STOP ALL (0,0,0) multiple times for robustness, like manual STOP ALL."""
        cmd = "0,0,0"
        repeats = 3
        last_success = True
        for i in range(repeats):
            all_success = True
            for d in devices:
                ok = _send_adhesive_command_tcp(d, cmd)
                if not ok:
                    all_success = False
            if not all_success:
                last_success = False
                print(f"STOP attempt {i+1}/{repeats} failed on at least one device")
            time.sleep(0.1)
        print("\nSent STOP (0,0,0)" if last_success else "\nSTOP may not have reached all devices")

    # Set stdin to non-blocking raw mode so we can detect 'q'/ESC while sleeping
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    try:
        for i, (t_target, motors) in enumerate(steps):
            now = time.time()
            wait = t_target - (now - start_time)
            # Wait in small chunks so we can poll for emergency key presses
            end_wait = time.time() + max(wait, 0)
            while time.time() < end_wait:
                # Poll stdin for key presses without blocking
                rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                if rlist:
                    ch = sys.stdin.read(1)
                    if ch in ("q", "Q", "\x1b"):
                        print("\nEmergency STOP requested during profile...")
                        _send_stop_all()
                        time.sleep(1)
                        return

            cmd = f"{motors[0]},{motors[1]},{motors[2]}"
            all_success = True
            for d in devices:
                ok = _send_adhesive_command_tcp(d, cmd)
                if not ok:
                    all_success = False

            print(f"[{i+1}/{len(steps)}] t={t_target:.2f}s -> {cmd} ({'ok' if all_success else 'error'})")

        print("\nProfile complete. Sending final STOP (0,0,0)...")
        _send_stop_all()
        time.sleep(1)
    except KeyboardInterrupt:
        print("\nKeyboard interrupt during profile. Sending EMERGENCY STOP (0,0,0)...")
        _send_stop_all()
        time.sleep(1)
    finally:
        # Restore terminal settings
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def cli_menu_adhesive_robot(appstate: dict):
    """Adhesive robot submenu: manual command input or profile playback."""

    while True:
        devices = appstate.get("selected_devices", [])
        print("\033c", end="")

        # Connection / listener status indicator
        print("Adhesive Robot - Connection Status:")
        if not devices:
            print("  No robots selected. Use 'Connect' menu first.\n")
        else:
            for d in devices:
                host = d["Host"]
                # Lightweight check: is listener reported as running?
                # We reuse the same check command logic as ensure_adhesive_listener_running,
                # but do not try to start here; we want to *show* status.
                user = d["User"]
                ssh_check = [
                    "sshpass",
                    "-p",
                    "lightsoff",
                    "ssh",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "ConnectTimeout=3",
                    f"{user}@{d['HostName']}",
                    'ps aux | grep "AdhesiveListener.py" | grep -v grep',
                ]
                state = "unknown"
                try:
                    result = subprocess.run(ssh_check, capture_output=True, text=True, timeout=5)
                    if result.returncode == 0 and result.stdout.strip() != "":
                        state = "LISTENER RUNNING"
                    else:
                        state = "listener stopped"
                except Exception:
                    state = "unreachable"
                print(f"  {host}: {state}")
            print()

        # Ensure listeners are running when entering this menu
        if devices:
            for d in devices:
                ensure_adhesive_listener_running(d)

        cli = Bullet(
            prompt="\nAdhesive Robot:",
            choices=[
                "a. Manual input",
                "b. Load profile (CSV)",
                "c. Restart listener on selected robots",
                "Back",
            ],
            margin=2,
        )
        choice = cli.launch()

        if choice.startswith("a."):
            _cli_adhesive_action(appstate, engage=True)
        elif choice.startswith("b."):
            _run_adhesive_profile(appstate)
        elif choice.startswith("c."):
            _cli_restart_adhesive_listener(appstate)
        elif choice == "Back":
            return


def _cli_restart_adhesive_listener(appstate: dict):
    """Kill and restart the adhesive listener on all selected robots.

    This is useful if the listener or serial stack got stuck and no
    commands (including STOP ALL) are going through anymore.
    """

    devices = appstate["selected_devices"]
    if not devices:
        print("\nNo robots selected. Use the Connect menu to discover/select first.")
        time.sleep(2)
        return

    print("\033c", end="")
    print("Restarting adhesive listeners on selected robots...")

    for d in devices:
        host = d["Host"]
        user = d["User"]
        # First, try to kill any running AdhesiveListener.py processes
        kill_cmd = [
            "sshpass",
            "-p",
            "lightsoff",
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=5",
            f"{user}@{d['HostName']}",
            "pkill -f AdhesiveListener.py || true",
        ]
        try:
            subprocess.run(kill_cmd, capture_output=True, text=True, timeout=10)
            print(f"[{host}] Killed any existing AdhesiveListener.py processes (if running).")
        except Exception as e:
            print(f"[{host}] Error attempting to kill AdhesiveListener.py: {e}")

        # Then ensure the listener is started again using the existing helper
        try:
            ok = ensure_adhesive_listener_running(d)
            if ok:
                print(f"[{host}] Listener restarted and running.")
            else:
                print(f"[{host}] Failed to confirm listener is running.")
        except Exception as e:
            print(f"[{host}] Error starting listener: {e}")

    print("\nDone restarting adhesive listeners.")
    time.sleep(2)


def _cli_emergency_stop(appstate: dict):
    """Emergency STOP: reconnect-ish behavior to force all motors off.

    This is intended for the case where the normal STOP ALL might not work
    due to a wedged listener or transient connection issue. The idea is:
    - Try to send a STOP ALL triple (0,0,0) to all selected devices.
    - Then restart the adhesive listener processes on those devices,
      which in your experience also ensures everything is in a safe state.
    """

    devices = appstate.get("selected_devices") or []
    if not devices:
        print("\nNo robots selected. Use the Connect menu first.")
        time.sleep(2)
        return

    print("\n=== EMERGENCY STOP: killing listeners, sending STOP ALL, and restarting ===")

    # 1) Kill any existing AdhesiveListener.py on all selected robots.
    user = "lightsoff"
    for d in devices:
        host = d.get("Host") or d.get("HostName") or "?"
        kill_cmd = [
            "sshpass",
            "-p",
            d["Password"],
            "ssh",
            "-p",
            str(d["Port"]),
            "-F",
            os.path.join(os.path.dirname(__file__), "..", "..", "ssh", "config_lightsoff"),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=5",
            f"{user}@{d['HostName']}",
            "pkill -f AdhesiveListener.py || true",
        ]
        try:
            subprocess.run(kill_cmd, capture_output=True, text=True, timeout=10)
            print(f"[{host}] Killed AdhesiveListener.py (if running).")
        except Exception as e:
            print(f"[{host}] Error attempting to kill AdhesiveListener.py during EMERGENCY STOP: {e}")

    # 2) Attempt a STOP ALL triple to all devices (in case any listener is still responsive
    #    or there are other consumers of the adhesive command port).
    cmd = "0,0,0"
    repeats = 3
    for i in range(repeats):
        all_success = True
        for d in devices:
            ok = _send_adhesive_command_tcp(d, cmd)
            if not ok:
                all_success = False
        if not all_success:
            print(f"STOP attempt {i+1}/{repeats} failed on at least one device")
        time.sleep(0.1)

    # 3) Restart listeners so the system returns to a known-good state for further control.
    print("Now restarting adhesive listeners on all selected robots...\n")
    _cli_restart_adhesive_listener(appstate)


def _cli_adhesive_action(appstate: dict, engage: bool):
    """Adhesive robot control loop using a persistent Jetson listener.

    Lets the user choose manual RPM/flowrates and STOP ALL.
    """

    devices = appstate["selected_devices"]

    if not devices:
        print("\nNo robots selected. Use the Connect menu to discover/select first.")
        time.sleep(2)
        return

    # Keep track of current triple; default to zeros
    current = ["0", "0", "0"]
    max_val = 1150  # flowrate limit for motors 2 & 3 (µL/s)
    max_rpm = 6000  # mechanical RPM limit for motor 1

    while True:
        print("\033c", end="")
        print("Motor 1 is in RPM; Motors 2 and 3 are in microliters per second (µL/s).")
        print(f"Max RPM for Motor 1: ±{max_rpm}")
        print(f"Current values: {current}")

        cli = Bullet(
            prompt="\nAdhesive Control:",
            choices=[
                "1. RPM (Motor 1)",
                "2. Flowrate A (Motor 2, µL/s)",
                "3. Flowrate B (Motor 3, µL/s)",
                "4. STOP ALL (set all to 0)",
                "5. EMERGENCY STOP (STOP ALL + restart listeners)",
                "Back",
            ],
            margin=2,
        )
        choice = cli.launch()

        if choice == "Back":
            return

        motor_index = None
        if choice.startswith("1."):
            motor_index = 0
        elif choice.startswith("2."):
            motor_index = 1
        elif choice.startswith("3."):
            motor_index = 2

        if motor_index is not None:
            unit_hint = " (RPM)" if motor_index == 0 else " (µL/s)"
            label = ["RPM", "Flowrate A", "Flowrate B"][motor_index]
            while True:
                print("\033c", end="")
                print("Motor 1 is in RPM; Motors 2 and 3 are in microliters per second (µL/s).")
                if motor_index == 0:
                    print(f"Maximum allowed value for RPM: ±{max_rpm}")
                elif motor_index in (1, 2):
                    print(f"Maximum allowed value for {label}: {max_val} µL/s")
                print(f"Current values: {current}")
                val = input(
                    f"New value for {label}{unit_hint} (empty to go back): "
                ).strip()
                if not val:
                    break  # return to selection menu

                # Validate numeric and max (limit only for flowrates)
                try:
                    num = float(val)
                except ValueError:
                    print("Please enter a numeric value.")
                    time.sleep(1)
                    continue

                if motor_index == 0 and abs(num) > max_rpm:
                    print(f"Value must be between -{max_rpm} and {max_rpm} RPM.")
                    time.sleep(1)
                    continue
                if motor_index in (1, 2) and abs(num) > max_val:
                    print(f"Value must be between -{max_val} and {max_val}.")
                    time.sleep(1)
                    continue

                # Accept and send
                current[motor_index] = str(num)
                cmd = ",".join(current)

                all_success = True
                for d in devices:
                    ok = _send_adhesive_command_tcp(d, cmd)
                    if not ok:
                        all_success = False

                print("Applied" if all_success else "Failed to apply", cmd)
                time.sleep(0.5)

        elif choice.startswith("4."):
            current = ["0", "0", "0"]
            cmd = "0,0,0"
            # Send STOP multiple times for robustness (emergency-stop behavior)
            repeats = 3
            for i in range(repeats):
                all_success = True
                for d in devices:
                    ok = _send_adhesive_command_tcp(d, cmd)
                    if not ok:
                        all_success = False
                if not all_success:
                    print(f"STOP attempt {i+1}/{repeats} failed on at least one device")
                time.sleep(0.1)
            print("\nSent STOP (0,0,0)" if all_success else "\nSTOP may not have reached all devices")
            time.sleep(0.5)

        elif choice.startswith("5."):
            # Emergency stop behavior: attempt STOP ALL and then restart listeners.
            _cli_emergency_stop(appstate)
        

def cli_menu_tracking(appstate: dict, plotter: PlotManager, config: str):
    """Tracking submenu: combined tracking (and later other modes)."""

    while True:
        print("\033c", end="")
        cli = Bullet(
            prompt="\nTracking:",
            choices=[
                "a. Combined tracking (Aruco + holes)",
                # Future extensions:
                # "b. Aruco-only tracking",
                # "c. Holes-only tracking",
                "Back",
            ],
            margin=2,
        )
        choice = cli.launch()

        if choice.startswith("a."):
            # Clean up any existing remote processes before starting
            cleanup_remote_python_processes(appstate["selected_devices"], config)
            appstate["server"].clear()
            cli_both_tracking(appstate=appstate, plotter=plotter)
        elif choice == "Back":
            return


def cli_main_menu(appstate: dict, plotter: PlotManager, config: str):
    """Top-level control menu, entered after initial linear setup.

    This replaces the old one-shot flow to combined tracking and allows
    the user to choose operations in any order.
    """

    while True:
        print("\033c", end="")
        cli = Bullet(
            prompt="Control System:",
            choices=[
                "1. Connect",
                "2. Component",
                "3. Assembly Robot",
                "4. Adhesive Robot",
                "5. Tracking",
                "6. Quit",
            ],
            margin=2,
        )
        choice = cli.launch()

        if choice.startswith("1."):
            cli_menu_devices(appstate, config)
        elif choice.startswith("2."):
            cli_menu_component(appstate)
        elif choice.startswith("3."):
            cli_menu_assembly_robot(appstate)
        elif choice.startswith("4."):
            cli_menu_adhesive_robot(appstate)
        elif choice.startswith("5."):
            cli_menu_tracking(appstate, plotter, config)
        elif choice.startswith("6."):
            break

    # After quitting the menu, perform cleanup and shutdown
    cleanup_remote_python_processes(appstate["selected_devices"], config)
    appstate["server"].close_server()
    print("Server closed")

if __name__ == "__main__":    

    # Select the correct SSH config file for your network and devices
    # config_lightsoff is the default config for LightsOff-5G travel router
    # config_jackslaptop is for jack to use his windows machine as a router
    # create new config files if you change the network
    # Ensure that your devices are on the config or else the app will not find them
    CONFIG = "config_lightsoff"

    # App state is a dict holding state data
    # this enables simple argument passing to cli functions
    APPSTATE = {
        "logging" : True,  # Enable logging of UDP messages to JSONL files
        "log_prefix" : "LogTesting",  # Prefix for log file names
        "server": None,  # UDP server instance for messaging
        "crane": None,  # Crane object (not implemented)
        "selected_component" : None,  # Selected component for tracking
        "selected_devices" : []  # List of selected remote devices
    }
    
    # clear terminal
    print("\033c", end="")  

    # Show Title
    title = "Lightsoff CLI App"
    print(f"\n{'#'*len(title)}\n{title}\n{'#'*len(title)}\n")
    
    # Start the UDP server
    APPSTATE["server"] = UDPServer()    
    APPSTATE["server"].start_server()    

    # Init the plot manager
    plotter = PlotManager(APPSTATE)

    # Connect to the Crane
    # TODO actually implement the below methods properly
    # APPSTATE["crane"] = Crane()
    # APPSTATE["crane"].connect()
    
    # User Selects From Online Devices (includes update code option)
    APPSTATE["selected_devices"] = cli_select_devices(config= CONFIG)

    # Set a default component (Component 0) until it is changed later
    # via the main menu.
    print("\nSetting default component: Component 0")
    APPSTATE["selected_component"] = Component(ComponentPositions(
        coarse=CranePosition(0,0,10,0,0,0),
        intermediate=CranePosition(0,0,5,0,0,0),
        fine=CranePosition(0,0,1,0,0,0),
        target=CranePosition(0,0,0,0,0,0)
        ),
        Aruco(
            id = 0,
            position=CranePosition(1,1,0,0,0,0)            
        )
    )

    # Immediately enter the new top-level menu. From there, the user can
    # choose Component, Assembly Robot (motors), Tracking, etc.
    cli_main_menu(APPSTATE, plotter, CONFIG)

