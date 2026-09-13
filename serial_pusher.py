import time
import json
import argparse
import requests
import datetime
import serial
import serial.tools.list_ports

def get_args():
    parser = argparse.ArgumentParser(description="Serial Port Data Pusher for Master Display Server")
    parser.add_argument("--port", type=str, default=None, help="Serial COM port (e.g., COM3, /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--server", type=str, default="http://127.0.0.1:5000", help="Flask Server URL")
    parser.add_argument("--device-id", type=str, default="SERIAL_DEVICE_01", help="Device ID for serial stream")
    return parser.parse_args()

def list_serial_ports():
    ports = serial.tools.list_ports.comports()
    print("Available Serial Ports:")
    if not ports:
        print("  (No serial ports detected on this machine)")
    for p in ports:
        print(f"  - {p.device}: {p.description}")

def run_serial_pusher(args):
    if not args.port:
        list_serial_ports()
        print("\nPlease specify a port using --port <PORT_NAME>")
        return

    endpoint = f"{args.server.rstrip('/')}/api/push_data"
    print(f"[SERIAL] Opening Serial Port {args.port} at {args.baud} baud...")

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
        print(f"[SERIAL OK] Connected to {args.port}. Forwarding data to {endpoint}...")
        
        while True:
            if ser.in_waiting > 0:
                raw_line = ser.readline().decode('utf-8', errors='replace').strip()
                if not raw_line:
                    continue

                try:
                    payload = json.loads(raw_line)
                except Exception:
                    payload = {"raw_text": raw_line}

                packet = {
                    "device_id": args.device_id,
                    "device_type": "hardware",
                    "hardware_id": f"SERIAL_{args.port}",
                    "payload": payload,
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

                try:
                    resp = requests.post(endpoint, json=packet, timeout=2.0)
                    print(f"[SERIAL -> FLASK] {raw_line} (HTTP {resp.status_code})")
                except Exception as req_err:
                    print(f"[ERROR] Failed to forward serial data to server: {req_err}")

            time.sleep(0.05)

    except serial.SerialException as e:
        print(f"[SERIAL ERROR] {e}")
    except KeyboardInterrupt:
        print("\n[STOP] Stopping serial pusher.")

if __name__ == "__main__":
    args = get_args()
    run_serial_pusher(args)
