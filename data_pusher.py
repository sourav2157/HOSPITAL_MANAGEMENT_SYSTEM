import time
import random
import datetime
import argparse
import requests
import socketio

def get_args():
    parser = argparse.ArgumentParser(description="Data Pusher Simulator for Master Display Server")
    parser.add_argument("--server", type=str, default="http://127.0.0.1:5000", help="Flask Server URL")
    parser.add_argument("--device-id", type=str, default="ESP_001", help="Device ID")
    parser.add_argument("--device-type", type=str, choices=["hardware", "browser"], default="hardware", help="Device Type")
    parser.add_argument("--hardware-id", type=str, default="A4:CF:12:89:5B:01", help="Hardware ID (MAC / LocalStorage ID)")
    parser.add_argument("--mode", type=str, choices=["ws", "http"], default="ws", help="Transport mode: ws or http")
    parser.add_argument("--interval", type=float, default=2.0, help="Interval between pushes in seconds")
    return parser.parse_args()

def generate_telemetry_payload(device_id):
    """Generates realistic sensor data payload."""
    if "ESP" in device_id.upper():
        return {
            "temperature_c": round(22.0 + random.uniform(-2.5, 4.0), 2),
            "humidity_pct": round(50.0 + random.uniform(-10.0, 15.0), 1),
            "vcc_voltage": round(3.28 + random.uniform(-0.05, 0.05), 3),
            "wifi_rssi_dbm": random.randint(-75, -45)
        }
    else:
        return {
            "battery_level": random.randint(45, 99),
            "screen_orientation": random.choice(["portrait", "landscape"]),
            "user_action": random.choice(["heartbeat", "tap", "scroll", "idle"]),
            "memory_usage_mb": round(120 + random.uniform(0, 50), 1)
        }

def run_websocket_pusher(args):
    sio = socketio.Client()
    
    @sio.event
    def connect():
        print(f"[OK] Connected to WebSocket server at {args.server}")

    @sio.event
    def disconnect():
        print("[INFO] Disconnected from WebSocket server")

    print(f"[CONNECTING] WebSocket server: {args.server} ...")
    try:
        sio.connect(args.server)
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        print("[FALLBACK] Switching to HTTP POST mode...")
        run_http_pusher(args)
        return

    print(f"[START] Pushing telemetry for [{args.device_id}] every {args.interval}s (Ctrl+C to stop)...")
    try:
        while True:
            payload = generate_telemetry_payload(args.device_id)
            packet = {
                "device_id": args.device_id,
                "device_type": args.device_type,
                "hardware_id": args.hardware_id,
                "payload": payload,
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            sio.emit("push_data", packet)
            print(f"[WS PUSH] {args.device_id} ({args.hardware_id}) -> {payload}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[STOP] Stopping data pusher.")
    finally:
        sio.disconnect()

def run_http_pusher(args):
    endpoint = f"{args.server.rstrip('/')}/api/push_data"
    print(f"[START] Pushing HTTP POST telemetry to {endpoint} every {args.interval}s (Ctrl+C to stop)...")
    
    try:
        while True:
            payload = generate_telemetry_payload(args.device_id)
            packet = {
                "device_id": args.device_id,
                "device_type": args.device_type,
                "hardware_id": args.hardware_id,
                "payload": payload,
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            try:
                resp = requests.post(endpoint, json=packet, timeout=3.0)
                if resp.status_code == 200:
                    print(f"[HTTP 200 OK] {args.device_id} ({args.hardware_id}) -> {payload}")
                else:
                    print(f"[HTTP {resp.status_code}] {resp.text}")
            except Exception as req_err:
                print(f"[HTTP ERROR] {req_err}")

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[STOP] Stopping data pusher.")

if __name__ == "__main__":
    args = get_args()
    if args.mode == "ws":
        run_websocket_pusher(args)
    else:
        run_http_pusher(args)
