#!/usr/bin/env python3
"""
Enhanced Raspberry Pi Video Streamer with Recording
Supports web control, video recording, and data downloads
"""

import cv2
import socket
import time
import struct
import threading
import json
import os
from datetime import datetime
from typing import Optional
from pathlib import Path

# Try to import picamera2 first (Raspberry Pi), fallback to cv2
USE_PICAMERA = False
try:
    from picamera2 import Picamera2
    USE_PICAMERA = True
    print("✓ Using Raspberry Pi Camera (picamera2)")
except ImportError:
    print("✓ Using OpenCV camera (USB/generic)")

# ==========================================
#     CONFIGURATION
# ==========================================
VIDEO_PORT = 5001      # UDP video stream
COMMAND_PORT = 5002    # UDP commands from web
STATUS_PORT = 5003     # TCP status/data queries
RECORDING_DIR = "/home/pi/recordings"  # Change as needed
MAX_RECORDING_SIZE_MB = 500  # Auto-stop if exceeded

# Create recordings directory
Path(RECORDING_DIR).mkdir(parents=True, exist_ok=True)

# ==========================================
#     SHARED STATE
# ==========================================
class StreamState:
    """Thread-safe state management"""
    def __init__(self):
        self.lock = threading.Lock()
        self.streaming = False
        self.recording = False
        self.pc_ip = None
        self.fps = 15
        self.quality = 40
        self.resolution = (640, 480)
        self.frames_sent = 0
        self.frames_recorded = 0
        self.recording_file = None
        self.recording_start_time = None
        self.video_writer = None
        self.session_start = time.time()
        
    def get_stats(self):
        """Get current statistics"""
        with self.lock:
            uptime = time.time() - self.session_start
            recording_duration = 0
            if self.recording and self.recording_start_time:
                recording_duration = time.time() - self.recording_start_time
            
            return {
                "streaming": self.streaming,
                "recording": self.recording,
                "fps": self.fps,
                "quality": self.quality,
                "resolution": list(self.resolution),
                "frames_sent": self.frames_sent,
                "frames_recorded": self.frames_recorded,
                "uptime_seconds": int(uptime),
                "recording_duration": int(recording_duration),
                "recording_file": self.recording_file,
                "camera_type": "picamera2" if USE_PICAMERA else "opencv"
            }
    
    def start_recording(self, filename=None):
        """Start video recording"""
        with self.lock:
            if self.recording:
                return False, "Already recording"
            
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"recording_{timestamp}.avi"
            
            filepath = os.path.join(RECORDING_DIR, filename)
            
            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            self.video_writer = cv2.VideoWriter(
                filepath, fourcc, self.fps, self.resolution
            )
            
            if not self.video_writer.isOpened():
                return False, "Failed to create video writer"
            
            self.recording = True
            self.recording_file = filename
            self.recording_start_time = time.time()
            self.frames_recorded = 0
            
            return True, f"Recording started: {filename}"
    
    def stop_recording(self):
        """Stop video recording"""
        with self.lock:
            if not self.recording:
                return False, "Not recording"
            
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
            
            filename = self.recording_file
            duration = time.time() - self.recording_start_time if self.recording_start_time else 0
            
            self.recording = False
            self.recording_file = None
            self.recording_start_time = None
            
            return True, f"Recording stopped: {filename} ({int(duration)}s, {self.frames_recorded} frames)"
    
    def write_frame(self, frame):
        """Write frame to recording"""
        with self.lock:
            if self.recording and self.video_writer:
                self.video_writer.write(frame)
                self.frames_recorded += 1
                return True
        return False

state = StreamState()

