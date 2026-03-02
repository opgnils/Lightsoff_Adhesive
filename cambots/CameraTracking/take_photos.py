"""
Remote script for interactive photo capture and saving.

Runs on cambot devices to capture photos interactively via user input, display frames in real-time if possible,
and save captured images to a timestamped session directory for later use in calibration or testing.
"""

import os
import sys
sys.path.append('../..')

import cv2
import os
from cambots.Utils import *

# Check if display is available for real-time visualization
display_connected = is_display_available()
print(f"DISPLAY: {display_connected}")

# Initialize camera pipeline for Jetson CSI camera
camera, size = camera_pipeline(CameraType.JETSON_CSI)

# List to store captured images
images = []

# Get session name for organizing photos
session_name = input("Please provide a name for this photo session").strip().lower()

# Interactive capture loop
i = 0
while True:
    ret, frame = camera.read()
    if not ret:
        print("Failed to capture image")
        break

    # Display frame if display is connected
    if display_connected: 
        cv2.imshow('frame', frame)

    # Get user input for capture or quit
    key = input("Press 's' to capture an image or 'q' to quit: ").strip().lower()
    if key == 's':
        images.append(frame)
        print(f"Captured {i+1}")
        i += 1
    elif key == 'q':
        break

# Cleanup display
cv2.destroyAllWindows()

# Setup save directory
username = os.getlogin()
save_dir = f"../save/{username}/cambot_capture"
os.makedirs(save_dir, exist_ok=True)

# Save captured images
for idx, image in enumerate(images):
    filename = os.path.join(save_dir, f"{session_name}_{idx+1:05d}.png")
    cv2.imwrite(filename, image)
    print(f"Saved {filename}")

# Release camera
camera.release()