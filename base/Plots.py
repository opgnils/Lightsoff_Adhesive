"""
Plot functions for the PlotManager with standardized structure.

This module contains plot functions that follow a specific structure required by PlotManager:

Plot Function Structure:
1. Function signature: plot_func(fig, axs, appstate)
   - fig: matplotlib Figure object
   - axs: Array of subplot axes
   - appstate: Application state containing server, selected_component, etc.

2. Setup phase: Configure plot layout, create initial empty plot elements
3. Return update function: def update(frame) that returns plot elements tuple

4. Update function structure:
   - Takes frame number parameter (provided by matplotlib animation)
   - Processes latest data from appstate['server']
   - Updates plot elements with new data
   - Returns tuple of updated elements for matplotlib optimization

Available plot functions:
- test_plot: Simple test plot with fake data
- aruco_plot: 3D visualization of ArUco marker tracking with distance/time plots
- holes_plot: 2D image space visualization of hole detections
"""

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.axes import Axes
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import math
import numpy as np
import cv2

from base.UDPServer import UDPServer
from base.Devices import *
from base.Crane import *
from base.Components import *
from base.Plots import *
from base.PlotManager import *

# Color mapping for cambot IDs based on last two digits
COLORS = ['b', 'r', 'g', 'm', 'c', 'y', 'k', 'orange', 'purple', 'brown']

def create_camera_box(camera_pos, camera_rvec, size=(0.05, 0.05, 0.3)):
    """Create a 3D camera box positioned and oriented in world coordinates
    
    Args:
        camera_pos: Position of camera in world coordinates (3D vector)
            In our case, this is the camera position in the ArUco marker's coordinate system
        camera_rvec: Orientation of camera in world coordinates (rotation vector)
            In our case, this is the camera orientation in the ArUco marker's coordinate system
        size: Size of the camera box (width, height, depth)
    
    Returns:
        vertices: 3D vertices of the camera box
        faces: Face definitions for the box
    """
    # Define box vertices centered at origin
    # For OpenCV's coordinate system:
    # - X: right 
    # - Y: down
    # - Z: forward (camera's optical axis)
    # So we create a box with its "front" along +Z
    w, h, d = size
    vertices = np.array([
        # In OpenCV coordinates, Z is forward, so back face is at -Z, front at +Z
        [-w/2, -h/2, -d/2], [w/2, -h/2, -d/2], [w/2, h/2, -d/2], [-w/2, h/2, -d/2],  # back face
        [-w/2, -h/2, d/2], [w/2, -h/2, d/2], [w/2, h/2, d/2], [-w/2, h/2, d/2]     # front face
    ])
    
    # Get rotation matrix from camera orientation in marker space
    R_camera, _ = cv2.Rodrigues(camera_rvec)
    
    # Apply rotation and translation to position camera in marker's coordinate system
    rotated_vertices = vertices @ R_camera.T
    translated_vertices = rotated_vertices + camera_pos.flatten()
    
    # Define faces (indices into vertices array)
    faces = [
        [0, 1, 2, 3],  # back
        [4, 5, 6, 7],  # front
        [0, 1, 5, 4],  # bottom
        [2, 3, 7, 6],  # top
        [0, 3, 7, 4],  # left
        [1, 2, 6, 5]   # right
    ]
    
    return translated_vertices, faces

def create_aruco_marker(size=0.15):
    """Create a 2D ArUco marker as a rectangle at z=0
    
    In OpenCV coordinate system:
    - X axis is horizontal across the marker (right)
    - Y axis is vertical on the marker (down)
    - Z axis is perpendicular to the marker (forward)
    """
    s = size / 2
    # Define marker in XY plane at Z=0
    vertices = np.array([
        [-s, -s, 0], [s, -s, 0], [s, s, 0], [-s, s, 0]
    ])
    faces = [[0, 1, 2, 3]]
    return vertices, faces

