import time
import argparse
import requests

def get_args():
    parser = argparse.ArgumentParser(description="ESP8266 Bedside Call Hardware Simulator")
    parser.add_argument("--server", type=str, default="http://127.0.0.1:5000", help="Flask Hospital Server URL")
    parser.add_argument("--room", type=str, default="101", help="Room Number")
    parser.add_argument("--bed", type=str, default="A1", help="Bed Number")
    parser.add_argument("--call", type=str, choices=["NURSE_CALL", "DOCTOR_CALL"], default="NURSE_CALL", help="Call Type: NURSE_CALL or DOCTOR_CALL")
    parser.add_argument("--mac", type=str, default="A4:CF:12:89:5B:01", help="ESP8266 Hardware MAC address")
    return parser.parse_args()

def trigger_call(args):
    endpoint = f"{args.server.rstrip('/')}/api/bedside/call"
    device_id = f"ESP_ROOM{args.room}_{args.bed}"
    
    packet = {
        "room_no": args.room,
        "bed_no": args.bed,
        "call_type": args.call,
        "device_id": device_id,
        "esp_mac": args.mac
    }

    print(f"[ESP8266 SIMULATOR] Triggering {args.call} from Room {args.room}, Bed {args.bed}...")
    try:
        resp = requests.post(endpoint, json=packet, timeout=3.0)
        if resp.status_code == 200:
            print(f"[OK 200] Alert broadcasted! Response: {resp.json()}")
        else:
            print(f"[ERROR {resp.status_code}] {resp.text}")
    except Exception as e:
        print(f"[CONNECTION ERROR] Failed to reach server at {endpoint}: {e}")

if __name__ == "__main__":
    args = get_args()
    trigger_call(args)
