#!/usr/bin/env python3
"""
Lightweight Video Streaming Server for Raspberry Pi
Optimized for low-performance devices with minimal overhead
"""

import cv2
import socket
import time
import struct
import threading
from typing import Optional

# Try to import picamera2 first (Raspberry Pi), fallback to cv2
USE_PICAMERA = False
try:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput
    import io
    USE_PICAMERA = True
    print("✓ Using Raspberry Pi Camera (picamera2)")
except ImportError:
    print("✓ Using OpenCV camera (USB/generic)")

# ==========================================
#     CONFIGURATION - Keep it simple!
# ==========================================
PC_IP = "100.100.100.100"  # CHANGE THIS - Your PC's IP
VIDEO_PORT = 5001
FPS = 15  # Lower FPS for low-performance devices
JPEG_QUALITY = 40  # Lower quality = less CPU usage
RESOLUTION = (640, 480)

# ==========================================
#     SIMPLE CAMERA CLASS
# ==========================================
class SimpleCamera:
    """Lightweight camera handler for both RPi and USB cameras"""
    
    def __init__(self):
        self.camera = None
        self.use_pi = USE_PICAMERA
        
    def start(self):
        """Initialize camera"""
        try:
            if self.use_pi:
                # Raspberry Pi Camera
                self.camera = Picamera2()
                config = self.camera.create_still_configuration(
                    main={"size": RESOLUTION, "format": "RGB888"}
                )
                self.camera.configure(config)
                self.camera.start()
                print(f"✓ Pi Camera started: {RESOLUTION}")
            else:
                # USB/Generic Camera
                self.camera = cv2.VideoCapture(0)
                if not self.camera.isOpened():
                    print("✗ Error: Could not open camera")
                    return False
                
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
                self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize lag
                print(f"✓ USB Camera started: {RESOLUTION}")
            
            time.sleep(0.5)  # Let camera warm up
            return True
            
        except Exception as e:
            print(f"✗ Camera error: {e}")
            return False
    
    def read(self):
        """Capture frame - returns None on error"""
        try:
            if self.use_pi:
                # Pi Camera - capture to array
                frame = self.camera.capture_array()
                return frame
            else:
                # USB Camera
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
#     VIDEO STREAMER (Main Thread)
# ==========================================
def stream_video(running_flag):
    """
    Simple streaming loop - runs in main thread
    No fancy features, just reliable streaming
    """
    camera = SimpleCamera()
    if not camera.start():
        return
    
    # UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 512 * 1024)
    
    # Pre-compile packet format
    header_struct = struct.Struct("!I Q")
    
    seq = 0
    frame_time = 1.0 / FPS
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    
    print(f"✓ Streaming to {PC_IP}:{VIDEO_PORT} at {FPS} FPS")
    print("✓ Ready! PC should start receiving frames now.")
    
    stats_counter = 0
    stats_time = time.time()
    
    try:
        while running_flag[0]:
            loop_start = time.time()
            
            # Capture frame
            frame = camera.read()
            if frame is None:
                time.sleep(0.1)
                continue
            
            # Resize if needed (faster than letting camera do it)
            if frame.shape[:2] != (RESOLUTION[1], RESOLUTION[0]):
                frame = cv2.resize(frame, RESOLUTION, interpolation=cv2.INTER_NEAREST)
            
            # Encode to JPEG (fastest encoding)
            _, jpeg = cv2.imencode(".jpg", frame, encode_params)
            jpeg_bytes = jpeg.tobytes()
            
            # Create packet
            timestamp_ns = time.time_ns()
            header = header_struct.pack(seq, timestamp_ns)
            packet = header + jpeg_bytes
            
            # Send (ignore errors - UDP is fire-and-forget)
            try:
                sock.sendto(packet, (PC_IP, VIDEO_PORT))
                seq += 1
                stats_counter += 1
            except:
                pass
            
            # Print stats every 5 seconds
            now = time.time()
            if now - stats_time >= 5.0:
                actual_fps = stats_counter / (now - stats_time)
                print(f"→ {stats_counter} frames sent, {actual_fps:.1f} FPS")
                stats_counter = 0
                stats_time = now
            
            # Simple FPS throttle
            elapsed = time.time() - loop_start
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    except KeyboardInterrupt:
        print("\n✓ Stopped by user")
    finally:
        camera.release()
        sock.close()

# ==========================================
#     COMMAND LISTENER (Background Thread)
# ==========================================
def listen_for_commands(running_flag):
    """
    Listen for UDP commands from PC
    PC sends commands, Pi just receives and streams
    Simpler than TCP - no connection management
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(1.0)  # Check running_flag periodically
    
    try:
        sock.bind(("0.0.0.0", 5002))  # Command port
        print(f"✓ Command listener on port 5002")
    except OSError as e:
        print(f"✗ Could not bind command port: {e}")
        return
    
    while running_flag[0]:
        try:
            data, addr = sock.recvfrom(1024)
            command = data.decode('utf-8').strip().upper()
            
            if command == "STOP":
                print(f"✓ STOP command from {addr}")
                running_flag[0] = False
                break
            elif command == "PING":
                # Respond to ping
                sock.sendto(b"PONG", addr)
        
        except socket.timeout:
            continue
        except Exception as e:
            if running_flag[0]:  # Only print if still running
                print(f"✗ Command error: {e}")
    
    sock.close()

# ==========================================
#     MAIN
# ==========================================
if __name__ == "__main__":
    print("=" * 50)
    print("Lightweight Video Streamer for Raspberry Pi")
    print("=" * 50)
    
    # Shared flag for clean shutdown (list so it's mutable)
    running = [True]
    
    # Start command listener in background
    cmd_thread = threading.Thread(target=listen_for_commands, args=(running,), daemon=True)
    cmd_thread.start()
    
    # Run streamer in main thread (simpler, less overhead)
    stream_video(running)
    
    print("✓ Shutdown complete")
