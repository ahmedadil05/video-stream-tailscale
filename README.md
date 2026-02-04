# Real-Time Video Control with Tailscale

This project provides a complete system for low-latency video streaming and remote camera management from a Raspberry Pi (or any Linux-based system with a camera) to a PC. It is specifically designed to work seamlessly over secure networks like **Tailscale VPN**, allowing you to control your camera from anywhere in the world as if it were on your local network.

## 🚀 Features

* **Dual Mode Operation**: Includes both a `lightweight` version for maximum performance and an `enhanced` version with recording capabilities.
* **Web-Based Control**: A modern, "cyberpunk-themed" dashboard to manage the stream, monitor FPS/latency, and handle recordings.
* **Remote Recording**: Capture video directly on the Pi and download the files to your PC through the web interface.
* **Cross-Camera Support**: Automatically detects and uses Raspberry Pi native cameras (`picamera2`) or generic USB webcams (`OpenCV`).
* **Optimized Networking**: Uses UDP for the video stream to minimize lag and TCP for reliable command/status exchanges.

---

## 🛠 Project Structure

* `pi_server_enhanced.py`: The full-featured server for the Raspberry Pi. Handles streaming, recording, and status reporting.
* `main_lightweight.py`: A stripped-down version for older Raspberry Pi models (like Zero or 2) focusing strictly on stream speed.
* `web_bridge.py`: Runs on your **PC**. It acts as a bridge between the HTML interface and the Raspberry Pi.
* `control_interface.html`: The frontend dashboard with live stats and control buttons.

---

## ⚙️ Setup Instructions

### 1. Prerequisites

* **Tailscale**: Install Tailscale on both your Pi and your PC to ensure they can communicate securely.
* **Python 3.x**: Installed on both devices.
* **Dependencies**: Install the required libraries on the Raspberry Pi:
```bash
pip install opencv-python

```



### 2. Configure the Raspberry Pi

1. Choose your server script (`pi_server_enhanced.py` is recommended).
2. Open the script and check the `RECORDING_DIR` path to ensure it exists or is reachable.
3. Run the server:
```bash
python pi_server_enhanced.py

```



### 3. Configure the PC (Web Bridge)

1. Open `web_bridge.py`.
2. **Crucial**: Change the `PI_IP` variable to your Raspberry Pi's **Tailscale IP address**.
```python
PI_IP = "100.x.y.z"  # Your Pi's Tailscale IP

```


3. Run the bridge:
```bash
python web_bridge.py

```



### 4. Access the Dashboard

1. Open your web browser and navigate to `http://localhost:8080`.
2. Click **"Start"** to begin the live stream.

---

## 📝 Documentation & Commands

### Communication Ports

* **5001 (UDP)**: Video frame transmission.
* **5002 (UDP)**: Command listener (START, STOP, RECORD_START).
* **5003 (TCP)**: Status server and file downloads.

### Available Web Commands

* **START/STOP**: Toggles the video stream.
* **RECORD_START/STOP**: Manages `.avi` video recording on the Pi's local storage.
* **REFRESH LIST**: Fetches the list of saved recordings from the Pi.

---

## 🚀 Future Plans

* **Authentication**: Add a login layer to the `web_bridge` for shared network environments.
* **Dynamic Settings**: Implement sliders in the UI to adjust JPEG quality and FPS in real-time without restarting the script.
* **H.264 Streaming**: Integrate hardware-accelerated H.264 encoding for better quality at lower bandwidths.
* **Multi-Camera Support**: Ability to toggle between multiple cameras connected to the same Raspberry Pi.
* **Auto-Reconnect**: Improve the Web Bridge to automatically reconnect if the Tailscale tunnel momentarily drops.

---

## ⚖️ License

This project is licensed under the **Apache License 2.0**.
