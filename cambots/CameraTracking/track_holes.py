"""
Remote script for hole detection and tracking using YOLO.

Runs on cambot devices to detect holes in camera feed using trained YOLO model, track them across frames with norfair,
and send data via UDP to the base station for real-time processing. Includes visualization and recording capabilities.
"""

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import cv2
import numpy as np
import time
from norfair import Detection, Tracker
from ultralytics import YOLO
from cambots.Network import Network
import queue
from threading import Thread

from cambots.Utils import *

# Check if display is available for real-time visualization
display_connected = is_display_available()
print(f"DISPLAY: {display_connected}")

# Initialize camera pipeline for Jetson CSI camera
camera, size = camera_pipeline(CameraType.JETSON_CSI)

# Load YOLO model for hole detection
model_name = "best.engine"
model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), f'../yolo/models/{model_name}'))
model = YOLO(model_path, task = 'detect')

# Setup recording parameters
b_record = True  # Enable video recording
video_name = f"Tracking_Record_{time.time()}"  # Unique video filename with timestamp
duration = 10000  # Maximum recording duration in seconds

# Setup save directory for recorded videos
username = os.getlogin()
root = os.path.dirname(os.path.abspath(__file__))
save_dir = os.path.join(root, f"../save/{username}/cambot_capture")
os.makedirs(save_dir, exist_ok=True)
video_filename = os.path.join(save_dir, f"{video_name}.avi")

# Initialize video writer for recording
fourcc = cv2.VideoWriter_fourcc(*'XVID')
out = cv2.VideoWriter(video_filename, fourcc, 20.0, size)

# Initialize norfair tracker for object tracking across frames
tracker = Tracker(
    distance_function="euclidean",  # Distance metric for tracking
    distance_threshold=170,  # Maximum distance to associate detections
    initialization_delay=3,  # Frames to wait before initializing track
    hit_counter_max=5  # Frames without detection before removing track
)

# Determine server IP for UDP communication
if 'SSH_CLIENT' in os.environ:
    server_ip = os.environ.get('SSH_CLIENT', '').split()[0]  # IP from SSH connection
    print(f"Using SSH Server IP: {server_ip}")
else: 
    server_ip = '192.168.8.156'  # Default fallback IP
    print(f"Using Default Server IP: {server_ip}")

# Initialize network communication
network = Network(server_address=server_ip)
network.open_socket()

# Send start signal to base station
network.send_pickle_packet({}, tag='start')

# Setup frame capture on separate thread for smooth processing
frame_queue = queue.Queue(maxsize=1)  # Queue to buffer latest frame

def capture_frames():
    """Continuously capture frames from camera and add to queue."""
    global frame_queue
    while True:
        ret, frame = camera.read()
        if not ret:
            break
        if not frame_queue.full():
            frame_queue.put(frame)

# Start frame capture thread
capture_thread = Thread(target=capture_frames, daemon=True)
capture_thread.start()

# Main processing loop
start_time = time.time()
while b_record is False or (time.time() - start_time) < duration:
    try:
        if frame_queue.qsize() == 0:
            pass    
        frame = frame_queue.get(timeout=1)
        
        # Run YOLO detection on current frame
        results = model(frame)

        # Prepare custom detections list from YOLO results
        custom_detections = []
        
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = box.conf[0].item()
                cls_id = int(box.cls[0].item())
                label = result.names[cls_id]
                custom_detections.append([x1, y1, x2, y2, conf, label])

        # Convert custom detections to norfair Detection objects
        norfair_detections = []
        for det in custom_detections:
            x1, y1, x2, y2, conf, label = det
            if label in ["slot_hole", "other_hole"]:  # Filter for relevant hole types
                center = np.array([(x1 + x2) / 2, (y1 + y2) / 2])  # Compute center for tracking
                bbox = [x1, y1, x2, y2]  # Store bounding box for drawing
                norfair_detections.append(
                    Detection(points=center, scores=np.array([conf]), data={"bbox": bbox, "label": label})
                )

        # Update tracker with new detections
        tracked_objects = tracker.update(detections=norfair_detections)

        # Define colors for visualization
        colors = {
            "Unknown": (0, 255, 255),
            "other_hole": (255, 100, 0),
            "slot_hole": (0, 255, 0)
        }   

        # Prepare data packet for tracked objects
        packet = {}
        for obj in tracked_objects:
            if obj.last_detection is not None:
                packet[obj.id] = obj.last_detection.data
                
                # Draw bounding boxes and labels if recording or displaying
                if (b_record or display_connected):
                    bbox = obj.last_detection.data["bbox"]
                    x1, y1, x2, y2 = map(int, bbox)
                    label = obj.last_detection.data.get("label", "Unknown")
                    col = colors[label] if label in colors.keys() else (0,0,255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), colors[label], 2)
                    cv2.putText(
                        frame,
                        f"{label} ID: {obj.id}",
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.9,
                        col,
                        2,
                    )  
                          
        # Send tracked data to base station
        network.send_pickle_packet(packet, tag="holes")

        # Record frame if enabled
        if b_record: out.write(frame)

        # Display frame if display is connected
        if display_connected:
            cv2.imshow("Tracked Objects", frame)
            cv2.namedWindow("Tracked Objects")
        
        else:
            print(f"tracking: {[o.id for o in tracked_objects if o.last_detection is not None]}")        
        
        # Check for quit key
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        
        # Check for stop signal from base station
        if network.check_for_stop_message() or network.check_for_stop_message() or network.check_for_stop_message():
            network.send_pickle_packet({},tag="stop")
            print("stop code received - terminating")
            break

    except queue.Empty:
        # No frame available within timeout; skip this iteration
        continue

# Cleanup resources
camera.release()
cv2.destroyAllWindows()
network.close_socket()

if b_record:
    out.release()
    print(f"Video saved as {video_filename}")

