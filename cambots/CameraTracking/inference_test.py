"""
Script for testing YOLO inference with object tracking.

Tests YOLO model performance on video files or webcam feed with real-time object tracking using norfair.
Allows model format selection (PyTorch, ONNX, TensorRT, NCNN) and optional video recording of
tracked results with bounding boxes and track IDs for hole detection evaluation.
"""

import os
import sys
sys.path.append('../..')

from ultralytics import YOLO
import cv2
import os
from norfair import Detection, Tracker
import numpy as np
import time
from bullet import Bullet

# Define available model formats and their paths
model_options = {
    "engine": r'../yolo/models/best.engine',  # TensorRT for Jetson
    "onnx": r'../yolo/models/best.onnx',      # ONNX for cross-platform
    "ncnn": r'../yolo/models/best_ncnn_model',
    "pt": r'../yolo/models/best.pt'           # PyTorch original
}

# Interactive model selection using bullet CLI
cli = Bullet(
    prompt="Select a model to load: ",
    choices=list(model_options.keys()),
    indent=0,
    align=5,
    margin=1,
    shift=0,
)

selected_model_type = cli.launch()
model_path = model_options[selected_model_type]

# Load the selected YOLO model
model = YOLO(model_path, task='detect')

# Input source configuration
test_video_path = r"../yolo/test_video/outside_data_03.avi"
webcam = False

if webcam is False:
    cap = cv2.VideoCapture(test_video_path)
else:
    cap = cv2.VideoCapture(0)

# Initialize norfair tracker for object tracking
tracker = Tracker(
    distance_function="euclidean",  # Distance metric between object centers
    distance_threshold=170,         # Maximum distance to associate detections
    initialization_delay=3,         # Frames to wait before initializing track
    hit_counter_max=10              # Frames without detection before removing track
)

# Recording setup variables
i_record = None
b_record = False
i_video_name = None
i_duration = -1

# Ask user if they want to record the session
while i_record not in ["y", "n"]:
    i_record = input("Record the Session? [y/n]").lower()

if i_record == "y":
    # Create unique filename for recorded video
    video_filename = test_video_path.removesuffix(".avi") + f"tracked_{time.time()}.avi"

    # Initialize video writer
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(video_filename, fourcc, 20.0, (1536, 864))
    b_record = True

# Main inference and tracking loop
count = 0
while True:
    # Read frame from video/webcam
    ret, frame = cap.read()
    if not ret:
        print("No Frames Found")
        break

    # Run YOLO inference
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
        # Compute center for tracking
        center = np.array([(x1 + x2) / 2, (y1 + y2) / 2])
        # Store bounding box for drawing
        bbox = [x1, y1, x2, y2]
        norfair_detections.append(
            Detection(points=center, scores=np.array([conf]), data={"bbox": bbox, "label": label})
        )

    # Update tracker with new detections
    tracked_objects = tracker.update(detections=norfair_detections)

    # Color mapping for different hole types
    colors = {
        "Unknown": (0, 255, 255),
        "other_hole": (255, 100, 0),
        "slot_hole": (0, 255, 0)
    }

    # Draw tracked objects on frame
    for obj in tracked_objects:
        if obj.last_detection is not None:
            # Get bounding box from last detection
            bbox = obj.last_detection.data["bbox"]
            x1, y1, x2, y2 = map(int, bbox)
            # Get label from last detection
            label = obj.last_detection.data.get("label", "Unknown")
            # Draw bounding box
            col = colors[label] if label in colors.keys() else (0, 0, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)

            # Draw track ID and label
            cv2.putText(
                frame,
                f"{label} ID: {obj.id}",
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                col,
                2,
            )

    # Display the tracked frame
    cv2.imshow("Tracked Objects", frame)
    cv2.namedWindow("Tracked Objects")

    # Write frame to video if recording
    if b_record: out.write(frame)

    # Check for quit key
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Cleanup resources
cap.release()
cv2.destroyAllWindows()

if b_record:
    out.release()
    print(f"Video saved as {video_filename}")