def test_plot(fig, axs:Axes, appstate:dict):
    """
    Simple test plot function demonstrating the PlotManager structure.
    
    This function creates a basic sine wave plot that updates in real-time,
    showing how plot functions should be structured for the PlotManager:
    1. Setup phase: Configure axes and create initial plot elements
    2. Return update function: def update(frame) that processes data and updates elements
    
    Args:
        fig: matplotlib Figure object (unused in this simple example)
        axs: Array of subplot axes (we use axs[0] for the single plot)
        appstate: Application state containing server and other components
    
    Returns:
        update: Function that takes frame number and returns plot elements tuple
    """
    ax = axs[0]
    ax.set_title('Test Plot')
    ax.set_xlabel('Time')
    ax.set_ylabel('Value')
    line, = ax.plot([], [], 'b-')
    
    def update(frame):
        # Get test messages from the UDP server
        messages = appstate["server"].get_message_by_tag('test')
        
        # Generate fake data for demonstration - sine wave over time
        fake_x = range(int(time.time_ns()/10000), int(time.time_ns()/10000+10))
        fake_y = [math.sin(d/3) for d in fake_x]
        
        # Update the line with new data
        line.set_data(fake_x,fake_y)
        
        # Auto-scale the axes to fit the data
        ax.relim()
        ax.autoscale_view()
        
        # Return tuple of updated elements (required by matplotlib animation)
        return line,
    
    return update

