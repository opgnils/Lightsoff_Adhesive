import os
import cv2
from enum import Enum

def is_display_available():
    # Check if running in an X11 or Wayland session
    return bool(("DISPLAY" in os.environ and os.environ["DISPLAY"]) or ("WAYLAND_DISPLAY" in os.environ))

class MachineType(Enum):
    UNKNOWN = 'unknown'
    PI = 'pi'
    JETSON = 'jetson'

class CameraType(Enum):
    USB = 'usb'
    PI_CSI = 'pi_csi'
    JETSON_CSI = 'jetson_csi'


def detect_machine_type()-> MachineType:
    username = os.getlogin()
    if 'j' in username.lower():
        machine_type = MachineType.JETSON
    else:
        machine_type = MachineType.PI
    return machine_type

def camera_pipeline(camera_type, video_index = 0, machine_type = MachineType.UNKNOWN):

    if machine_type == MachineType.UNKNOWN:
        machine_type = detect_machine_type()

    if machine_type == MachineType.PI:
        if camera_type == CameraType.PI_CSI:
            # Raspberry Pi CSI camera pipeline
            width = 1280
            height = 720
            cam_hardware = "/base/axi/pcie@120000/rp1/i2c@88000/imx708@1a"
            pipeline = "libcamerasrc camera-name=%s ! video/x-raw,width=%d,height=%d,framerate=56/1,format=BGR ! appsink" % (cam_hardware, width, height)
            camera = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            size = (width, height)
        elif camera_type == CameraType.USB:
            raise NotImplementedError("USB camera pipeline is not implemented.")

    elif machine_type == MachineType.JETSON:
        if camera_type == CameraType.JETSON_CSI:
            # Jetson CSI camera pipeline
            pipeline = "nvarguscamerasrc ! video/x-raw(memory:NVMM), width=1280, height=720, format=NV12, framerate=60/1 ! nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! appsink"
            camera = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            size = (1280, 720)
        elif camera_type == CameraType.USB:
            # Jetson USB camera pipeline
            width = 1920
            height = 1080
            camera = cv2.VideoCapture(video_index, cv2.CAP_V4L2)
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            size = (width, height)
        else:
            raise ValueError("Unsupported camera type for Jetson: %s" % camera_type)
    else:
        raise ValueError("Unsupported machine type: %s" % machine_type)
    
    if not camera.isOpened():
        print("Error: Could not open the camera pipeline.")
        exit()

    return camera, size