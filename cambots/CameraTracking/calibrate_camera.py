"""
Script for camera calibration using checkerboard pattern. Should be run on remote from the programs directory.

Runs on cambot devices to capture multiple checkerboard images, detect corners, perform camera calibration
to obtain intrinsic parameters (camera matrix, distortion coefficients), and save calibration data for
use in Aruco marker pose estimation and other computer vision tasks.
"""

import os
import sys
sys.path.append('../..')

import cv2
import numpy as np
from cambots.Utils import *

# Initialize camera pipeline for Jetson CSI camera
camera, size = camera_pipeline(CameraType.JETSON_CSI)

# Define checkerboard dimensions (corners per row, corners per column)
CHECKERBOARD = (8, 6)

# Calibration termination criteria
criteria = (cv2.TERM_CRITERIA_EPS +
            cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

# Lists to store 3D world points and 2D image points
threedpoints = []
twodpoints = []

# Physical size of checkerboard squares in meters
square_size = 2.4  # Size in fullscreen on HiWi Laptop

# Generate 3D world coordinates for checkerboard corners
objectp3d = np.zeros((1, CHECKERBOARD[0] * CHECKERBOARD[1], 3), np.float32)
objectp3d[0, :, :2] = np.mgrid[0:CHECKERBOARD[0], 0:CHECKERBOARD[1]].T.reshape(-1, 2)
objectp3d *= square_size  # Scale by square size

prev_img_shape = None

# Capture calibration images
images = []
num_images = 20

print("press s to capture and q to quit")

while len(images) < num_images:
    ret, frame = camera.read()
    if not ret:
        print("Failed to capture image")
        break
    cv2.imshow('frame', frame)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('s'):
        images.append(frame)
        print(f"Captured {len(images)} of {num_images}")
    elif key == ord('q'):
        break

cv2.destroyAllWindows()

# Process captured images for corner detection
count = 0
while count < num_images:

    image = images[count]
    count += 1

    print(f"scanning {count} of {num_images}")

    grayColor = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Find checkerboard corners
    ret, corners = cv2.findChessboardCorners(
                    grayColor, CHECKERBOARD,
                    cv2.CALIB_CB_ADAPTIVE_THRESH
                    + cv2.CALIB_CB_FAST_CHECK +
                    cv2.CALIB_CB_NORMALIZE_IMAGE)

    if ret == True:
        threedpoints.append(objectp3d)

        # Refine corner pixel coordinates
        corners2 = cv2.cornerSubPix(
            grayColor, corners, (11, 11), (-1, -1), criteria)

        twodpoints.append(corners2)

        # Draw detected corners on image
        image = cv2.drawChessboardCorners(image,
                                          CHECKERBOARD,
                                          corners2, ret)

    cv2.imshow('img', image)
    cv2.waitKey(0)

cv2.destroyAllWindows()

h, w = image.shape[:2]

# Perform camera calibration
ret, matrix, distortion, r_vecs, t_vecs = cv2.calibrateCamera(
    threedpoints, twodpoints, grayColor.shape[::-1], None, None)

# Display calibration results
print(" Camera matrix:")
print(matrix)

print("\n Distortion coefficient:")
print(distortion)

print("\n Rotation Vectors:")
print(r_vecs)

print("\n Translation Vectors:")
print(t_vecs)

# Save calibration data
calibration_data = {
    "camera_matrix": matrix,
    "distortion_coefficients": distortion,
    "rotation_vectors": r_vecs,
    "translation_vectors": t_vecs
}

save_path = "../../camera_calibration_data.npz"
np.savez(save_path, **calibration_data)

print("Camera calibration data saved to camera_calibration_data.npz")

# Verify calibration by reloading and computing reprojection error
print("Reloading data to confirm it is saved correctly")
with np.load(save_path) as data:
    camera_matrix = data["camera_matrix"]
    distortion_coefficients = data["distortion_coefficients"]

mean_error = 0
for i in range(len(threedpoints)):
    imgpoints2, _ = cv2.projectPoints(threedpoints[i], r_vecs[i], t_vecs[i], matrix, distortion)
    error = cv2.norm(twodpoints[i], imgpoints2, cv2.NORM_L2)/len(imgpoints2)
    mean_error += error

print( "total error: {}".format(mean_error/len(threedpoints)) )

# Test calibration by undistorting first image
print("Confirming the calibration is correct by undistorting first image")

first_image = images[0]
h, w = first_image.shape[:2]
new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(camera_matrix, distortion_coefficients, (w, h), 1, (w, h))

undistorted_image = cv2.undistort(first_image, camera_matrix, distortion_coefficients, None, new_camera_matrix)

# Display original and undistorted images for comparison
cv2.imshow('Original Image', first_image)
cv2.imshow('Undistorted Image', undistorted_image)
cv2.waitKey(0)
camera.release()
cv2.destroyAllWindows()