def aruco_plot(fig, axs, appstate: dict):
    """
    Complex 3D visualization of ArUco marker tracking with multiple views.
    
    This function creates a comprehensive visualization showing:
    1. Distance over time plot (top subplot spanning both columns)
    2. 2D plan view (bottom left) - top-down view of camera positions
    3. 3D axonometric view (bottom right) - 3D visualization of cameras and marker
    
    The plot integrates with the DataFilter system to show:
    - Raw distance data (outliers marked as scatter points)
    - Filtered distance data (solid lines)
    - Smoothed distance data (dashed lines)
    
    Camera positions are shown as 3D boxes in the axonometric view and as
    directed circles in the plan view, with colors based on cambot ID.
    
    Args:
        fig: matplotlib Figure object to contain the subplots
        axs: Array of subplot axes (unused - we create our own layout)
        appstate: Application state containing server, selected_component, etc.
    
    Returns:
        update: Function that takes frame number and returns plot elements tuple
        
    Coordinate Systems:
    - ArUco marker coordinate system: Origin at marker center, Z perpendicular to marker
    - OpenCV camera coordinates: X right, Y down, Z forward from camera
    - Visualization coordinates: Match ArUco marker system for consistency
    """
    # Create subplot layout: distance plot on top, two 3D views below
    fig.clear()  # Clear any existing subplots
    
    # Top subplot: Distance over time (spans both columns)
    ax_distance = plt.subplot2grid((2, 2), (0, 0), colspan=2, fig=fig)
    ax_distance.set_title('ArUco Distance Plot')
    ax_distance.set_xlabel('Time (s)')
    ax_distance.set_ylabel('Distance (m)')
    ax_distance.set_ylim(0, 15)
    
    # Bottom left subplot: 2D plan view (top-down)
    ax_plan = plt.subplot2grid((2, 2), (1, 0), fig=fig)
    ax_plan.set_title('Plan View (Top-Down)')
    ax_plan.set_xlabel('X (m)')
    ax_plan.set_ylabel('Y (m)')
    ax_plan.set_xlim(-5, 5)
    ax_plan.set_ylim(-5, 5)
    ax_plan.grid(True)
    ax_plan.set_aspect('equal')  # Ensure square aspect ratio
    
    # Bottom right subplot: Axonometric view
    ax_axon = plt.subplot2grid((2, 2), (1, 1), projection='3d', fig=fig)
    ax_axon.set_title('Axonometric View')
    ax_axon.set_xlabel('X (m)')
    ax_axon.set_ylabel('Y (m)')
    ax_axon.set_zlabel('Z (m)')
    ax_axon.set_xlim(-5, 5)
    ax_axon.set_ylim(-5, 5)
    ax_axon.set_zlim(-0, 15)
    ax_axon.view_init(elev=30, azim=45)  # Axonometric view

    # Configure 3D view to show only horizontal grid (transparent vertical panes)
    ax_axon.grid(True)
    ax_axon.xaxis.pane.fill = False
    ax_axon.yaxis.pane.fill = False
    ax_axon.zaxis.pane.fill = False
    ax_axon.xaxis.pane.set_edgecolor('none')
    ax_axon.yaxis.pane.set_edgecolor('none')
    ax_axon.zaxis.pane.set_edgecolor('none')
    ax_axon.zaxis.set_pane_color((1.0, 1.0, 1.0, 0.0))  # Transparent Z pane
    
    # Create ArUco marker (fixed at origin) for reference in both views
    aruco_vertices, aruco_faces = create_aruco_marker(0.45)
    
    # Add ArUco marker to 2D plan view as a rectangle with orientation indicators
    marker_size = 0.45
    aruco_2d = plt.Rectangle((0,0), marker_size, marker_size, 
                             facecolor='black', alpha=0.8, edgecolor='white')
    ax_plan.add_patch(aruco_2d)
    
    # Add orientation indicators to the ArUco marker in 2D view
    # X-axis indicator (red)
    ax_plan.arrow(0, 0, marker_size/2, 0, head_width=0.02, head_length=0.03, fc='red', ec='red')
    # Y-axis indicator (green)
    ax_plan.arrow(0, 0, 0, marker_size/2, head_width=0.02, head_length=0.03, fc='green', ec='green')
    
    # Add ArUco marker to 3D axonometric view
    aruco_poly_axon = Poly3DCollection([aruco_vertices[face] for face in aruco_faces], 
                                       facecolors='black', alpha=0.8, edgecolors='white')
    ax_axon.add_collection3d(aruco_poly_axon)
    
    # Add coordinate axes to 3D view to indicate the ArUco marker's coordinate system
    marker_size = 0.45
    axis_length = marker_size * 1.5
    
    # X-axis (red)
    ax_axon.plot([0, axis_length], [0, 0], [0, 0], color='red', linewidth=2)
    # Y-axis (green)
    ax_axon.plot([0, 0], [0, axis_length], [0, 0], color='green', linewidth=2)
    # Z-axis (blue) - perpendicular to marker
    ax_axon.plot([0, 0], [0, 0], [0, axis_length], color='blue', linewidth=2)
    
    # Dictionary to store plot elements for each cambot_id
    distance_outliers = {}           # Scatter plots for outliers
    distance_filtered = {}           # Lines for filtered (non-outlier) data
    distance_smoothed = {}           # Dashed lines for smoothed data
    camera_boxes_plan = {}  # Now will store 2D rectangles/circles for plan view
    camera_boxes_axon = {}

    def update(frame):
        """
        Update function called by matplotlib animation for each frame.
        
        Processes latest ArUco tracking data from all cambots and updates
        the visualization with filtered/smoothed data and 3D camera positions.
        """
        messages = appstate['server'].get_message_by_tag('aruco', num=30)

        # Clear previous elements that are no longer active
        current_cambots = set(messages.keys())
        for cambot_id in list(distance_outliers.keys()):
            if cambot_id not in current_cambots:
                if cambot_id in distance_outliers:
                    distance_outliers[cambot_id].remove()
                    del distance_outliers[cambot_id]
                if cambot_id in distance_filtered:
                    distance_filtered[cambot_id].remove()
                    del distance_filtered[cambot_id]
                if cambot_id in distance_smoothed:
                    distance_smoothed[cambot_id].remove()
                    del distance_smoothed[cambot_id]
                if cambot_id in camera_boxes_plan:
                    # Handle both circle and direction line
                    if isinstance(camera_boxes_plan[cambot_id], list):
                        for item in camera_boxes_plan[cambot_id]:
                            item.remove()
                    else:
                        camera_boxes_plan[cambot_id].remove()
                    del camera_boxes_plan[cambot_id]
                if cambot_id in camera_boxes_axon:
                    camera_boxes_axon[cambot_id].remove()
                    del camera_boxes_axon[cambot_id]

        # Process messages for each cambot
        for cambot_id, cambot_messages in messages.items():
            if not cambot_messages:
                continue

            times = []
            distances = []
            latest_tvec = None
            latest_rvec = None
            
            # Extract time, distance, and position data from messages
            for message in cambot_messages:
                if 'time' in message and 'data' in message:
                    msg_time = message['time']
                    aruco_data = message['data']
                    
                    # Only process the marker matching the selected component's aruco id
                    selected_marker_id = appstate["selected_component"].aruco.id
                    if selected_marker_id is not None and selected_marker_id in aruco_data:
                        marker_data = aruco_data[selected_marker_id]
                        if 'distance' in marker_data:
                            times.append(msg_time)
                            distances.append(float(marker_data['distance']))
                        # Keep track of latest position data
                        if 'tvec' in marker_data and 'rvec' in marker_data:
                            latest_tvec = marker_data['tvec']
                            latest_rvec = marker_data['rvec']

            # Get color based on last two digits of cambot_id for consistent coloring
            last_digits = int(cambot_id[-2:]) if cambot_id[-2:].isdigit() else 0
            color = COLORS[last_digits % len(COLORS)]

            # Get the selected aruco marker ID for data filtering
            selected_marker_id = appstate["selected_component"].aruco.id
            
            # Get filtered data for this cambot using DataFilter interface
            distance_filtered_data = appstate['server'].get_filtered_data(
                tag="aruco", 
                cambot_id=cambot_id, 
                keys=("data", selected_marker_id, "distance"),
                num_points=30
            )
            
            # Get outliers for this cambot
            distance_outliers_data = appstate['server'].get_outliers(
                tag="aruco", 
                cambot_id=cambot_id, 
                keys=("data", selected_marker_id, "distance"),
                num_points=30
            )
            
            # Get smoothed data for this cambot
            distance_smoothed_data = appstate['server'].get_smoothed_data(
                tag="aruco", 
                cambot_id=cambot_id, 
                keys=("data", selected_marker_id, "distance"),
                window=5
            )
            
            # Plot outliers if available
            if distance_outliers_data is not None and not distance_outliers_data.empty:
                if cambot_id not in distance_outliers:
                    scatter = ax_distance.scatter([], [], color=color, alpha=0.5, s=50, marker='o')
                    distance_outliers[cambot_id] = scatter
                
                # Convert timestamps to seconds for plotting
                outlier_times = distance_outliers_data.index.astype(np.int64) / 10**9
                outlier_distances = distance_outliers_data['value'].values
                distance_outliers[cambot_id].set_offsets(list(zip(outlier_times, outlier_distances)))
            elif cambot_id in distance_outliers:
                # Clear outliers if no data - provide proper empty 2D array
                distance_outliers[cambot_id].set_offsets(np.empty((0, 2)))
            
            # Plot filtered data if available
            if distance_filtered_data is not None and not distance_filtered_data.empty:
                if cambot_id not in distance_filtered:
                    line, = ax_distance.plot([], [], color=color, linewidth=2)
                    distance_filtered[cambot_id] = line
                
                # Convert timestamps to seconds for plotting
                filtered_times = distance_filtered_data.index.astype(np.int64) / 10**9
                filtered_distances = distance_filtered_data['value'].values
                distance_filtered[cambot_id].set_data(filtered_times, filtered_distances)
            elif cambot_id in distance_filtered:
                # Clear filtered data if no data
                distance_filtered[cambot_id].set_data([], [])
            
            # Plot smoothed data if available
            if distance_smoothed_data is not None and not distance_smoothed_data.empty:
                if cambot_id not in distance_smoothed:
                    line, = ax_distance.plot([], [], color=color, linewidth=1.5, linestyle='--')
                    distance_smoothed[cambot_id] = line
                
                # Convert timestamps to seconds for plotting
                smoothed_times = distance_smoothed_data.index.astype(np.int64) / 10**9
                smoothed_distances = distance_smoothed_data['value'].values
                distance_smoothed[cambot_id].set_data(smoothed_times, smoothed_distances)
            elif cambot_id in distance_smoothed:
                # Clear smoothed data if no data
                distance_smoothed[cambot_id].set_data([], [])

            # Update 3D camera boxes and 2D plan view using smoothed position data
            # Get smoothed tvec and rvec data
            tvec_smoothed_data = appstate['server'].get_smoothed_data(
                tag="aruco", 
                cambot_id=cambot_id, 
                keys=("data", selected_marker_id, "tvec"),
                window=5
            )
            
            rvec_smoothed_data = appstate['server'].get_smoothed_data(
                tag="aruco", 
                cambot_id=cambot_id, 
                keys=("data", selected_marker_id, "rvec"),
                window=5
            )
            
            # Use smoothed data if available, otherwise fall back to latest raw data
            smoothed_tvec = None
            smoothed_rvec = None
            
            if tvec_smoothed_data is not None and not tvec_smoothed_data.empty:
                # Get the most recent smoothed tvec value
                smoothed_tvec = tvec_smoothed_data['value'].iloc[-1]
            
            if rvec_smoothed_data is not None and not rvec_smoothed_data.empty:
                # Get the most recent smoothed rvec value
                smoothed_rvec = rvec_smoothed_data['value'].iloc[-1]
            
            # Fall back to latest raw data if smoothed data is not available
            if smoothed_tvec is None or smoothed_rvec is None:
                if latest_tvec is not None and latest_rvec is not None:
                    smoothed_tvec = latest_tvec if smoothed_tvec is None else smoothed_tvec
                    smoothed_rvec = latest_rvec if smoothed_rvec is None else smoothed_rvec

            if smoothed_tvec is not None and smoothed_rvec is not None:
                # Remove old elements if they exist
                if cambot_id in camera_boxes_plan:
                    # Handle both circle and direction line
                    if isinstance(camera_boxes_plan[cambot_id], list):
                        for item in camera_boxes_plan[cambot_id]:
                            item.remove()
                    else:
                        camera_boxes_plan[cambot_id].remove()
                if cambot_id in camera_boxes_axon:
                    camera_boxes_axon[cambot_id].remove()
                
                # Convert rvec and tvec to proper numpy arrays if needed
                rvec_np = np.array(smoothed_rvec, dtype=np.float32)
                tvec_np = np.array(smoothed_tvec, dtype=np.float32)
                
                # Get rotation matrix from marker to camera coordinate system
                R_marker_to_cam, _ = cv2.Rodrigues(rvec_np)
                
                # OpenCV's coordinate system:
                # - X: right in the image plane
                # - Y: down in the image plane
                # - Z: forward from the camera (i.e., into the scene)
                
                # ArUco marker coordinate system (as defined in track_aruco.py):
                # - Origin: center of the marker
                # - X: along the marker width
                # - Y: along the marker height
                # - Z: perpendicular to the marker (normal)
                
                # The camera position in world coordinates (ArUco marker space)
                # Apply inverse transform to get camera position relative to marker
                R_cam_to_marker = R_marker_to_cam.T  # Transpose for inverse rotation
                tvec_flat = tvec_np.flatten()
                camera_pos_world = -R_cam_to_marker @ tvec_flat  # Camera position in marker frame
                
                # For visualization, we need to handle the coordinate system difference:
                # In OpenCV's system, Z is forward from camera, but in our 3D plot
                # we typically want Z to be up, Y to be forward, and X to be right
                
                # Option 1: Keep OpenCV's coordinate system (Z forward)
                # This matches the direct output from cv2.solvePnP
                camera_rvec_world = cv2.Rodrigues(R_cam_to_marker)[0]
                
                # Optional: Transform coordinates if we want Z to be up
                # Uncomment this code if you want to visualize with Z as up
                # transform_to_zup = np.array([
                #     [1, 0, 0],
                #     [0, 0, 1],  # Y -> Z (Y becomes up)
                #     [0, -1, 0]  # Z -> -Y (forward becomes -Y)
                # ])
                # camera_pos_world = transform_to_zup @ camera_pos_world
                # R_cam_to_marker_zup = transform_to_zup @ R_cam_to_marker @ transform_to_zup.T
                # camera_rvec_world = cv2.Rodrigues(R_cam_to_marker_zup)[0]
                
                # Create 3D camera box for axonometric view in ArUco marker's coordinate system
                camera_vertices, camera_faces = create_camera_box(camera_pos_world, camera_rvec_world, size=(0.15, 0.15, 0.9))
                
                # Add 2D representation to plan view
                x_pos = float(camera_pos_world[0])
                y_pos = float(camera_pos_world[1])
                
                # Instead of just a circle, use a directed marker to show orientation
                # Extract camera forward direction in XY plane
                R_cam, _ = cv2.Rodrigues(camera_rvec_world)
                
                # In OpenCV camera coordinates:
                # - Z axis is the optical axis (forward from camera)
                # - X is to the right
                # - Y is down
                # For our 2D plan view (top-down), we need to project the camera's 
                # forward direction (Z-axis) onto the XY plane
                forward_vec = R_cam[:, 2]  # Camera Z axis (optical axis)
                
                # Project onto XY plane - this gives us the camera's forward direction
                # in the ArUco marker's XY plane
                forward_xy = np.array([forward_vec[0], forward_vec[1]])
                
                # Normalize if not zero
                norm = np.linalg.norm(forward_xy)
                if norm > 1e-6:  # Avoid division by zero
                    forward_xy = forward_xy / norm
                else:
                    # If the camera is pointing straight up or down, we won't see direction in XY plane
                    # In that case, use the X axis direction as default
                    forward_xy = np.array([R_cam[0, 0], R_cam[1, 0]])
                
                # Create a circle with a line indicating direction
                camera_circle = plt.Circle((x_pos, y_pos), 0.15, facecolor=color, alpha=0.7, edgecolor='black')
                ax_plan.add_patch(camera_circle)
                
                # Add direction indicator line (scaled to be visible)
                line_length = 0.45
                end_x = x_pos + forward_xy[0] * line_length
                end_y = y_pos + forward_xy[1] * line_length
                direction_line = ax_plan.plot([x_pos, end_x], [y_pos, end_y], color='black', linewidth=1.5)[0]
                
                # Store both the circle and line for removal later
                camera_boxes_plan[cambot_id] = [camera_circle, direction_line]
                
                # Add 3D camera box to axonometric view
                camera_poly_axon = Poly3DCollection([camera_vertices[face] for face in camera_faces], 
                                                   facecolors=color, alpha=0.7, edgecolors='black')
                camera_boxes_axon[cambot_id] = ax_axon.add_collection3d(camera_poly_axon)

        # Update axis limits (no legend)
        ax_distance.relim()
        ax_distance.autoscale_view()

        # Collect all plot elements to return
        plot_elements = list(distance_outliers.values()) + list(distance_filtered.values()) + list(distance_smoothed.values())
        
        # Add plan view elements (both circles and lines)
        plan_elements = []
        for item in camera_boxes_plan.values():
            if isinstance(item, list):
                plan_elements.extend(item)
            else:
                plan_elements.append(item)
        
        # Add axon view elements
        plot_elements.extend(plan_elements)
        plot_elements.extend(list(camera_boxes_axon.values()))
        
        return plot_elements

    return update


