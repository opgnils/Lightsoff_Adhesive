"""
Script for converting YOLO models to TensorRT format.

Converts trained YOLO models (.pt) to TensorRT engine format (.engine) for optimized inference
on NVIDIA Jetson devices, enabling faster hole detection with FP16 precision and matching
the training image size for best performance.
"""

import os
import sys
import subprocess
from ultralytics import YOLO

def convert_to_tensorrt(model_path, img_size=640):
    """
    Convert YOLO model to TensorRT engine format.

    Args:
        model_path (str): Path to the trained YOLO model (.pt file)
        img_size (int): Image size for the model (should match training size)

    Returns:
        str: Path to the converted TensorRT engine file
    """

    print(f"Loading model: {model_path}")
    model = YOLO(model_path)

    print("Converting to TensorRT engine...")
    try:
        results = model.export(
            format='engine',  # Export to TensorRT engine
            half=True,       # Use FP16 for faster inference
            imgsz=img_size,  # Match training image size
        )
        print("✅ Conversion successful!")
        print(f"Engine saved to: {results}")
        return results
    except Exception as e:
        print(f"Conversion failed: {e}")
        return None

if __name__ == "__main__":
    # Example usage - change this path to your trained model
    model_path = r'../yolo/models/best.pt'
    convert_to_tensorrt(model_path)
