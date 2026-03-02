"""
Remote script for Aruco marker detection and tracking.

Runs on cambot devices to detect Aruco markers in camera feed, calculate pose and distance using camera calibration,
and send data via UDP to the base station for real-time processing. Includes visualization and recording capabilities.
"""

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import cv2
import numpy as np
import time
from cambots.Network import Network
import queue
from threading import Thread
from cambots.Utils import *

# Check if display is available for real-time visualization
display_connected = is_display_available()
print(f"DISPLAY: {display_connected}")

# Initialize camera pipeline for Jetson CSI camera
camera, size = camera_pipeline(CameraType.JETSON_CSI)

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

# Load camera calibration data for accurate pose estimation
calibration_filepath = os.path.abspath(os.path.join(os.path.dirname(__file__), "../camera_calibration_data.npz"))

if not os.path.exists(calibration_filepath):
    raise Exception("Camera is not calibrated. Calibration file not found.")

with np.load(calibration_filepath) as data:
    camera_matrix = data['camera_matrix']  # Camera intrinsic matrix
    dist_coeffs = data["distortion_coefficients"]  # Lens distortion coefficients

# Aruco marker size in meters for pose calculation
ARUCO_SIZE = 0.15

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

    time.sleep(0.05)   

    if frame_queue.qsize()==0: pass    
    frame = frame_queue.get(timeout=1)

    # Detect Aruco markers in current frame
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
    aruco_params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)
    corners, ids, rejected = detector.detectMarkers(frame)

    if ids is not None:
        # Define 3D object points for pose estimation
        obj_points = np.array([
            [-ARUCO_SIZE/2,  ARUCO_SIZE/2, 0],
            [ ARUCO_SIZE/2,  ARUCO_SIZE/2, 0],
            [ ARUCO_SIZE/2, -ARUCO_SIZE/2, 0],
            [-ARUCO_SIZE/2, -ARUCO_SIZE/2, 0]
        ], dtype=np.float32)

        rvecs, tvecs = [], []
        for corner in corners:
            img_points = corner.reshape(4, 2).astype(np.float32)
            success, rvec, tvec = cv2.solvePnP(obj_points, img_points, camera_matrix, dist_coeffs)
              
        if success:
            rvecs.append(rvec)
            tvecs.append(tvec)
        else:
            rvecs.append(None)
            tvecs.append(None)

        packet = {}

        for corner, id, rvec, tvec in zip(corners, ids, rvecs, tvecs):
            id = int(id[0])

            cv2.aruco.drawDetectedMarkers(frame, [corner], borderColor=(0, 0, 255))                 
        
            distance = np.linalg.norm(tvec)

            print(f"Distance to marker: {distance:.2f} meters")            
            cv2.putText(frame, f"Distance: {distance:.2f}m", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)

            packet[id] = {
                "corners" : corner,
                "distance" : distance,
                "tvec" : tvec,
                "rvec" : rvec
                }

        network.send_pickle_packet(packet, tag="aruco")

    else:
        network.send_pickle_packet({}, tag = "aruco")
    
        
    aruco_detected = ids is not None
    text_aruco = f"Aruco detected: {aruco_detected}"
    cv2.putText(frame, text_aruco, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)

    # Record frame if enabled
    if b_record: out.write(frame)

    # Display frame if display is connected
    if display_connected:
        cv2.imshow("Tracked Objects", frame)
        cv2.namedWindow("Tracked Objects")
        
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

    # Check for stop signal from base station
    if network.check_for_stop_message() or network.check_for_stop_message() or network.check_for_stop_message():
        network.send_pickle_packet({},tag="stop")
        print("stop code received - terminating")
        break

# Cleanup resources
camera.release()
cv2.destroyAllWindows()
network.close_socket()

if b_record:
    out.release()
    print(f"Video saved as {video_filename}")