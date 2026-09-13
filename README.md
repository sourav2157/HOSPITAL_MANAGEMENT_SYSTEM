# 🏥 Hospital Patient Management & Nurse Call System

A real-time, Wi-Fi local network **Patient Management & Bedside Nurse Call System** built with **Flask**, **SQLite**, and **Flask-SocketIO**.

Designed for hospitals, clinics, and care facilities to connect bedside hardware units (ESP8266) to a central dashboard accessible across laptops, tablets, and phones used by **Doctors, Nurses, Lab Technicians, and Receptionists**.

---

## 🏛️ Identity Architecture

```
  ┌─────────────────────────────────────────────────────────────┐
  │                 ESP8266 Bedside Unit                        │
  │  (Hardware MAC | Room 101 | Bed 1 | Call Nurse / Doc Btns)  │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ MQTT / HTTP POST
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │               Flask Server & SQLite Database                │
  │     - Real-Time Socket.IO Engine                            │
  │     - Active Call State Tracker                             │
  │     - Immutable Timestamped Action Record Book              │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ WebSockets (Real-Time)
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │              Hospital Staff Web Dashboards                  │
  │  (Accessible on PCs, Tablets, Mobiles across Hospital LAN)  │
  │                                                             │
  │  - 🚨 Nurse Station Call Monitor & Alarm Banner             │
  │  - 📌 Doctor & Nurse Patient Pinning, Sorting & Filtering   │
  │  - 📖 Role-Based Action Record Book & Timestamped Comments  │
  │    [Doctor] [Nurse] [Lab Technician] [Receptionist]         │
  └──────────────────────────────┴──────────────────────────────┘
```

---

## ✨ Features

- **🚨 Real-Time Alarm Monitor**: Flashing banner + audio chime sound across all dashboards when a patient presses *Call Nurse* or *Call Doctor*.
- **📌 Patient Pinning**: Lock critical/high-priority patients to the top of the grid.
- **🔍 Filter & Sort**: Filter by *Active Calls, Emergency Doctor Calls, Nurse Calls, Pinned Patients, or Room #*. Sort by *Urgency, Room #, or Patient Name*.
- **📖 Role-Based Action Record Book**: Timestamped timeline log for each patient. Staff members post comments tagged with their role:
  - 🩺 `[Doctor]`
  - 👩‍⚕️ `[Nurse]`
  - 🧪 `[Lab Technician]`
  - 📋 `[Receptionist]`
- **🔌 ESP8266 Bedside Hardware**: Connects via Wi-Fi sending HTTP POST or MQTT messages with room, bed, call type, and MAC address.
- **📱 Soft Bedside Console (`/bedside`)**: Soft-button browser UI for patient phones/tablets.

---

## 🚀 How to Run

### 1. Start the Flask Server
```bash
python app.py
```
Outputs access URLs, for example:
```
=================================================================
🏥 HOSPITAL PATIENT MANAGEMENT & NURSE CALL SYSTEM RUNNING
=================================================================
Accessible across your WiFi network at:
  --> Staff Dashboard  : http://192.168.1.50:5000
  --> Soft Bedside Unit: http://192.168.1.50:5000/bedside
=================================================================
```

### 2. Access from LAN Devices
- Open `http://<SERVER_IP>:5000` on any computer or tablet on the hospital Wi-Fi.

### 3. Simulate Bedside Call (CLI Tool)
Trigger a simulated patient call from another terminal:
```bash
# Simulate Nurse Call from Room 101, Bed A1
python esp8266_simulator.py --room 101 --bed A1 --call NURSE_CALL

# Simulate Emergency Doctor Call from Room 102, Bed B1
python esp8266_simulator.py --room 102 --bed B1 --call DOCTOR_CALL
```

---

## 🔌 Hardware Wiring & ESP8266 Sketch

The ESP8266 C++ source code is located in [`firmware/esp8266_bedside.ino`](file:///c:/Users/eTrans/Desktop/python_code/firmware/esp8266_bedside.ino).

**Pinout Connections:**
- **Pin D1 (GPIO 5)**: Call Nurse Pushbutton -> GND
- **Pin D2 (GPIO 4)**: Call Doctor Pushbutton -> GND
- **Pin D4 (GPIO 2)**: Status LED (Built-in)