# ==========================================
#     CAMERA
# ==========================================
class SimpleCamera:
    """Lightweight camera handler"""
    
    def __init__(self):
        self.camera = None
        self.use_pi = USE_PICAMERA
        
    def start(self):
        """Initialize camera"""
        try:
            if self.use_pi:
                self.camera = Picamera2()
                config = self.camera.create_still_configuration(
                    main={"size": state.resolution, "format": "RGB888"}
                )
                self.camera.configure(config)
                self.camera.start()
                print(f"✓ Pi Camera started: {state.resolution}")
            else:
                self.camera = cv2.VideoCapture(0)
                if not self.camera.isOpened():
                    print("✗ Error: Could not open camera")
                    return False
                
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, state.resolution[0])
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, state.resolution[1])
                self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                print(f"✓ USB Camera started: {state.resolution}")
            
            time.sleep(0.5)
            return True
            
        except Exception as e:
            print(f"✗ Camera error: {e}")
            return False
    
    def read(self):
        """Capture frame"""
        try:
            if self.use_pi:
                frame = self.camera.capture_array()
                # Convert RGB to BGR for OpenCV
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                return frame
            else:
                ret, frame = self.camera.read()
                return frame if ret else None
        except:
            return None
    
    def release(self):
        """Stop camera"""
        try:
            if self.use_pi:
                self.camera.stop()
            else:
                self.camera.release()
            print("✓ Camera released")
        except:
            pass

# ==========================================
#     VIDEO STREAMER
# ==========================================
def stream_video(running_flag):
    """Main streaming loop"""
    camera = SimpleCamera()
    if not camera.start():
        return
    
    # UDP socket for streaming
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 512 * 1024)
    
    header_struct = struct.Struct("!I Q")
    seq = 0
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), state.quality]
    
    print(f"✓ Video streamer ready")
    
    last_stats = time.time()
    
    try:
        while running_flag[0]:
            if not state.streaming:
                time.sleep(0.1)
                continue
            
            loop_start = time.time()
            
            # Capture frame
            frame = camera.read()
            if frame is None:
                time.sleep(0.1)
                continue
            
            # Resize if needed
            if frame.shape[:2] != (state.resolution[1], state.resolution[0]):
                frame = cv2.resize(frame, state.resolution, interpolation=cv2.INTER_NEAREST)
            
            # Save to recording if active
            state.write_frame(frame)
            
            # Encode to JPEG
            _, jpeg = cv2.imencode(".jpg", frame, encode_params)
            jpeg_bytes = jpeg.tobytes()
            
            # Create packet
            timestamp_ns = time.time_ns()
            header = header_struct.pack(seq, timestamp_ns)
            packet = header + jpeg_bytes
            
            # Send to PC if we have an IP
            if state.pc_ip:
                try:
                    sock.sendto(packet, (state.pc_ip, VIDEO_PORT))
                    with state.lock:
                        state.frames_sent += 1
                    seq += 1
                except:
                    pass
            
            # Check recording file size
            if state.recording and state.recording_file:
                filepath = os.path.join(RECORDING_DIR, state.recording_file)
                if os.path.exists(filepath):
                    size_mb = os.path.getsize(filepath) / (1024 * 1024)
                    if size_mb > MAX_RECORDING_SIZE_MB:
                        print(f"⚠ Recording size limit reached ({size_mb:.1f}MB), stopping...")
                        state.stop_recording()
            
            # Print stats
            now = time.time()
            if now - last_stats >= 5.0:
                stats = state.get_stats()
                print(f"→ Streaming: {state.streaming}, Recording: {state.recording}, "
                      f"Sent: {stats['frames_sent']}, Recorded: {stats['frames_recorded']}")
                last_stats = now
            
            # FPS throttle
            elapsed = time.time() - loop_start
            sleep_time = (1.0 / state.fps) - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    except KeyboardInterrupt:
        print("\n✓ Stopped by user")
    finally:
        if state.recording:
            state.stop_recording()
        camera.release()
        sock.close()

