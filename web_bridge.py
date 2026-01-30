#!/usr/bin/env python3
"""
Web Bridge Server
Connects HTML control interface to Raspberry Pi via HTTP
Runs on your PC
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import socket
import json
import urllib.parse
import os

# Configuration
PI_IP = "100.122.162.65"  # CHANGE THIS - Your Pi's IP
COMMAND_PORT = 5002
STATUS_PORT = 5003
VIDEO_PORT = 5001
WEB_PORT = 8080  # Port for this web server

class BridgeHandler(BaseHTTPRequestHandler):
    """HTTP handler that bridges web interface to Pi"""
    
    def _send_cors_headers(self):
        """Send CORS headers for web access"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/':
            # Serve the control interface
            self.serve_control_interface()
        elif self.path == '/status':
            # Get status from Pi
            self.get_pi_status()
        elif self.path == '/recordings':
            # List recordings
            self.list_recordings()
        elif self.path.startswith('/download/'):
            # Download recording
            filename = self.path.split('/')[-1]
            self.download_recording(filename)
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        if self.path == '/command':
            # Send command to Pi
            content_length = int(self.headers['Content-Length'])
            command = self.rfile.read(content_length).decode('utf-8')
            self.send_command_to_pi(command)
        else:
            self.send_error(404)
    
    def serve_control_interface(self):
        """Serve the HTML control interface"""
        try:
            # Look for control_interface.html in same directory
            html_file = os.path.join(os.path.dirname(__file__), 'control_interface.html')
            with open(html_file, 'r') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(content.encode())
        except FileNotFoundError:
            self.send_error(404, "control_interface.html not found")
    
    def send_command_to_pi(self, command):
        """Send UDP command to Pi"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2.0)
            
            # Send command
            sock.sendto(command.encode(), (PI_IP, COMMAND_PORT))
            
            # Wait for response
            try:
                data, _ = sock.recvfrom(1024)
                response = data.decode('utf-8')
            except socket.timeout:
                response = "TIMEOUT"
            
            sock.close()
            
            # Send response to web client
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"response": response}).encode())
            
            print(f"✓ Command '{command}' -> {response}")
            
        except Exception as e:
            print(f"✗ Error sending command: {e}")
            self.send_error(500, str(e))
    
    def get_pi_status(self):
        """Get status from Pi via TCP"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((PI_IP, STATUS_PORT))
            sock.sendall(b"STATUS")
            
            # Receive response
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            
            sock.close()
            
            # Parse JSON response
            status = json.loads(data.decode('utf-8'))
            
            # Send to web client
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
            
        except Exception as e:
            print(f"✗ Error getting status: {e}")
            # Send default/error status
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": str(e),
                "streaming": False,
                "recording": False
            }).encode())
    
    def list_recordings(self):
        """List recordings from Pi"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((PI_IP, STATUS_PORT))
            sock.sendall(b"LIST_RECORDINGS")
            
            # Receive response
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            
            sock.close()
            
            # Parse JSON response
            recordings = json.loads(data.decode('utf-8'))
            
            # Send to web client
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(recordings).encode())
            
        except Exception as e:
            print(f"✗ Error listing recordings: {e}")
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps([]).encode())
    
    def download_recording(self, filename):
        """Download recording file from Pi"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((PI_IP, STATUS_PORT))
            sock.sendall(f"DOWNLOAD:{filename}".encode())
            
            # Receive file size
            size_line = b""
            while b"\n" not in size_line:
                size_line += sock.recv(1)
            
            size_str = size_line.decode('utf-8').strip()
            if size_str.startswith("SIZE:"):
                file_size = int(size_str.split(":")[1])
                
                # Send response headers
                self.send_response(200)
                self.send_header('Content-type', 'video/avi')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Content-Length', str(file_size))
                self._send_cors_headers()
                self.end_headers()
                
                # Stream file data
                bytes_received = 0
                while bytes_received < file_size:
                    chunk = sock.recv(min(8192, file_size - bytes_received))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    bytes_received += len(chunk)
                
                print(f"✓ Downloaded {filename} ({bytes_received} bytes)")
            else:
                self.send_error(404, "File not found")
            
            sock.close()
            
        except Exception as e:
            print(f"✗ Error downloading file: {e}")
            self.send_error(500, str(e))
    
    def log_message(self, format, *args):
        """Custom log format"""
        print(f"[{self.log_date_time_string()}] {format % args}")

def main():
    print("=" * 60)
    print("Web Bridge Server for Pi Camera Control")
    print("=" * 60)
    print(f"\n✓ Server starting on http://localhost:{WEB_PORT}")
    print(f"✓ Connecting to Pi at {PI_IP}")
    print(f"\n→ Open your browser to: http://localhost:{WEB_PORT}")
    print("→ Press Ctrl+C to stop\n")
    
    try:
        server = HTTPServer(('0.0.0.0', WEB_PORT), BridgeHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n✓ Server stopped")

if __name__ == "__main__":
    main()
