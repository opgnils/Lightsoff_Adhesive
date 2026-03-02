"""
Remote script for testing camera functionality.

Runs on cambot devices to detect machine type, configure camera pipeline based on user input (CSI/USB),
and display a test video feed for 5 seconds to verify camera setup and connectivity.
"""

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import cv2
from cambots.Utils import *
import time

# Detect and print machine type for configuration
print("Detecting machine type...")
machine_type = detect_machine_type()
print(f"Detected machine type: {machine_type}")

# Get camera type from user input
camera_input = input("Is the camera CSI or USB? (Enter 'csi' or 'usb'): ").strip().lower()
if camera_input == 'csi':
    camera_type = CameraType.JETSON_CSI if machine_type == MachineType.JETSON else CameraType.PI_CSI
elif camera_input == 'usb':
    camera_type = CameraType.USB
else:
    print("Invalid input. Exiting...")
    sys.exit(1)

# Get video device index for USB cameras
if camera_type == CameraType.USB:
    video_idx = input("Enter the video device ID (e.g., 0, 1, 2): ").strip()
    try:
        video_idx = int(video_idx)
    except ValueError:
        print("Invalid video device ID. Exiting...")
        sys.exit(1)
else:
    video_idx = 0

# Setup camera pipeline based on machine type
if machine_type == MachineType.JETSON:
    print("Setting up camera pipeline for Jetson...")
    camera_type = CameraType.JETSON_CSI if camera_input == 'csi' else CameraType.USB
    camera, size = camera_pipeline(camera_type, video_idx, machine_type)
elif machine_type == MachineType.PI:
    print("Setting up camera pipeline for Raspberry Pi...")
    camera_type = CameraType.PI_CSI if camera_input == 'csi' else CameraType.USB
    camera, size = camera_pipeline(camera_type, video_idx, machine_type)
else:
    print("Unknown machine type. Exiting...")
    sys.exit(1)

# Check display availability for video feed
if is_display_available():
    print("Display is available. Camera feed will be shown.")
else:
    print("Display is not available. Camera feed will not be shown.")
    sys.exit(1)

# Test video stream for 5 seconds
print("Starting video stream. Press 'q' to quit early.")
start_time = time.time()
while True:
    ret, frame = camera.read()
    if not ret:
        print("Failed to grab frame.")
        break
    cv2.imshow("Camera Feed", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
    if time.time() - start_time > 5:
        break

# Cleanup resources
camera.release()
cv2.destroyAllWindows()