# ==========================================
#     COMMAND LISTENER
# ==========================================
def listen_for_commands(running_flag):
    """Listen for UDP commands"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(1.0)
    
    try:
        sock.bind(("0.0.0.0", COMMAND_PORT))
        print(f"✓ Command listener on port {COMMAND_PORT}")
    except OSError as e:
        print(f"✗ Could not bind command port: {e}")
        return
    
    while running_flag[0]:
        try:
            data, addr = sock.recvfrom(1024)
            command = data.decode('utf-8').strip().upper()
            
            # Process commands
            response = "OK"
            
            if command == "START":
                with state.lock:
                    state.streaming = True
                    state.pc_ip = addr[0]  # Remember PC IP
                response = "STREAMING_STARTED"
                print(f"✓ START from {addr[0]}")
                
            elif command == "STOP":
                with state.lock:
                    state.streaming = False
                response = "STREAMING_STOPPED"
                print(f"✓ STOP from {addr[0]}")
                
            elif command == "RECORD_START":
                success, msg = state.start_recording()
                response = msg
                print(f"✓ RECORD_START: {msg}")
                
            elif command == "RECORD_STOP":
                success, msg = state.stop_recording()
                response = msg
                print(f"✓ RECORD_STOP: {msg}")
                
            elif command == "PING":
                response = "PONG"
                
            elif command == "SHUTDOWN":
                print(f"✓ SHUTDOWN from {addr[0]}")
                running_flag[0] = False
                response = "SHUTTING_DOWN"
            
            # Send response
            sock.sendto(response.encode(), addr)
        
        except socket.timeout:
            continue
        except Exception as e:
            if running_flag[0]:
                print(f"✗ Command error: {e}")
    
    sock.close()

# ==========================================
#     STATUS/DATA SERVER (TCP)
# ==========================================
def status_server(running_flag):
    """TCP server for status queries and file downloads"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        
        try:
            sock.bind(("0.0.0.0", STATUS_PORT))
            sock.listen(5)
            print(f"✓ Status server on port {STATUS_PORT}")
        except OSError as e:
            print(f"✗ Could not bind status port: {e}")
            return
        
        while running_flag[0]:
            try:
                conn, addr = sock.accept()
                threading.Thread(
                    target=handle_status_client,
                    args=(conn, addr),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if running_flag[0]:
                    print(f"✗ Status server error: {e}")

def handle_status_client(conn, addr):
    """Handle status/data requests"""
    try:
        conn.settimeout(5.0)
        data = conn.recv(1024).decode('utf-8').strip()
        
        if data == "STATUS":
            # Send JSON status
            stats = state.get_stats()
            response = json.dumps(stats, indent=2)
            conn.sendall(response.encode())
            
        elif data == "LIST_RECORDINGS":
            # List available recordings
            files = []
            for f in os.listdir(RECORDING_DIR):
                if f.endswith('.avi'):
                    filepath = os.path.join(RECORDING_DIR, f)
                    size = os.path.getsize(filepath)
                    mtime = os.path.getmtime(filepath)
                    files.append({
                        "filename": f,
                        "size_mb": round(size / (1024 * 1024), 2),
                        "modified": datetime.fromtimestamp(mtime).isoformat()
                    })
            response = json.dumps(files, indent=2)
            conn.sendall(response.encode())
            
        elif data.startswith("DOWNLOAD:"):
            # Download a recording file
            filename = data.split(":", 1)[1].strip()
            filepath = os.path.join(RECORDING_DIR, filename)
            
            if not os.path.exists(filepath):
                conn.sendall(b"ERROR: File not found")
                return
            
            # Send file size first
            filesize = os.path.getsize(filepath)
            conn.sendall(f"SIZE:{filesize}\n".encode())
            
            # Send file data
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    conn.sendall(chunk)
            
            print(f"✓ Sent file {filename} to {addr[0]}")
    
    except Exception as e:
        print(f"✗ Status client error: {e}")
    finally:
        conn.close()

# ==========================================
#     MAIN
# ==========================================
if __name__ == "__main__":
    print("=" * 60)
    print("Enhanced Raspberry Pi Video Streamer with Recording")
    print("=" * 60)
    
    running = [True]
    
    # Start all servers
    threading.Thread(target=listen_for_commands, args=(running,), daemon=True).start()
    threading.Thread(target=status_server, args=(running,), daemon=True).start()
    
    # Run streamer in main thread
    try:
        stream_video(running)
    except KeyboardInterrupt:
        print("\n✓ Interrupted by user")
        running[0] = False
    
    print("✓ Shutdown complete")
