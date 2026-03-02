"""
Remote script for video recording with specified duration.

Runs on cambot devices to record video for a user-specified duration, display frames in real-time if possible,
and save the video to a timestamped file for later analysis or testing purposes.
"""

import os
import sys
sys.path.append('../..')

import cv2
import os
import time
from cambots.Utils import *

# Check if display is available for real-time visualization
display_connected = is_display_available()
print(f"DISPLAY: {display_connected}")

# Initialize camera pipeline for Jetson CSI camera
camera, size = camera_pipeline(CameraType.JETSON_CSI)

# Setup save directory
username = os.getlogin()
save_dir = f"../save/{username}/cambot_capture"

# Get video name and duration from user
video_name = input("Please provide a name for the video : ")
duration = int(input("How long of a video? (sec) : "))

# Ensure save directory exists
os.makedirs(save_dir, exist_ok=True)
video_filename = os.path.join(save_dir, f"{video_name}.avi")

# Initialize video writer
fourcc = cv2.VideoWriter_fourcc(*'XVID')
out = cv2.VideoWriter(video_filename, fourcc, 20.0, size)

# Recording loop
start_time = time.time()

while (time.time() - start_time) < duration:
    ret, frame = camera.read()
    if not ret:
        print("Failed to capture image")
        break

    # Display frame if display is connected
    if display_connected:
        cv2.imshow('frame', frame)

    # Write frame to video
    out.write(frame)

    # Check for quit key
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break

# Cleanup resources
cv2.destroyAllWindows()
camera.release()
out.release()
print(f"Video saved as {video_filename}")