def holes_plot(fig, axs:Axes, appstate:dict):
    """
    2D visualization of hole detections in image space.
    
    This function creates a single plot showing hole detections as they appear
    in the camera's image coordinate system (pixel coordinates). Each hole is
    visualized with:
    - Colored circle outline at the detection center
    - Semi-transparent bounding box fill
    - Dashed line from detection center to image center (target location)
    - Hole ID text label
    
    A red crosshair marks the image center (640, 360) as the target location.
    Colors are assigned based on cambot ID for multi-camera visualization.
    
    Args:
        fig: matplotlib Figure object to contain the plot
        axs: Array of subplot axes (unused - we create our own layout)
        appstate: Application state containing server and other components
    
    Returns:
        update: Function that takes frame number and returns plot elements tuple
    """
    # Clear and rebuild the figure layout each time (like aruco_plot)
    fig.clear()
    
    # Create single subplot for the image space
    ax = fig.add_subplot(1, 1, 1)
    ax.set_title('Holes Detection Plot')
    ax.set_xlabel('X (pixels)')
    ax.set_ylabel('Y (pixels)')
    ax.set_xlim(0, 1280)
    ax.set_ylim(0, 720)
    ax.set_aspect('equal')
    ax.invert_yaxis()  # Image origin is top-left
    
    # Add crosshair at image center (target location)
    image_center_x = 1280 / 2  # 640
    image_center_y = 720 / 2   # 360
    crosshair_length = 20
    
    # Horizontal line of crosshair
    ax.plot([image_center_x - crosshair_length, image_center_x + crosshair_length], 
            [image_center_y, image_center_y], color='red', linewidth=1, linestyle='-', alpha=0.8, zorder=1)
    # Vertical line of crosshair
    ax.plot([image_center_x, image_center_x], 
            [image_center_y - crosshair_length, image_center_y + crosshair_length], 
            color='red', linewidth=1, linestyle='-', alpha=0.8, zorder=1)
    
    # Store plot elements for each cambot_id
    circles = {}
    boxes = {}
    texts = {}
    lines = {}
    
    def update(frame):
        """
        Update function called by matplotlib animation for each frame.
        
        Processes latest hole detection data from all cambots and updates
        the image space visualization with bounding boxes, circles, and labels.
        """
        messages = appstate['server'].get_message_by_tag('holes', num=30)
        
        # Clear previous elements that are no longer active
        current_cambots = set(messages.keys())
        for cambot_id in list(circles.keys()):
            if cambot_id not in current_cambots:
                if cambot_id in circles:
                    for circle in circles[cambot_id]:
                        circle.remove()
                    del circles[cambot_id]
                if cambot_id in boxes:
                    for box in boxes[cambot_id]:
                        box.remove()
                    del boxes[cambot_id]
                if cambot_id in texts:
                    for text in texts[cambot_id]:
                        text.remove()
                    del texts[cambot_id]
                if cambot_id in lines:
                    for line in lines[cambot_id]:
                        line.remove()
                    del lines[cambot_id]
        
        # Process messages for each cambot
        for cambot_id, cambot_messages in messages.items():
            if not cambot_messages:
                continue
                
            # Get the latest message data
            latest_message = cambot_messages[-1] if cambot_messages else None
            if not latest_message or 'data' not in latest_message:
                continue
                
            # Extract bounding box data from nested structure
            data = latest_message['data']
            
            # Remove old elements for this cambot
            if cambot_id in circles:
                for circle in circles[cambot_id]:
                    circle.remove()
                del circles[cambot_id]
            if cambot_id in boxes:
                for box in boxes[cambot_id]:
                    box.remove()
                del boxes[cambot_id]
            if cambot_id in texts:
                for text in texts[cambot_id]:
                    text.remove()
                del texts[cambot_id]
            if cambot_id in lines:
                for line in lines[cambot_id]:
                    line.remove()
                del lines[cambot_id]
            
            # Get color based on last two digits of cambot_id
            last_digits = int(str(cambot_id)[-2:]) if str(cambot_id)[-2:].isdigit() else 0
            color = COLORS[last_digits % len(COLORS)]
            
            # Initialize lists to store multiple circles, boxes, texts, and lines for this cambot
            circles[cambot_id] = []
            boxes[cambot_id] = []
            texts[cambot_id] = []
            lines[cambot_id] = []
            
            # Process each detection (numbered keys in data)
            for detection_id, detection_data in data.items():
                if 'bbox' not in detection_data:
                    continue
                    
                bbox = detection_data['bbox']
                x1, y1, x2, y2 = bbox
                
                # Calculate center and radius for circle to be smaller than bounding box
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                r = min((x2 - x1), (y2 - y1)) / 2 - 3  # Make it 3 pixels smaller
                
                # Draw circle outline only with cambot color
                circle = plt.Circle((cx, cy), r, facecolor='none', edgecolor=color, linewidth=2, alpha=1.0, zorder=3)
                ax.add_patch(circle)
                circles[cambot_id].append(circle)
                
                # Draw dashed line from circle center to image center (50% opacity)
                image_center_x = 1280 / 2  # 640
                image_center_y = 720 / 2   # 360
                line, = ax.plot([cx, image_center_x], [cy, image_center_y], 
                               color=color, linewidth=1.5, linestyle='--', alpha=0.5, zorder=1)
                lines[cambot_id].append(line)
                
                # Draw bounding box with fill only, no border
                box = plt.Rectangle((x1, y1), x2 - x1, y2 - y1, facecolor=color, alpha=0.25, edgecolor='none', zorder=2)
                ax.add_patch(box)
                boxes[cambot_id].append(box)
                
                # Add hole ID text above the upper left corner of bounding box
                text = ax.text(x1 + 2, y1 - 2, str(detection_id), fontsize=12, color=color, 
                              weight='bold', ha='left', va='bottom', zorder=4)
                texts[cambot_id].append(text)
        
        # Update axis limits
        ax.relim()
        ax.autoscale_view()
        
        # Return all plot elements (flatten the lists)
        plot_elements = []
        for circle_list in circles.values():
            plot_elements.extend(circle_list)
        for box_list in boxes.values():
            plot_elements.extend(box_list)
        for text_list in texts.values():
            plot_elements.extend(text_list)
        for line_list in lines.values():
            plot_elements.extend(line_list)
        return plot_elements
        
    return update