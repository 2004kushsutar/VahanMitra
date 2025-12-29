#!/usr/bin/env python3
"""
================================================
ENHANCED TRAFFIC SIGNAL SYSTEM - BACKEND
AI-Powered Vehicle Detection & Predictive Traffic Control
================================================
"""

import cv2
import time
import os
import sys
import numpy as np
from ultralytics import YOLO
from flask import Flask, request 
from flask_socketio import SocketIO
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================
class Config:
    SNAPSHOT_BEFORE_END = 3000  # Take snapshot 3s before green ends (milliseconds)
    CONFIDENCE = 0.2            # YOLO confidence threshold
    APP_PORT = 5000             # Flask server port
    RESIZE_W = 320              # Frame width for processing
    RESIZE_H = 240              # Frame height for processing
    MODEL_PATH = 'yolov8n.pt'   # YOLO model
    VIDEO_DIRS = ['north', 'south', 'east', 'west']
    VEHICLE_CLASSES = [1, 2, 3, 5, 7]  # car, motorcycle, bus, truck, train
    DISPLAY_GRID = True         # Show OpenCV window
    DEBUG = True                # Enable debug logging
    EMERGENCY_GREEN_TIME = 30000  # 30s fixed time for emergency override

config = Config()

# ============================================
# FLASK & SOCKETIO SETUP
# ============================================
app = Flask(__name__)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=config.DEBUG,
    engineio_logger=config.DEBUG
)

# ============================================
# GLOBAL STATE
# ============================================
class TrafficSystem:
    def __init__(self):
        self.model = None
        self.videos = {}
        self.last_counts = {'north': 0, 'south': 0, 'east': 0, 'west': 0}
        self.total_detections = 0
        self.start_time = time.time()
        self.frame_count = 0
        self.snapshot_requests = []  # Queue for snapshot requests from frontend
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")

system = TrafficSystem()

# ============================================
# INITIALIZATION
# ============================================
def initialize_system():
    """Initialize YOLO model and video captures"""
    try:
        system.log("Initializing Traffic Control System...")
        
        # Check if model exists
        if not os.path.exists(config.MODEL_PATH):
            system.log(f"Downloading YOLO model: {config.MODEL_PATH}", "INFO")
        
        # Load YOLO model
        system.log("Loading AI Model...", "INFO")
        system.model = YOLO(config.MODEL_PATH)
        system.log("✅ YOLO Model Loaded Successfully", "SUCCESS")
        
        # Initialize video captures
        for direction in config.VIDEO_DIRS:
            video_path = f'{direction}.mp4'
            
            if not os.path.exists(video_path):
                system.log(f"❌ ERROR: {video_path} not found!", "ERROR")
                system.log(f"Please ensure {video_path} exists in the current directory", "ERROR")
                return False
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                system.log(f"❌ ERROR: Cannot open {video_path}", "ERROR")
                return False
            
            system.videos[direction] = cap
            system.log(f"✅ Loaded {video_path}", "SUCCESS")
        
        system.log("System Initialization Complete", "SUCCESS")
        return True
        
    except Exception as e:
        system.log(f"Initialization Error: {str(e)}", "ERROR")
        return False

# ============================================
# VIDEO PROCESSING
# ============================================
def get_frame(cap):
    """Read and resize frame, handle video looping"""
    success, frame = cap.read()
    
    if not success:
        # Loop video
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        success, frame = cap.read()
        
    if not success:
        system.log("Failed to read frame", "WARNING")
        return None
    
    return cv2.resize(frame, (config.RESIZE_W, config.RESIZE_H))

def detect_vehicles(frame):
    """Run YOLO detection on frame"""
    try:
        results = system.model(
            frame,
            verbose=False,
            conf=config.CONFIDENCE,
            classes=config.VEHICLE_CLASSES
        )
        
        detections = results[0].boxes
        count = len(detections)
        
        return count, detections
        
    except Exception as e:
        system.log(f"Detection error: {str(e)}", "ERROR")
        return 0, None

def draw_detections(frame, detections, count, direction):
    """Draw bounding boxes and labels on frame"""
    if detections is not None and len(detections) > 0:
        for box in detections:
            # Get coordinates
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            cls = int(box.cls[0])
            
            # Draw box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Draw label
            label = f"{conf:.2f}"
            cv2.putText(frame, label, (x1, y1 - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
    
    # Draw direction label and count
    cv2.rectangle(frame, (0, 0), (config.RESIZE_W, 45), (0, 0, 0), -1)
    cv2.putText(frame, f"{direction.upper()}", (10, 25),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.putText(frame, f"Vehicles: {count}", (10, 42),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    return frame

def take_snapshot_for_direction(direction):
    """Take a snapshot and count vehicles for a specific direction"""
    try:
        system.log(f"📸 Taking snapshot for {direction.upper()}...", "INFO")
        
        # Get current frame for the direction
        cap = system.videos.get(direction)
        if not cap:
            system.log(f"Video capture not found for {direction}", "ERROR")
            return 0
        
        frame = get_frame(cap)
        if frame is None:
            system.log(f"Failed to get frame for {direction}", "ERROR")
            return 0
        
        # Run AI detection
        count, detections = detect_vehicles(frame)
        
        # Update the count for this direction
        system.last_counts[direction] = count
        
        system.log(f"  {direction.upper()}: {count} vehicles detected", "SUCCESS")
        
        return count
        
    except Exception as e:
        system.log(f"Snapshot error for {direction}: {str(e)}", "ERROR")
        return 0