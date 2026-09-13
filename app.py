import os
import io
import csv
import json
import time
import socket
import sqlite3
import datetime
import threading
from flask import Flask, render_template, request, jsonify, Response, session, redirect, url_for
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'antigravity_hospital_secret_2026'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Database Configurations
DB_PATH = os.path.join(os.path.dirname(__file__), 'hospital.db')
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/hospital_db")

USE_MONGO = False
mongo_db = None

try:
    import pymongo
    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    client.admin.command('ping')
    mongo_db = client.get_database()
    USE_MONGO = True
    print("[DATABASE] Connected to MongoDB database: hospital_db")
except Exception as e:
    USE_MONGO = False
    print(f"[DATABASE INFO] Local MongoDB server not active ({e}). Using SQLite database fallback (hospital.db).")

def get_sqlite_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize DB schema including Users, Patients, Prescriptions, Action Logs, and User Patient Selections."""
    if USE_MONGO:
        users_col = mongo_db["users"]
        patients_col = mongo_db["patients"]
        action_logs_col = mongo_db["action_logs"]

        seed_users_mongo = [
            {"id": 1, "username": "doc_smith", "password": "doc123", "full_name": "Dr. John Smith", "role": "Doctor"},
            {"id": 2, "username": "nurse_sarah", "password": "nurse123", "full_name": "Nurse Sarah Connor", "role": "Nurse"},
            {"id": 3, "username": "reception_user", "password": "rec123", "full_name": "Reception Desk", "role": "Receptionist"},
            {"id": 4, "username": "helper_mark", "password": "help123", "full_name": "Helper Mark", "role": "General Helper"},
            {"id": 5, "username": "admin", "password": "admin123", "full_name": "System Administrator", "role": "Admin"}
        ]
        for u in seed_users_mongo:
            if users_col.count_documents({"username": u["username"]}) == 0:
                users_col.insert_one(u)

        if patients_col.count_documents({}) == 0:
            seed_patients = [
                {"id": 1, "patient_name": "John Doe", "ward": "General Ward A", "room_no": "101", "bed_no": "A1", "age": 45, "gender": "Male", "esp_device_id": "ESP_ROOM101_A1", "esp_mac": "A4:CF:12:89:5B:01", "status": "NORMAL", "assigned_doctor_name": "Dr. John Smith", "admitted_at": "2026-09-01 10:00:00"},
                {"id": 2, "patient_name": "Alice Smith", "ward": "ICU", "room_no": "102", "bed_no": "B1", "age": 62, "gender": "Female", "esp_device_id": "ESP_ROOM102_B1", "esp_mac": "B8:27:EB:14:9C:02", "status": "NORMAL", "assigned_doctor_name": "Dr. John Smith", "admitted_at": "2026-09-05 14:30:00"},
                {"id": 3, "patient_name": "Robert Johnson", "ward": "Cardiology", "room_no": "103", "bed_no": "A2", "age": 38, "gender": "Male", "esp_device_id": "ESP_ROOM103_A2", "esp_mac": "CC:50:E3:88:2A:03", "status": "NORMAL", "assigned_doctor_name": "Unassigned", "admitted_at": "2026-09-08 09:15:00"},
                {"id": 4, "patient_name": "Emma Davis", "ward": "General Ward B", "room_no": "104", "bed_no": "B2", "age": 29, "gender": "Female", "esp_device_id": "ESP_ROOM104_B2", "esp_mac": "00:1B:44:11:3A:04", "status": "NORMAL", "assigned_doctor_name": "Unassigned", "admitted_at": "2026-09-10 11:45:00"}
            ]
            patients_col.insert_many(seed_patients)

            for p in seed_patients:
                action_logs_col.insert_one({
                    "patient_id": p["id"],
                    "staff_name": "System",
                    "staff_role": "Receptionist",
                    "comment": f"Patient {p['patient_name']} admitted to {p['ward']} (Room {p['room_no']}, Bed {p['bed_no']}).",
                    "action_type": "NOTE",
                    "timestamp": p["admitted_at"]
                })
    else:
        conn = get_sqlite_db()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL
            )
        ''')

        seed_users = [
            ("doc_smith", "doc123", "Dr. John Smith", "Doctor"),
            ("nurse_sarah", "nurse123", "Nurse Sarah Connor", "Nurse"),
            ("reception_user", "rec123", "Reception Desk", "Receptionist"),
            ("helper_mark", "help123", "Helper Mark", "General Helper"),
            ("admin", "admin123", "System Administrator", "Admin")
        ]
        for u, p, name, role in seed_users:
            cursor.execute("SELECT id FROM users WHERE username = ?", (u,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO users (username, password, full_name, role) VALUES (?, ?, ?, ?)", (u, p, name, role))
        conn.commit()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_name TEXT NOT NULL,
                ward TEXT DEFAULT 'General Ward',
                room_no TEXT NOT NULL,
                bed_no TEXT NOT NULL,
                age INTEGER,
                gender TEXT,
                esp_device_id TEXT UNIQUE,
                esp_mac TEXT,
                status TEXT DEFAULT 'NORMAL',
                is_pinned INTEGER DEFAULT 0,
                assigned_doctor_name TEXT DEFAULT 'Unassigned',
                admitted_at TIMESTAMP,
                discharged_at TIMESTAMP
            )
        ''')

        cursor.execute("PRAGMA table_info(patients)")
        columns = [column[1] for column in cursor.fetchall()]
        cursor.execute("PRAGMA table_info(nurse_calls)")
        nc_cols = [c[1] for c in cursor.fetchall()]
        if 'resolved_by' not in nc_cols:
            cursor.execute("ALTER TABLE nurse_calls ADD COLUMN resolved_by TEXT")

        
        cursor.execute("PRAGMA table_info(service_requests)")
        sr_cols = [c[1] for c in cursor.fetchall()]
        if 'solved_by_roles' not in sr_cols:
            cursor.execute("ALTER TABLE service_requests ADD COLUMN solved_by_roles TEXT DEFAULT '[]'")
        if 'sla_tracking_id' not in sr_cols:
            cursor.execute("ALTER TABLE service_requests ADD COLUMN sla_tracking_id TEXT DEFAULT 'UNKNOWN'")


        cursor.execute("PRAGMA table_info(general_help_calls)")
        gh_cols = [c[1] for c in cursor.fetchall()]
        if 'resolved_by' not in gh_cols:
            cursor.execute("ALTER TABLE general_help_calls ADD COLUMN resolved_by TEXT")

        if 'assigned_doctor_name' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN assigned_doctor_name TEXT DEFAULT 'Unassigned'")
        if 'id_card_type' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN id_card_type TEXT DEFAULT 'Aadhar Card'")
        if 'id_card_no' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN id_card_no TEXT DEFAULT 'N/A'")
        if 'aadhar_no' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN aadhar_no TEXT DEFAULT 'N/A'")
        if 'mobile_no' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN mobile_no TEXT DEFAULT 'N/A'")
        if 'alt_mobile_no' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN alt_mobile_no TEXT DEFAULT 'N/A'")
        if 'emergency_contact_name' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN emergency_contact_name TEXT DEFAULT 'N/A'")
        if 'cause_of_admission' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN cause_of_admission TEXT DEFAULT 'General Checkup'")
        if 'admitted_by' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN admitted_by TEXT DEFAULT 'Reception Desk'")
        if 'referred_by' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN referred_by TEXT DEFAULT 'Self / Walk-in'")
        if 'admission_notes' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN admission_notes TEXT DEFAULT 'N/A'")
        if 'comments' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN comments TEXT DEFAULT 'N/A'")
        if 'custom_fields' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN custom_fields TEXT DEFAULT '{}'")
        if 'health_condition' not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN health_condition INTEGER DEFAULT 100")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS service_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                room_no TEXT NOT NULL,
                bed_no TEXT NOT NULL,
                ward TEXT DEFAULT 'General Ward',
                requested_by TEXT NOT NULL,
                requested_role TEXT NOT NULL,
                target_roles TEXT NOT NULL,
                instructions TEXT,
                target_minutes INTEGER DEFAULT 15,
                due_by_time TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                served_at TIMESTAMP,
                served_by TEXT,
                served_notes TEXT,
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_patient_selections (
                user_id INTEGER NOT NULL,
                patient_id INTEGER NOT NULL,
                is_selected INTEGER DEFAULT 1,
                is_pinned INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, patient_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prescriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                doctor_name TEXT NOT NULL,
                medication TEXT NOT NULL,
                dosage TEXT NOT NULL,
                duration TEXT NOT NULL,
                instructions TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nurse_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                room_no TEXT NOT NULL,
                bed_no TEXT NOT NULL,
                call_type TEXT NOT NULL,
                status TEXT DEFAULT 'ACTIVE',
                called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                acknowledged_at TIMESTAMP,
                resolved_at TIMESTAMP,
                acknowledged_by TEXT,
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                staff_name TEXT NOT NULL,
                staff_role TEXT NOT NULL,
                comment TEXT NOT NULL,
                action_type TEXT DEFAULT 'NOTE',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS general_help_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                room_no TEXT NOT NULL,
                bed_no TEXT NOT NULL,
                ward TEXT DEFAULT 'General Ward',
                call_type TEXT DEFAULT 'BEDSIDE_CALL',
                status TEXT DEFAULT 'ACTIVE',
                assigned_by TEXT DEFAULT 'Bedside Unit',
                assigned_role TEXT DEFAULT 'Patient',
                notes TEXT,
                called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                acknowledged_at TIMESTAMP,
                resolved_at TIMESTAMP,
                acknowledged_by TEXT,
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notice_board_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_name TEXT NOT NULL,
                sender_role TEXT NOT NULL,
                target_type TEXT DEFAULT 'ALL',
                target_department TEXT DEFAULT 'ALL',
                target_recipient TEXT DEFAULT 'ALL',
                message TEXT NOT NULL,
                priority TEXT DEFAULT 'NORMAL',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute("SELECT COUNT(*) as cnt FROM patients")
        if cursor.fetchone()['cnt'] == 0:
            seed_patients = [
                ("John Doe", "General Ward A", "101", "A1", 45, "Male", "ESP_ROOM101_A1", "A4:CF:12:89:5B:01", "Dr. John Smith", "Aadhar Card", "9876-5432-1098", "+91 98765-43210", "+91 98765-43211", "Mary Doe (Spouse)", "Severe Acute Chest Pain", "Reception Desk", "Dr. R. Sharma (City Clinic)", "Initial ECG normal. Kept under observation in ICU."),
                ("Alice Smith", "ICU", "102", "B1", 62, "Female", "ESP_ROOM102_B1", "B8:27:EB:14:9C:02", "Dr. John Smith", "Passport", "A9876543", "+91 98123-45678", "+91 98123-45679", "Tom Smith (Son)", "Hypertension & Severe Dizziness", "Reception Desk", "Emergency Referral", "BP 170/110 mmHg on admission."),
                ("Robert Johnson", "Cardiology", "103", "A2", 38, "Male", "ESP_ROOM103_A2", "CC:50:E3:88:2A:03", "Unassigned", "Voter ID", "ABC1234567", "+91 97654-32109", "+91 97654-32110", "Mark Johnson (Brother)", "Arrhythmia Evaluation", "Reception Desk", "Self / Walk-in", "Scheduled for Holter monitor tracking."),
                ("Emma Davis", "General Ward B", "104", "B2", 29, "Female", "ESP_ROOM104_B2", "00:1B:44:11:3A:04", "Unassigned", "Driving License", "DL-0420110012345", "+91 96543-21098", "+91 96543-21099", "Sarah Davis (Mother)", "Post-op Care (Appendectomy)", "Reception Desk", "Dr. K. Patel", "Stable post-surgery recovery.")
            ]
            for name, ward, room, bed, age, gender, dev_id, mac, doc, id_type, id_no, mobile, alt_mobile, emg_contact, cause, adm_by, ref_by, notes in seed_patients:
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute('''
                    INSERT INTO patients (patient_name, ward, room_no, bed_no, age, gender, esp_device_id, esp_mac, assigned_doctor_name, id_card_type, id_card_no, aadhar_no, mobile_no, alt_mobile_no, emergency_contact_name, cause_of_admission, admitted_by, referred_by, admission_notes, admitted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (name, ward, room, bed, age, gender, dev_id, mac, doc, id_type, id_no, id_no, mobile, alt_mobile, emg_contact, cause, adm_by, ref_by, notes, now_str))
                p_id = cursor.lastrowid

                cursor.execute('''
                    INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type)
                    VALUES (?, 'System', 'Receptionist', ?, 'NOTE')
                ''', (p_id, f"Patient {name} admitted to {ward} (Room {room}, Bed {bed})."))
        else:
            cursor.execute("UPDATE patients SET id_card_type = 'Aadhar Card', id_card_no = '9876-5432-1098', aadhar_no = '9876-5432-1098', mobile_no = '+91 98765-43210' WHERE id = 1 AND (id_card_no IS NULL OR id_card_no = 'N/A')")
            cursor.execute("UPDATE patients SET id_card_type = 'Passport', id_card_no = 'A9876543', aadhar_no = 'A9876543', mobile_no = '+91 98123-45678' WHERE id = 2 AND (id_card_no IS NULL OR id_card_no = 'N/A')")
            cursor.execute("UPDATE patients SET id_card_type = 'Voter ID', id_card_no = 'ABC1234567', aadhar_no = 'ABC1234567', mobile_no = '+91 97654-32109' WHERE id = 3 AND (id_card_no IS NULL OR id_card_no = 'N/A')")
            cursor.execute("UPDATE patients SET id_card_type = 'Driving License', id_card_no = 'DL-0420110012345', aadhar_no = 'DL-0420110012345', mobile_no = '+91 96543-21098' WHERE id = 4 AND (id_card_no IS NULL OR id_card_no = 'N/A')")
            
            cursor.execute("UPDATE patients SET alt_mobile_no = '+91 98765-43211', emergency_contact_name = 'Mary Doe (Spouse)' WHERE id = 1 AND (alt_mobile_no IS NULL OR alt_mobile_no = 'N/A')")
            cursor.execute("UPDATE patients SET alt_mobile_no = '+91 98123-45679', emergency_contact_name = 'Tom Smith (Son)' WHERE id = 2 AND (alt_mobile_no IS NULL OR alt_mobile_no = 'N/A')")
            cursor.execute("UPDATE patients SET alt_mobile_no = '+91 97654-32110', emergency_contact_name = 'Mark Johnson (Brother)' WHERE id = 3 AND (alt_mobile_no IS NULL OR alt_mobile_no = 'N/A')")
            cursor.execute("UPDATE patients SET alt_mobile_no = '+91 96543-21099', emergency_contact_name = 'Sarah Davis (Mother)' WHERE id = 4 AND (alt_mobile_no IS NULL OR alt_mobile_no = 'N/A')")

            cursor.execute("UPDATE patients SET cause_of_admission = 'Severe Acute Chest Pain', admitted_by = 'Reception Desk', referred_by = 'Dr. R. Sharma', admission_notes = 'Initial ECG normal. Kept under observation in ICU.' WHERE id = 1 AND (cause_of_admission IS NULL OR cause_of_admission = 'General Checkup')")
            cursor.execute("UPDATE patients SET cause_of_admission = 'Hypertension & Dizziness', admitted_by = 'Reception Desk', referred_by = 'Emergency Referral', admission_notes = 'BP 170/110 mmHg on admission.' WHERE id = 2 AND (cause_of_admission IS NULL OR cause_of_admission = 'General Checkup')")
            cursor.execute("UPDATE patients SET cause_of_admission = 'Arrhythmia Evaluation', admitted_by = 'Reception Desk', referred_by = 'Self / Walk-in', admission_notes = 'Scheduled for Holter monitor tracking.' WHERE id = 3 AND (cause_of_admission IS NULL OR cause_of_admission = 'General Checkup')")
            cursor.execute("UPDATE patients SET cause_of_admission = 'Post-op Care (Appendectomy)', admitted_by = 'Reception Desk', referred_by = 'Dr. K. Patel', admission_notes = 'Stable post-surgery recovery.' WHERE id = 4 AND (cause_of_admission IS NULL OR cause_of_admission = 'General Checkup')")

        conn.commit()
        conn.close()

init_db()

def get_local_ips():
    ip_list = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary_ip = s.getsockname()[0]
        s.close()
        ip_list.append(primary_ip)
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if ip not in ip_list and not ip.startswith("127."):
                ip_list.append(ip)
    except Exception:
        pass

    if not ip_list:
        ip_list.append("127.0.0.1")
    return ip_list

def format_elapsed_time(start_str, end_str):
    if not start_str or not end_str:
        return "N/A"
    try:
        s_dt = datetime.datetime.strptime(str(start_str), "%Y-%m-%d %H:%M:%S")
        e_dt = datetime.datetime.strptime(str(end_str), "%Y-%m-%d %H:%M:%S")
        secs = int((e_dt - s_dt).total_seconds())
        if secs < 0:
            secs = 0
        mins = secs // 60
        rem_secs = secs % 60
        if mins == 0:
            return f"{rem_secs}s"
        return f"{mins}m {rem_secs}s"
    except Exception:
        return "N/A"

BEDSIDE_PRESS_HISTORY = {}
RAPID_PRESS_WINDOW_SECONDS = 30
RAPID_PRESS_COUNT_THRESHOLD = 3

def record_and_check_rapid_press(room_no, bed_no, call_type):
    key = f"{room_no}_{bed_no}"
    now = time.time()
    if key not in BEDSIDE_PRESS_HISTORY:
        BEDSIDE_PRESS_HISTORY[key] = []
    
    BEDSIDE_PRESS_HISTORY[key] = [
        p for p in BEDSIDE_PRESS_HISTORY[key]
        if now - p["timestamp"] <= RAPID_PRESS_WINDOW_SECONDS
    ]
    
    BEDSIDE_PRESS_HISTORY[key].append({"timestamp": now, "call_type": call_type})
    recent = BEDSIDE_PRESS_HISTORY[key]
    
    same_button_count = sum(1 for p in recent if p["call_type"] == call_type)
    unique_buttons = set(p["call_type"] for p in recent)
    
    is_urgent = False
    msg = ""
    if same_button_count >= RAPID_PRESS_COUNT_THRESHOLD:
        is_urgent = True
        msg = f"🚨 URGENT EMERGENCY ALERT: Button '{call_type}' pressed {same_button_count} times rapidly within {RAPID_PRESS_WINDOW_SECONDS}s at Room {room_no}, Bed {bed_no}! Doctor, Nurse, and General Helper requested URGENTLY!"
    elif len(unique_buttons) >= 2 and len(recent) >= 3:
        is_urgent = True
        msg = f"🚨 URGENT EMERGENCY ALERT: Multiple buttons ({', '.join(unique_buttons)}) pressed rapidly within {RAPID_PRESS_WINDOW_SECONDS}s at Room {room_no}, Bed {bed_no}! Doctor, Nurse, and General Helper requested URGENTLY!"
        
    return is_urgent, msg, len(recent)

def broadcast_led_state(room_no, bed_no, led_state, call_type="NORMAL"):
    payload = {
        "room_no": room_no,
        "bed_no": bed_no,
        "led_state": led_state, # SOLID, BLINKING, OFF
        "call_type": call_type,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    socketio.emit("led_state_changed", payload)
    return payload

def trigger_general_help_call(room_no, bed_no, call_type="BEDSIDE_CALL", notes="General Help / Attendee requested.", assigned_by="Bedside Unit", assigned_role="Patient", patient_id=None):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if USE_MONGO:
        patients_col = mongo_db["patients"]
        help_col = mongo_db["general_help_calls"]

        patient = None
        if patient_id:
            patient = patients_col.find_one({"id": int(patient_id)})
        elif room_no and bed_no:
            patient = patients_col.find_one({"room_no": room_no, "bed_no": bed_no, "status": {"$nin": ["DISCHARGED", "DECEASED"]}})

        p_id = patient["id"] if patient else (int(patient_id) if patient_id else None)
        p_name = patient["patient_name"] if patient else f"Patient (Room {room_no}-{bed_no})"
        ward = patient["ward"] if patient else "General Ward"
        r_no = patient["room_no"] if patient else room_no
        b_no = patient["bed_no"] if patient else bed_no

        help_doc = {
            "patient_id": p_id,
            "patient_name": p_name,
            "room_no": r_no,
            "bed_no": b_no,
            "ward": ward,
            "call_type": call_type,
            "status": "ACTIVE",
            "assigned_by": assigned_by,
            "assigned_role": assigned_role,
            "notes": notes,
            "called_at": now_str
        }
        res = help_col.insert_one(help_doc)
        help_doc["id"] = str(res.inserted_id)
        help_doc.pop("_id", None)
    else:
        conn = get_sqlite_db()
        cursor = conn.cursor()

        patient = None
        if patient_id:
            cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
            patient = cursor.fetchone()
        elif room_no and bed_no:
            cursor.execute("SELECT * FROM patients WHERE room_no = ? AND bed_no = ? AND status NOT IN ('DISCHARGED', 'DECEASED')", (room_no, bed_no))
            patient = cursor.fetchone()

        p_id = patient["id"] if patient else (int(patient_id) if patient_id else None)
        p_name = patient["patient_name"] if patient else f"Patient (Room {room_no}-{bed_no})"
        ward = patient["ward"] if patient else "General Ward"
        r_no = patient["room_no"] if patient else room_no
        b_no = patient["bed_no"] if patient else bed_no

        cursor.execute('''
            INSERT INTO general_help_calls (patient_id, room_no, bed_no, ward, call_type, status, assigned_by, assigned_role, notes, called_at)
            VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?)
        ''', (p_id, r_no, b_no, ward, call_type, assigned_by, assigned_role, notes, now_str))
        help_id = cursor.lastrowid
        conn.commit()
        conn.close()

        help_doc = {
            "id": help_id,
            "patient_id": p_id,
            "patient_name": p_name,
            "room_no": r_no,
            "bed_no": b_no,
            "ward": ward,
            "call_type": call_type,
            "status": "ACTIVE",
            "assigned_by": assigned_by,
            "assigned_role": assigned_role,
            "notes": notes,
            "called_at": now_str
        }

    socketio.emit("general_help_alert", help_doc)
    return help_doc

def trigger_bedside_call(room_no, bed_no, call_type="NURSE_CALL", device_id=None, esp_mac=None):
    is_urgent, urgent_msg, press_count = record_and_check_rapid_press(room_no, bed_no, call_type)
    effective_status = "URGENT_EMERGENCY" if is_urgent else call_type

    if call_type == "GENERAL_HELP":
        # Multiple presses of GENERAL_HELP are an emergency for the General Helper team, NOT a clinical medical emergency!
        helper_msg = (
            f"🚨 URGENT ATTENDEE ALERT: General Help button pressed {press_count} times rapidly within 30s at Room {room_no}, Bed {bed_no}! Immediate Attendee Assistance Required!"
            if is_urgent
            else "General Help / Attendee requested from Bedside Unit."
        )

        help_doc = trigger_general_help_call(
            room_no=room_no,
            bed_no=bed_no,
            call_type="BEDSIDE_CALL",
            notes=helper_msg,
            assigned_by="Bedside Unit",
            assigned_role="Patient"
        )
        help_doc["is_urgent"] = is_urgent
        help_doc["message"] = helper_msg

        # Update patient status to GENERAL_HELP on main patient records
        if USE_MONGO:
            p_doc = mongo_db["patients"].find_one({"room_no": room_no, "bed_no": bed_no, "status": {"$nin": ["DISCHARGED", "DECEASED"]}})
            if p_doc:
                mongo_db["patients"].update_one({"id": p_doc["id"]}, {"$set": {"status": "GENERAL_HELP"}})
                p_updated = mongo_db["patients"].find_one({"id": p_doc["id"]})
                p_updated.pop("_id", None)
                socketio.emit("patient_updated", p_updated)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE patients SET status = 'GENERAL_HELP' WHERE room_no = ? AND bed_no = ? AND status NOT IN ('DISCHARGED', 'DECEASED')", (room_no, bed_no))
            conn.commit()
            cursor.execute("SELECT * FROM patients WHERE room_no = ? AND bed_no = ? AND status NOT IN ('DISCHARGED', 'DECEASED')", (room_no, bed_no))
            p_row = cursor.fetchone()
            if p_row:
                p_dict = dict(p_row)
                socketio.emit("patient_updated", p_dict)
            conn.close()

        # Emit urgent alert specifically to General Helper portal
        if is_urgent:
            socketio.emit("general_help_urgent_alert", {
                "room_no": room_no,
                "bed_no": bed_no,
                "call_type": "GENERAL_HELP",
                "message": helper_msg,
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        broadcast_led_state(room_no, bed_no, "SOLID", "GENERAL_HELP")
        return help_doc

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if USE_MONGO:
        patients_col = mongo_db["patients"]
        calls_col = mongo_db["nurse_calls"]
        logs_col = mongo_db["action_logs"]

        patient = None
        if device_id:
            patient = patients_col.find_one({"esp_device_id": device_id})
        if not patient and room_no and bed_no:
            patient = patients_col.find_one({"room_no": room_no, "bed_no": bed_no, "status": {"$nin": ["DISCHARGED", "DECEASED"]}})

        if not patient:
            max_p = list(patients_col.find().sort("id", -1).limit(1))
            new_id = (max_p[0]["id"] + 1) if max_p else 1
            patient_name = f"Patient (Room {room_no}-{bed_no})"
            dev_id = device_id or f"ESP_{room_no}_{bed_no}"
            patient = {
                "id": new_id,
                "patient_name": patient_name,
                "ward": "General Ward",
                "room_no": room_no,
                "bed_no": bed_no,
                "esp_device_id": dev_id,
                "esp_mac": esp_mac or "UNKNOWN",
                "status": effective_status,
                "is_pinned": 0,
                "assigned_doctor_name": "Unassigned",
                "admitted_at": now_str
            }
            patients_col.insert_one(patient)
        else:
            patients_col.update_one({"id": patient["id"]}, {"$set": {"status": effective_status}})

        patient_id = patient["id"]
        call_doc = {
            "patient_id": patient_id,
            "room_no": room_no,
            "bed_no": bed_no,
            "call_type": call_type,
            "status": "ACTIVE",
            "called_at": now_str
        }
        res = calls_col.insert_one(call_doc)

        call_label = "URGENT EMERGENCY CALL (DOCTOR, NURSE, HELPER NEEDED)" if is_urgent else ("CALL NURSE" if call_type == "NURSE_CALL" else "EMERGENCY CALL DOCTOR")
        logs_col.insert_one({
            "patient_id": patient_id,
            "staff_name": "Bedside Unit",
            "staff_role": "Bedside Unit",
            "comment": urgent_msg if is_urgent else f"Patient triggered {call_label} from Room {room_no}, Bed {bed_no}.",
            "action_type": "URGENT_EMERGENCY" if is_urgent else "CALL_TRIGGERED",
            "timestamp": now_str
        })

        updated_patient = patients_col.find_one({"id": patient_id})
        updated_patient.pop("_id", None)
        call_id = str(res.inserted_id)

    else:
        conn = get_sqlite_db()
        cursor = conn.cursor()

        patient = None
        if device_id:
            cursor.execute("SELECT * FROM patients WHERE esp_device_id = ?", (device_id,))
            patient = cursor.fetchone()
        if not patient and room_no and bed_no:
            cursor.execute("SELECT * FROM patients WHERE room_no = ? AND bed_no = ? AND status NOT IN ('DISCHARGED', 'DECEASED')", (room_no, bed_no))
            patient = cursor.fetchone()

        if not patient:
            patient_name = f"Patient (Room {room_no}-{bed_no})"
            base_dev_id = device_id or f"ESP_{room_no}_{bed_no}"
            dev_id = base_dev_id
            cursor.execute("SELECT id FROM patients WHERE esp_device_id = ?", (dev_id,))
            if cursor.fetchone():
                dev_id = f"{base_dev_id}_{int(time.time())}"
            cursor.execute('''
                INSERT INTO patients (patient_name, ward, room_no, bed_no, esp_device_id, esp_mac, status, assigned_doctor_name, admitted_at)
                VALUES (?, 'General Ward', ?, ?, ?, ?, ?, 'Unassigned', ?)
            ''', (patient_name, room_no, bed_no, dev_id, esp_mac or "UNKNOWN", effective_status, now_str))
            patient_id = cursor.lastrowid
        else:
            patient_id = patient['id']
            cursor.execute("UPDATE patients SET status = ? WHERE id = ?", (effective_status, patient_id))

        cursor.execute('''
            INSERT INTO nurse_calls (patient_id, room_no, bed_no, call_type, status, called_at)
            VALUES (?, ?, ?, ?, 'ACTIVE', ?)
        ''', (patient_id, room_no, bed_no, call_type, now_str))
        call_id = cursor.lastrowid

        call_label = "URGENT EMERGENCY CALL (DOCTOR, NURSE, HELPER NEEDED)" if is_urgent else ("CALL NURSE" if call_type == "NURSE_CALL" else "EMERGENCY CALL DOCTOR")
        cursor.execute('''
            INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
            VALUES (?, 'Bedside Unit', 'Bedside Unit', ?, ?, ?)
        ''', (patient_id, urgent_msg if is_urgent else f"Patient triggered {call_label} from Room {room_no}, Bed {bed_no}.", "URGENT_EMERGENCY" if is_urgent else "CALL_TRIGGERED", now_str))

        conn.commit()

        cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
        updated_patient = dict(cursor.fetchone())
        conn.close()

    call_payload = {
        "call_id": call_id,
        "patient_id": patient_id,
        "patient_name": updated_patient['patient_name'],
        "room_no": room_no,
        "bed_no": bed_no,
        "call_type": effective_status,
        "called_at": now_str,
        "status": "ACTIVE",
        "is_urgent": is_urgent,
        "message": urgent_msg if is_urgent else ""
    }

    if is_urgent:
        socketio.emit("urgent_call_alert", call_payload)

    socketio.emit("nurse_call_alert", call_payload)
    socketio.emit("patient_updated", updated_patient)
    broadcast_led_state(room_no, bed_no, "SOLID", effective_status)

    return call_payload

# Authentication & Session Routes
@app.route("/login")
def login_view():
    return render_template("login.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    user = None
    if USE_MONGO:
        users_col = mongo_db["users"]
        user = users_col.find_one({"username": username, "password": password})
        if user:
            user.pop("_id", None)
    else:
        conn = get_sqlite_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        row = cursor.fetchone()
        conn.close()
        if row:
            user = dict(row)

    if user:
        session["user"] = user
        return jsonify({"status": "success", "user": user})
    return jsonify({"status": "error", "message": "Invalid username or password"}), 401

@app.route("/api/logout", methods=["GET", "POST"])
def api_logout():
    session.pop("user", None)
    return jsonify({"status": "success"})

@app.route("/api/me", methods=["GET"])
def api_me():
    user = session.get("user")
    if user:
        return jsonify({"status": "success", "user": user})
    return jsonify({"status": "error", "message": "Not logged in"}), 401

@app.route("/")
def index():
    if "user" not in session:
        return redirect("/login")
    return render_template("index.html")

@app.route("/bedside")
def bedside_view():
    return render_template("bedside.html")

# REST API Endpoints
@app.route("/api/bedside/call", methods=["POST"])
def api_bedside_call():
    try:
        data = request.get_json(force=True)
        room_no = data.get("room_no") or data.get("room")
        bed_no = data.get("bed_no") or data.get("bed")
        call_type = data.get("call_type", "NURSE_CALL")
        device_id = data.get("device_id")
        esp_mac = data.get("esp_mac") or data.get("mac")

        if not room_no or not bed_no:
            return jsonify({"status": "error", "message": "room_no and bed_no are required"}), 400

        result = trigger_bedside_call(room_no, bed_no, call_type, device_id, esp_mac)
        return jsonify({"status": "success", "data": result}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def fetch_active_calls_for_patients(patient_ids, conn=None):
    """
    Fetches active (unresolved) calls for given patient IDs, grouped by call_type.
    Returns dict: { patient_id: [ call_obj, ... ] }
    """
    result = {pid: [] for pid in patient_ids}
    if not patient_ids:
        return result

    if USE_MONGO:
        calls_col = mongo_db["nurse_calls"]
        gh_col = mongo_db["general_help_calls"]
        
        mongo_calls = list(calls_col.find({
            "patient_id": {"$in": patient_ids},
            "status": {"$ne": "RESOLVED"}
        }).sort("id", 1))
        
        mongo_gh = list(gh_col.find({
            "patient_id": {"$in": patient_ids},
            "status": {"$nin": ["RESOLVED", "COMPLETED"]}
        }).sort("id", 1))
        
        grouped = {}
        for c in mongo_calls:
            pid = c.get("patient_id")
            ctype = c.get("call_type", "NURSE_CALL")
            key = (pid, ctype)
            if key not in grouped:
                grouped[key] = {
                    "call_type": ctype,
                    "status": c.get("status", "ACTIVE"),
                    "timestamps": [],
                    "first_called_at": str(c.get("called_at", "")),
                    "acknowledged_by": c.get("acknowledged_by")
                }
            t_str = str(c.get("called_at", ""))
            time_part = t_str.split(" ")[-1] if " " in t_str else t_str
            if time_part not in grouped[key]["timestamps"]:
                grouped[key]["timestamps"].append(time_part)
            if c.get("status") == "ACKNOWLEDGED":
                grouped[key]["status"] = "ACKNOWLEDGED"
                if c.get("acknowledged_by"):
                    grouped[key]["acknowledged_by"] = c.get("acknowledged_by")
                    
        for (pid, ctype), data in grouped.items():
            title = "🚨 EMERGENCY DOCTOR CALL" if "DOCTOR" in ctype else ("🚨 URGENT EMERGENCY CALL" if "URGENT" in ctype else "🔔 NURSE CALL")
            cat = "Doctor" if "DOCTOR" in ctype else "Nurse"
            if pid in result:
                result[pid].append({
                    "call_type": ctype,
                    "title": title,
                    "category": cat,
                    "status": data["status"],
                    "press_count": len(data["timestamps"]),
                    "first_called_at": data["first_called_at"],
                    "timestamps": data["timestamps"],
                    "acknowledged_by": data["acknowledged_by"]
                })
                
        gh_grouped = {}
        for gh in mongo_gh:
            pid = gh.get("patient_id")
            key = (pid, "GENERAL_HELP")
            if key not in gh_grouped:
                gh_grouped[key] = {
                    "call_type": "GENERAL_HELP",
                    "status": gh.get("status", "ACTIVE"),
                    "timestamps": [],
                    "first_called_at": str(gh.get("called_at", "")),
                    "acknowledged_by": gh.get("acknowledged_by") or gh.get("assigned_helper")
                }
            t_str = str(gh.get("called_at", ""))
            time_part = t_str.split(" ")[-1] if " " in t_str else t_str
            if time_part not in gh_grouped[key]["timestamps"]:
                gh_grouped[key]["timestamps"].append(time_part)
            if gh.get("status") in ["ACKNOWLEDGED", "IN_PROGRESS"]:
                gh_grouped[key]["status"] = "ACKNOWLEDGED"
                if gh.get("acknowledged_by") or gh.get("assigned_helper"):
                    gh_grouped[key]["acknowledged_by"] = gh.get("acknowledged_by") or gh.get("assigned_helper")

        for (pid, ctype), data in gh_grouped.items():
            if pid in result:
                result[pid].append({
                    "call_type": "GENERAL_HELP",
                    "title": "🤝 GENERAL HELP CALL",
                    "category": "General Helper",
                    "status": data["status"],
                    "press_count": len(data["timestamps"]),
                    "first_called_at": data["first_called_at"],
                    "timestamps": data["timestamps"],
                    "acknowledged_by": data["acknowledged_by"]
                })

    else:
        close_conn = False
        if not conn:
            conn = get_sqlite_db()
            close_conn = True
        cursor = conn.cursor()
        
        placeholders = ",".join(["?"] * len(patient_ids))
        
        cursor.execute(f'''
            SELECT id, patient_id, call_type, status, called_at, acknowledged_by
            FROM nurse_calls
            WHERE patient_id IN ({placeholders}) AND status != 'RESOLVED'
            ORDER BY id ASC
        ''', tuple(patient_ids))
        n_rows = cursor.fetchall()
        
        grouped = {}
        for r in n_rows:
            pid = r["patient_id"]
            ctype = r["call_type"]
            key = (pid, ctype)
            if key not in grouped:
                grouped[key] = {
                    "call_type": ctype,
                    "status": r["status"],
                    "timestamps": [],
                    "first_called_at": str(r["called_at"] or ""),
                    "acknowledged_by": r["acknowledged_by"]
                }
            t_str = str(r["called_at"] or "")
            time_part = t_str.split(" ")[-1] if " " in t_str else t_str
            grouped[key]["timestamps"].append(time_part)
            if r["status"] == "ACKNOWLEDGED":
                grouped[key]["status"] = "ACKNOWLEDGED"
                if r["acknowledged_by"]:
                    grouped[key]["acknowledged_by"] = r["acknowledged_by"]
                    
        for (pid, ctype), data in grouped.items():
            title = "🚨 EMERGENCY DOCTOR CALL" if "DOCTOR" in ctype else ("🚨 URGENT EMERGENCY CALL" if "URGENT" in ctype else "🔔 NURSE CALL")
            cat = "Doctor" if "DOCTOR" in ctype else "Nurse"
            if pid in result:
                result[pid].append({
                    "call_type": ctype,
                    "title": title,
                    "category": cat,
                    "status": data["status"],
                    "press_count": len(data["timestamps"]),
                    "first_called_at": data["first_called_at"],
                    "timestamps": data["timestamps"],
                    "acknowledged_by": data["acknowledged_by"]
                })

        cursor.execute(f'''
            SELECT id, patient_id, call_type, status, called_at, acknowledged_by
            FROM general_help_calls
            WHERE patient_id IN ({placeholders}) AND status NOT IN ('RESOLVED', 'COMPLETED')
            ORDER BY id ASC
        ''', tuple(patient_ids))
        gh_rows = cursor.fetchall()
        
        gh_grouped = {}
        for r in gh_rows:
            pid = r["patient_id"]
            key = (pid, "GENERAL_HELP")
            if key not in gh_grouped:
                gh_grouped[key] = {
                    "call_type": "GENERAL_HELP",
                    "status": r["status"],
                    "timestamps": [],
                    "first_called_at": str(r["called_at"] or ""),
                    "acknowledged_by": r["acknowledged_by"]
                }
            t_str = str(r["called_at"] or "")
            time_part = t_str.split(" ")[-1] if " " in t_str else t_str
            gh_grouped[key]["timestamps"].append(time_part)
            if r["status"] in ["ACKNOWLEDGED", "IN_PROGRESS"]:
                gh_grouped[key]["status"] = "ACKNOWLEDGED"
                if r["acknowledged_by"]:
                    gh_grouped[key]["acknowledged_by"] = r["acknowledged_by"]

        for (pid, ctype), data in gh_grouped.items():
            if pid in result:
                result[pid].append({
                    "call_type": "GENERAL_HELP",
                    "title": "🤝 GENERAL HELP CALL",
                    "category": "General Helper",
                    "status": data["status"],
                    "press_count": len(data["timestamps"]),
                    "first_called_at": data["first_called_at"],
                    "timestamps": data["timestamps"],
                    "acknowledged_by": data["acknowledged_by"]
                })

        if close_conn:
            conn.close()
            
    return result

@app.route("/api/patients", methods=["GET"])
def api_get_patients():
    include_archived = request.args.get("include_archived", "false").lower() == "true"
    user = session.get("user")
    user_id = user.get("id") if user else None
    
    now_dt = datetime.datetime.now()
    if USE_MONGO:
        patients_col = mongo_db["patients"]
        selections_col = mongo_db["user_patient_selections"]
        req_col = mongo_db["service_requests"]
        query = {} if include_archived else {"status": {"$nin": ["DISCHARGED", "DECEASED"]}}
        patients = list(patients_col.find(query).sort([("id", 1)]))
        
        user_selections = {}
        if user_id:
            for s in selections_col.find({"user_id": user_id}):
                user_selections[s["patient_id"]] = s
                
        p_ids = [p["id"] for p in patients]
        active_calls_map = fetch_active_calls_for_patients(p_ids)

        for p in patients:
            p.pop("_id", None)
            sel = user_selections.get(p["id"], {})
            p["is_selected"] = sel.get("is_selected", 1)
            p["is_pinned"] = sel.get("is_pinned", 0)
            
            ac_list = active_calls_map.get(p["id"], [])
            p["active_calls"] = ac_list
            if ac_list:
                p["active_call_type"] = ac_list[0]["call_type"]
                p["active_call_time"] = ac_list[0]["first_called_at"]
                p["active_call_count"] = sum([c["press_count"] for c in ac_list])
            else:
                p["active_call_type"] = None
                p["active_call_time"] = None
                p["active_call_count"] = 0

            srv_reqs = list(req_col.find({"patient_id": p["id"], "status": {"$in": ["PENDING", "IN_PROCESS"]}}).sort("id", -1))
            active_reqs = []
            min_rem = 999999999
            for sr in srv_reqs:
                sr.pop("_id", None)
                if sr.get("due_by_time"):
                    try:
                        due_dt = datetime.datetime.strptime(sr["due_by_time"], "%Y-%m-%d %H:%M:%S")
                        sr["remaining_seconds"] = int((due_dt - now_dt).total_seconds())
                    except Exception:
                        sr["remaining_seconds"] = 0
                else:
                    sr["remaining_seconds"] = 0
                active_reqs.append(sr)
                if sr["remaining_seconds"] < min_rem:
                    min_rem = sr["remaining_seconds"]
            p["active_service_requests"] = active_reqs
            p["min_remaining_seconds"] = min_rem
            
        patients.sort(key=lambda x: (-x.get("is_pinned", 0), x.get("min_remaining_seconds", 999999999), x.get("id", 0)))
        return jsonify(patients)
    else:
        conn = get_sqlite_db()
        cursor = conn.cursor()
        where_clause = "" if include_archived else "WHERE p.status NOT IN ('DISCHARGED', 'DECEASED')"
        cursor.execute(f'''
            SELECT p.id, p.patient_name, p.ward, p.room_no, p.bed_no, p.age, p.gender, 
                   p.esp_device_id, p.esp_mac, p.status, p.assigned_doctor_name,
                   COALESCE(p.id_card_type, 'Aadhar Card') as id_card_type,
                   COALESCE(p.id_card_no, p.aadhar_no, 'N/A') as id_card_no,
                   COALESCE(p.aadhar_no, 'N/A') as aadhar_no, COALESCE(p.mobile_no, 'N/A') as mobile_no,
                   COALESCE(p.alt_mobile_no, 'N/A') as alt_mobile_no,
                   COALESCE(p.emergency_contact_name, 'N/A') as emergency_contact_name,
                   COALESCE(p.cause_of_admission, 'General Checkup') as cause_of_admission,
                   COALESCE(p.admitted_by, 'Reception Desk') as admitted_by,
                   COALESCE(p.referred_by, 'Self / Walk-in') as referred_by,
                   COALESCE(p.admission_notes, 'N/A') as admission_notes,
                   COALESCE(p.comments, 'N/A') as comments,
                   COALESCE(p.custom_fields, '{{}}') as custom_fields,
                   COALESCE(p.health_condition, 100) as health_condition,
                   p.admitted_at, p.discharged_at,
                   COALESCE(ups.is_selected, 1) as is_selected,
                   COALESCE(ups.is_pinned, 0) as is_pinned
            FROM patients p
            LEFT JOIN user_patient_selections ups ON ups.patient_id = p.id AND ups.user_id = ?
            {where_clause}
            ORDER BY COALESCE(ups.is_pinned, 0) DESC, p.id ASC
        ''', (user_id,))
        patients = [dict(row) for row in cursor.fetchall()]

        p_ids = [p["id"] for p in patients]
        active_calls_map = fetch_active_calls_for_patients(p_ids, conn=conn)

        cursor.execute("SELECT * FROM service_requests WHERE status IN ('PENDING', 'IN_PROCESS') ORDER BY id DESC")
        all_pending_reqs = cursor.fetchall()

        reqs_by_patient = {}
        for r in all_pending_reqs:
            req_dict = dict(r)
            try:
                req_dict["target_roles"] = json.loads(req_dict["target_roles"])
            except Exception:
                pass
            if req_dict.get("due_by_time"):
                try:
                    due_dt = datetime.datetime.strptime(req_dict["due_by_time"], "%Y-%m-%d %H:%M:%S")
                    req_dict["remaining_seconds"] = int((due_dt - now_dt).total_seconds())
                except Exception:
                    req_dict["remaining_seconds"] = 0
            else:
                req_dict["remaining_seconds"] = 0
            
            pid = req_dict.get("patient_id")
            if pid:
                if pid not in reqs_by_patient:
                    reqs_by_patient[pid] = []
                reqs_by_patient[pid].append(req_dict)

        for p in patients:
            ac_list = active_calls_map.get(p["id"], [])
            p["active_calls"] = ac_list
            if ac_list:
                p["active_call_type"] = ac_list[0]["call_type"]
                p["active_call_time"] = ac_list[0]["first_called_at"]
                p["active_call_count"] = sum([c["press_count"] for c in ac_list])
            else:
                p["active_call_type"] = None
                p["active_call_time"] = None
                p["active_call_count"] = 0

            p_reqs = reqs_by_patient.get(p["id"], [])
            p["active_service_requests"] = p_reqs
            if p_reqs:
                p["min_remaining_seconds"] = min([r["remaining_seconds"] for r in p_reqs])
            else:
                p["min_remaining_seconds"] = 999999999

        patients.sort(key=lambda x: (-x.get("is_pinned", 0), x.get("min_remaining_seconds", 999999999), x.get("id", 0)))
        conn.close()
        return jsonify(patients)

# Prescription Endpoints
@app.route("/api/prescription/add", methods=["POST"])
def api_add_prescription():
    try:
        user = session.get("user")
        data = request.get_json(force=True)
        patient_id = int(data.get("patient_id"))
        doctor_name = (user.get("full_name") if user else None) or data.get("doctor_name", "Dr. Smith")
        medication = data.get("medication")
        dosage = data.get("dosage", "1 tab 2x daily")
        duration = data.get("duration", "5 days")
        instructions = data.get("instructions", "Take after meals")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not medication:
            return jsonify({"status": "error", "message": "Medication name required"}), 400

        comment = f"PRESCRIPTION ADDED: {medication} ({dosage}, for {duration}). Instructions: {instructions}"

        if USE_MONGO:
            rx_col = mongo_db["prescriptions"]
            logs_col = mongo_db["action_logs"]

            rx_doc = {
                "patient_id": patient_id,
                "doctor_name": doctor_name,
                "medication": medication,
                "dosage": dosage,
                "duration": duration,
                "instructions": instructions,
                "created_at": now_str
            }
            res = rx_col.insert_one(rx_doc)
            rx_doc["_id"] = str(res.inserted_id)

            logs_col.insert_one({
                "patient_id": patient_id,
                "staff_name": doctor_name,
                "staff_role": "Doctor",
                "comment": comment,
                "action_type": "NOTE",
                "timestamp": now_str
            })
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO prescriptions (patient_id, doctor_name, medication, dosage, duration, instructions, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (patient_id, doctor_name, medication, dosage, duration, instructions, now_str))
            rx_id = cursor.lastrowid

            cursor.execute('''
                INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                VALUES (?, ?, 'Doctor', ?, 'NOTE', ?)
            ''', (patient_id, doctor_name, comment, now_str))
            conn.commit()

            cursor.execute("SELECT * FROM prescriptions WHERE id = ?", (rx_id,))
            rx_doc = dict(cursor.fetchone())
            conn.close()

        socketio.emit("new_prescription", {"patient_id": patient_id, "prescription": rx_doc})
        return jsonify({"status": "success", "prescription": rx_doc}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/prescriptions/<int:patient_id>", methods=["GET"])
def api_get_prescriptions(patient_id):
    if USE_MONGO:
        rx_col = mongo_db["prescriptions"]
        items = list(rx_col.find({"patient_id": patient_id}).sort("created_at", -1))
        for item in items:
            item["_id"] = str(item["_id"])
        return jsonify(items)
    else:
        conn = get_sqlite_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY id DESC", (patient_id,))
        items = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(items)
@app.route("/api/patient/select", methods=["POST"])
def api_toggle_select():
    try:
        user = session.get("user")
        if not user:
            return jsonify({"status": "error", "message": "Not authenticated"}), 401
        user_id = user["id"]
        data = request.get_json(force=True)
        patient_id = int(data.get("patient_id"))
        
        if USE_MONGO:
            selections_col = mongo_db["user_patient_selections"]
            sel = selections_col.find_one({"user_id": user_id, "patient_id": patient_id})
            if sel:
                new_val = 0 if sel.get("is_selected", 1) == 1 else 1
                selections_col.update_one({"user_id": user_id, "patient_id": patient_id}, {"$set": {"is_selected": new_val}})
            else:
                new_val = 0
                selections_col.insert_one({"user_id": user_id, "patient_id": patient_id, "is_selected": 0, "is_pinned": 0})
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute("SELECT is_selected FROM user_patient_selections WHERE user_id = ? AND patient_id = ?", (user_id, patient_id))
            row = cursor.fetchone()
            if row:
                new_val = 0 if row['is_selected'] == 1 else 1
                cursor.execute("UPDATE user_patient_selections SET is_selected = ? WHERE user_id = ? AND patient_id = ?", (new_val, user_id, patient_id))
            else:
                new_val = 0
                cursor.execute("INSERT INTO user_patient_selections (user_id, patient_id, is_selected, is_pinned) VALUES (?, ?, 0, 0)", (user_id, patient_id))
            conn.commit()
            conn.close()
            
        return jsonify({"status": "success", "is_selected": new_val}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/patient/pin", methods=["POST"])
def api_toggle_pin():
    try:
        user = session.get("user")
        if not user:
            return jsonify({"status": "error", "message": "Not authenticated"}), 401
        user_id = user["id"]
        data = request.get_json(force=True)
        patient_id = int(data.get("patient_id"))

        if USE_MONGO:
            selections_col = mongo_db["user_patient_selections"]
            sel = selections_col.find_one({"user_id": user_id, "patient_id": patient_id})
            if sel:
                new_pinned = 0 if sel.get("is_pinned", 0) == 1 else 1
                selections_col.update_one({"user_id": user_id, "patient_id": patient_id}, {"$set": {"is_pinned": new_pinned, "is_selected": 1}})
            else:
                new_pinned = 1
                selections_col.insert_one({"user_id": user_id, "patient_id": patient_id, "is_selected": 1, "is_pinned": 1})
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute("SELECT is_pinned FROM user_patient_selections WHERE user_id = ? AND patient_id = ?", (user_id, patient_id))
            row = cursor.fetchone()
            if row:
                new_pinned = 0 if row['is_pinned'] == 1 else 1
                cursor.execute("UPDATE user_patient_selections SET is_pinned = ?, is_selected = 1 WHERE user_id = ? AND patient_id = ?", (new_pinned, user_id, patient_id))
            else:
                new_pinned = 1
                cursor.execute("INSERT INTO user_patient_selections (user_id, patient_id, is_selected, is_pinned) VALUES (?, ?, 1, 1)", (user_id, patient_id))
            conn.commit()
            conn.close()

        return jsonify({"status": "success", "is_pinned": new_pinned}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/patient/edit", methods=["POST"])
def api_edit_patient():
    try:
        data = request.get_json(force=True)
        patient_id = data.get("id")
        user = session.get("user")
        staff_name = user.get("full_name") if user else "Reception Desk"
        staff_role = user.get("role") if user else "Receptionist"
        
        if staff_role not in ["Receptionist", "Admin"]:
            return jsonify({"status": "error", "message": "Unauthorized"}), 403

        if not patient_id:
            return jsonify({"status": "error", "message": "Patient ID required"}), 400

        name = data.get("patient_name")
        ward = data.get("ward")
        room = data.get("room_no")
        bed = data.get("bed_no")
        age = data.get("age")
        gender = data.get("gender")
        mobile_no = data.get("mobile_no")
        cause = data.get("cause_of_admission")
        
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if USE_MONGO:
            patients_col = mongo_db["patients"]
            logs_col = mongo_db["action_logs"]
            
            old_p = patients_col.find_one({"id": int(patient_id)})
            if not old_p:
                return jsonify({"status": "error", "message": "Patient not found"}), 404
                
            updates = {}
            changes = []
            if name and name != old_p.get("patient_name"): updates["patient_name"] = name; changes.append(f"Name: {old_p.get('patient_name')} -> {name}")
            if ward and ward != old_p.get("ward"): updates["ward"] = ward; changes.append(f"Ward: {old_p.get('ward')} -> {ward}")
            if room and room != old_p.get("room_no"): updates["room_no"] = room; changes.append(f"Room: {old_p.get('room_no')} -> {room}")
            if bed and bed != old_p.get("bed_no"): updates["bed_no"] = bed; changes.append(f"Bed: {old_p.get('bed_no')} -> {bed}")
            if age and int(age) != old_p.get("age"): updates["age"] = int(age); changes.append(f"Age: {old_p.get('age')} -> {age}")
            if gender and gender != old_p.get("gender"): updates["gender"] = gender; changes.append(f"Gender: {old_p.get('gender')} -> {gender}")
            if mobile_no and mobile_no != old_p.get("mobile_no"): updates["mobile_no"] = mobile_no; changes.append(f"Mobile: {old_p.get('mobile_no')} -> {mobile_no}")
            if cause and cause != old_p.get("cause_of_admission"): updates["cause_of_admission"] = cause; changes.append(f"Cause: {old_p.get('cause_of_admission')} -> {cause}")
            
            if not updates:
                return jsonify({"status": "success", "message": "No changes made."})
                
            patients_col.update_one({"id": int(patient_id)}, {"$set": updates})
            
            logs_col.insert_one({
                "patient_id": int(patient_id),
                "staff_name": staff_name,
                "staff_role": staff_role,
                "comment": "Edited details: " + ", ".join(changes),
                "action_type": "NOTE",
                "timestamp": now_str
            })
        else:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
            old_p = cursor.fetchone()
            if not old_p:
                conn.close()
                return jsonify({"status": "error", "message": "Patient not found"}), 404
                
            updates = []
            params = []
            changes = []
            
            def check_update(field, val, col_idx):
                old_val = old_p[col_idx]
                if val and str(val) != str(old_val):
                    updates.append(f"{field} = ?")
                    params.append(val)
                    changes.append(f"{field}: {old_val} -> {val}")

            # Note: Need correct column indices or dict factory. We assume dict factory is used.
            # get_db_connection sets row_factory = sqlite3.Row
            old_p_dict = dict(old_p)
            
            if name and name != old_p_dict.get("patient_name"): updates.append("patient_name = ?"); params.append(name); changes.append(f"Name: {old_p_dict.get('patient_name')} -> {name}")
            if ward and ward != old_p_dict.get("ward"): updates.append("ward = ?"); params.append(ward); changes.append(f"Ward: {old_p_dict.get('ward')} -> {ward}")
            if room and room != old_p_dict.get("room_no"): updates.append("room_no = ?"); params.append(room); changes.append(f"Room: {old_p_dict.get('room_no')} -> {room}")
            if bed and bed != old_p_dict.get("bed_no"): updates.append("bed_no = ?"); params.append(bed); changes.append(f"Bed: {old_p_dict.get('bed_no')} -> {bed}")
            if age and str(age) != str(old_p_dict.get("age")): updates.append("age = ?"); params.append(int(age)); changes.append(f"Age: {old_p_dict.get('age')} -> {age}")
            if gender and gender != old_p_dict.get("gender"): updates.append("gender = ?"); params.append(gender); changes.append(f"Gender: {old_p_dict.get('gender')} -> {gender}")
            if mobile_no and mobile_no != old_p_dict.get("mobile_no"): updates.append("mobile_no = ?"); params.append(mobile_no); changes.append(f"Mobile: {old_p_dict.get('mobile_no')} -> {mobile_no}")
            if cause and cause != old_p_dict.get("cause_of_admission"): updates.append("cause_of_admission = ?"); params.append(cause); changes.append(f"Cause: {old_p_dict.get('cause_of_admission')} -> {cause}")
            
            if not updates:
                conn.close()
                return jsonify({"status": "success", "message": "No changes made."})
                
            query = f"UPDATE patients SET {', '.join(updates)} WHERE id = ?"
            params.append(patient_id)
            cursor.execute(query, params)
            
            cursor.execute('''
                INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                VALUES (?, ?, ?, ?, 'NOTE', ?)
            ''', (patient_id, staff_name, staff_role, "Edited details: " + ", ".join(changes), now_str))
            
            conn.commit()
            conn.close()

        socketio.emit('patient_updated', {"message": "Patient details updated"})
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/patient/add", methods=["POST"])
def api_add_patient():
    try:
        data = request.get_json(force=True)
        name = data.get("patient_name")
        ward = data.get("ward", "General Ward")
        room = data.get("room_no")
        bed = data.get("bed_no")
        age = data.get("age", 0)
        gender = data.get("gender", "Unknown")
        id_card_type = data.get("id_card_type", "Aadhar Card")
        id_card_no = data.get("id_card_no") or data.get("aadhar_no", "N/A")
        aadhar_no = id_card_no
        mobile_no = data.get("mobile_no", "N/A")
        alt_mobile_no = data.get("alt_mobile_no", "N/A")
        emergency_contact_name = data.get("emergency_contact_name", "N/A")
        cause_of_admission = data.get("cause_of_admission", "General Checkup")
        user = session.get("user")
        admitted_by = data.get("admitted_by") or (user.get("full_name") if user else "Reception Desk")
        referred_by = data.get("referred_by", "Self / Walk-in")
        admission_notes = data.get("admission_notes", "N/A")
        comments = data.get("comments", "N/A")
        custom_fields = data.get("custom_fields", {})
        if isinstance(custom_fields, dict):
            import json
            custom_fields_str = json.dumps(custom_fields)
        else:
            custom_fields_str = str(custom_fields) if custom_fields else "{}"

        dev_id = data.get("esp_device_id") or f"ESP_{room}_{bed}"
        mac = data.get("esp_mac", "N/A")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not name or not room or not bed:
            return jsonify({"status": "error", "message": "Name, Room, and Bed are required"}), 400

        if USE_MONGO:
            patients_col = mongo_db["patients"]
            logs_col = mongo_db["action_logs"]
            max_p = list(patients_col.find().sort("id", -1).limit(1))
            new_id = (max_p[0]["id"] + 1) if max_p else 1
            patient = {
                "id": new_id,
                "patient_name": name,
                "ward": ward,
                "room_no": room,
                "bed_no": bed,
                "age": age,
                "gender": gender,
                "id_card_type": id_card_type,
                "id_card_no": id_card_no,
                "aadhar_no": aadhar_no,
                "mobile_no": mobile_no,
                "alt_mobile_no": alt_mobile_no,
                "emergency_contact_name": emergency_contact_name,
                "cause_of_admission": cause_of_admission,
                "admitted_by": admitted_by,
                "referred_by": referred_by,
                "admission_notes": admission_notes,
                "comments": comments,
                "custom_fields": custom_fields if isinstance(custom_fields, dict) else (json.loads(custom_fields_str) if custom_fields_str.startswith("{") else {}),
                "esp_device_id": dev_id,
                "esp_mac": mac,
                "status": "NORMAL",
                "is_pinned": 0,
                "assigned_doctor_name": "Unassigned",
                "admitted_at": now_str
            }
            patients_col.insert_one(patient)

            logs_col.insert_one({
                "patient_id": new_id,
                "staff_name": admitted_by,
                "staff_role": "Receptionist",
                "comment": f"New admission: {name} assigned to {ward} (Room {room}, Bed {bed}). Cause: {cause_of_admission}. Referred by: {referred_by}.",
                "action_type": "NOTE",
                "timestamp": now_str
            })

            patient.pop("_id", None)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO patients (patient_name, ward, room_no, bed_no, age, gender, id_card_type, id_card_no, aadhar_no, mobile_no, alt_mobile_no, emergency_contact_name, cause_of_admission, admitted_by, referred_by, admission_notes, comments, custom_fields, esp_device_id, esp_mac, assigned_doctor_name, admitted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Unassigned', ?)
            ''', (name, ward, room, bed, age, gender, id_card_type, id_card_no, aadhar_no, mobile_no, alt_mobile_no, emergency_contact_name, cause_of_admission, admitted_by, referred_by, admission_notes, comments, custom_fields_str, dev_id, mac, now_str))
            p_id = cursor.lastrowid

            cursor.execute('''
                INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                VALUES (?, ?, 'Receptionist', ?, 'NOTE', ?)
            ''', (p_id, admitted_by, f"New admission: {name} assigned to {ward} (Room {room}, Bed {bed}). Cause: {cause_of_admission}. Referred by: {referred_by}.", now_str))
            conn.commit()

            cursor.execute("SELECT * FROM patients WHERE id = ?", (p_id,))
            patient = dict(cursor.fetchone())
            conn.close()

        socketio.emit("patient_added", patient)
        return jsonify({"status": "success", "patient": patient}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/patient/transfer", methods=["POST"])
def api_transfer_patient():
    try:
        data = request.get_json(force=True)
        patient_id = int(data.get("patient_id"))
        new_ward = data.get("new_ward", "General Ward")
        new_room = data.get("new_room_no")
        new_bed = data.get("new_bed_no")
        staff_name = data.get("staff_name", "Nurse")
        staff_role = data.get("staff_role", "Nurse")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not new_room or not new_bed:
            return jsonify({"status": "error", "message": "New room and bed number required"}), 400

        comment = f"PATIENT TRANSFERRED by {staff_name} [{staff_role}] -> New Location: {new_ward} (Room {new_room}, Bed {new_bed})."

        if USE_MONGO:
            patients_col = mongo_db["patients"]
            logs_col = mongo_db["action_logs"]
            patients_col.update_one(
                {"id": patient_id},
                {"$set": {"ward": new_ward, "room_no": new_room, "bed_no": new_bed}}
            )
            logs_col.insert_one({
                "patient_id": patient_id,
                "staff_name": staff_name,
                "staff_role": staff_role,
                "comment": comment,
                "action_type": "PATIENT_TRANSFERRED",
                "timestamp": now_str
            })
            updated_patient = patients_col.find_one({"id": patient_id})
            updated_patient.pop("_id", None)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE patients 
                SET ward = ?, room_no = ?, bed_no = ?
                WHERE id = ?
            ''', (new_ward, new_room, new_bed, patient_id))

            cursor.execute('''
                INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                VALUES (?, ?, ?, ?, 'PATIENT_TRANSFERRED', ?)
            ''', (patient_id, staff_name, staff_role, comment, now_str))

            conn.commit()
            cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
            updated_patient = dict(cursor.fetchone())
            conn.close()

        socketio.emit("patient_updated", updated_patient)
        return jsonify({"status": "success", "patient": updated_patient}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/patient/status", methods=["POST"])
def api_update_patient_status():
    try:
        data = request.get_json(force=True)
        patient_id = int(data.get("patient_id"))
        new_status = data.get("new_status")
        staff_name = data.get("staff_name", "Doctor")
        staff_role = data.get("staff_role", "Doctor")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not new_status:
            return jsonify({"status": "error", "message": "new_status required"}), 400

        comment = f"STATUS UPDATE: Patient status changed to '{new_status}' by {staff_name} [{staff_role}]."

        if USE_MONGO:
            patients_col = mongo_db["patients"]
            logs_col = mongo_db["action_logs"]
            update_data = {"status": new_status}
            if new_status in ["DISCHARGED", "DECEASED"]:
                update_data["discharged_at"] = now_str
                update_data["is_pinned"] = 0

            patients_col.update_one({"id": patient_id}, {"$set": update_data})
            logs_col.insert_one({
                "patient_id": patient_id,
                "staff_name": staff_name,
                "staff_role": staff_role,
                "comment": comment,
                "action_type": "STATUS_CHANGE",
                "timestamp": now_str
            })
            updated_patient = patients_col.find_one({"id": patient_id})
            updated_patient.pop("_id", None)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            discharged_at_val = now_str if new_status in ["DISCHARGED", "DECEASED"] else None
            cursor.execute('''
                UPDATE patients 
                SET status = ?, discharged_at = COALESCE(?, discharged_at), is_pinned = CASE WHEN ? IN ('DISCHARGED', 'DECEASED') THEN 0 ELSE is_pinned END
                WHERE id = ?
            ''', (new_status, discharged_at_val, new_status, patient_id))

            cursor.execute('''
                INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                VALUES (?, ?, ?, ?, 'STATUS_CHANGE', ?)
            ''', (patient_id, staff_name, staff_role, comment, now_str))

            conn.commit()
            cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
            updated_patient = dict(cursor.fetchone())
            conn.close()

        socketio.emit("patient_updated", updated_patient)
        return jsonify({"status": "success", "patient": updated_patient}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route("/api/call/acknowledge", methods=["POST"])
def api_acknowledge_call():
    try:
        data = request.get_json(force=True)
        patient_id = int(data.get("patient_id"))
        user = session.get("user")
        staff_name = (user.get("full_name") if user else None) or data.get("staff_name", "Staff")
        staff_role = (user.get("role") if user else None) or data.get("staff_role", "Nurse")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        req_call_type = data.get("call_type") or data.get("call_category")

        # Determine active call_type if not specified
        if not req_call_type:
            active_list = fetch_active_calls_for_patients([patient_id]).get(patient_id, [])
            req_call_type = active_list[0]["call_type"] if active_list else ""

        # Strict Role Authorization: Doctor -> Doctor Calls, Nurse -> Nurse Calls, Helper -> Helper Calls
        if staff_role != "Admin":
            if "DOCTOR" in req_call_type and "Doctor" not in staff_role:
                return jsonify({"status": "error", "message": "Access denied: Only Doctors are authorized to acknowledge Doctor Calls."}), 403
            if "NURSE" in req_call_type and "Nurse" not in staff_role:
                return jsonify({"status": "error", "message": "Access denied: Only Nurses are authorized to acknowledge Nurse Calls."}), 403
            if ("HELP" in req_call_type or "GENERAL" in req_call_type) and ("General Helper" not in staff_role and "Helper" not in staff_role):
                return jsonify({"status": "error", "message": "Access denied: Only General Helpers are authorized to acknowledge General Help Calls."}), 403

        if USE_MONGO:
            patients_col = mongo_db["patients"]
            calls_col = mongo_db["nurse_calls"]
            logs_col = mongo_db["action_logs"]

            if "GENERAL" in req_call_type or "HELP" in req_call_type:
                mongo_db["general_help_calls"].update_many(
                    {"patient_id": patient_id, "status": {"$in": ["ACTIVE", "PENDING"]}},
                    {"$set": {"status": "ACKNOWLEDGED", "acknowledged_by": f"{staff_name} ({staff_role})", "acknowledged_at": now_str}}
                )
            else:
                calls_col.update_many(
                    {"patient_id": patient_id, "call_type": req_call_type, "status": "ACTIVE"},
                    {"$set": {"status": "ACKNOWLEDGED", "acknowledged_at": now_str, "acknowledged_by": f"{staff_name} ({staff_role})"}}
                )

            patients_col.update_one({"id": patient_id}, {"$set": {"status": "IN_TREATMENT"}})

            logs_col.insert_one({
                "patient_id": patient_id,
                "staff_name": staff_name,
                "staff_role": staff_role,
                "comment": f"{req_call_type} call acknowledged by {staff_name} [{staff_role}].",
                "action_type": "CALL_ACKNOWLEDGED",
                "timestamp": now_str
            })

            patient = patients_col.find_one({"id": patient_id})
            patient.pop("_id", None)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            if "GENERAL" in req_call_type or "HELP" in req_call_type:
                cursor.execute('''
                    UPDATE general_help_calls 
                    SET status = 'ACKNOWLEDGED', acknowledged_at = ?, acknowledged_by = ?
                    WHERE patient_id = ? AND status IN ('ACTIVE', 'PENDING')
                ''', (now_str, f"{staff_name} ({staff_role})", patient_id))
            else:
                cursor.execute('''
                    UPDATE nurse_calls 
                    SET status = 'ACKNOWLEDGED', acknowledged_at = ?, acknowledged_by = ?
                    WHERE patient_id = ? AND call_type = ? AND status = 'ACTIVE'
                ''', (now_str, f"{staff_name} ({staff_role})", patient_id, req_call_type))

            cursor.execute("UPDATE patients SET status = 'IN_TREATMENT' WHERE id = ?", (patient_id,))

            cursor.execute('''
                INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                VALUES (?, ?, ?, ?, 'CALL_ACKNOWLEDGED', ?)
            ''', (patient_id, staff_name, staff_role, f"{req_call_type} call acknowledged by {staff_name} [{staff_role}].", now_str))

            conn.commit()
            cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
            patient = dict(cursor.fetchone())
            conn.close()

        socketio.emit("call_updated", {"patient_id": patient_id, "call_type": req_call_type, "status": "ACKNOWLEDGED"})
        socketio.emit("patient_updated", patient)
        if patient:
            broadcast_led_state(patient.get("room_no"), patient.get("bed_no"), "BLINKING", patient.get("status"))
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/call/resolve", methods=["POST"])
def api_resolve_call():
    try:
        data = request.get_json(force=True)
        patient_id = int(data.get("patient_id"))
        user = session.get("user")
        staff_name = (user.get("full_name") if user else None) or data.get("staff_name", "Staff")
        staff_role = (user.get("role") if user else None) or data.get("staff_role", "Nurse")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        req_call_type = data.get("call_type") or data.get("call_category")

        # Determine active call_type if not specified
        if not req_call_type:
            active_list = fetch_active_calls_for_patients([patient_id]).get(patient_id, [])
            req_call_type = active_list[0]["call_type"] if active_list else ""

        # Strict Role Authorization: Doctor -> Doctor Calls, Nurse -> Nurse Calls, Helper -> Helper Calls
        if staff_role != "Admin":
            if "DOCTOR" in req_call_type and "Doctor" not in staff_role:
                return jsonify({"status": "error", "message": "Access denied: Only Doctors are authorized to clear Doctor Calls."}), 403
            if "NURSE" in req_call_type and "Nurse" not in staff_role:
                return jsonify({"status": "error", "message": "Access denied: Only Nurses are authorized to clear Nurse Calls."}), 403
            if ("HELP" in req_call_type or "GENERAL" in req_call_type) and ("General Helper" not in staff_role and "Helper" not in staff_role):
                return jsonify({"status": "error", "message": "Access denied: Only General Helpers are authorized to clear General Help Calls."}), 403

        if USE_MONGO:
            patients_col = mongo_db["patients"]
            calls_col = mongo_db["nurse_calls"]
            logs_col = mongo_db["action_logs"]

            if "GENERAL" in req_call_type or "HELP" in req_call_type:
                mongo_db["general_help_calls"].update_many(
                    {"patient_id": patient_id, "status": {"$ne": "RESOLVED"}},
                    {"$set": {"status": "RESOLVED", "resolved_at": now_str}}
                )
            else:
                calls_col.update_many(
                    {"patient_id": patient_id, "call_type": req_call_type, "status": {"$ne": "RESOLVED"}},
                    {"$set": {"status": "RESOLVED", "resolved_at": now_str}}
                )

            # Re-evaluate remaining active calls for patient
            rem_calls = fetch_active_calls_for_patients([patient_id]).get(patient_id, [])
            new_patient_status = rem_calls[0]["call_type"] if rem_calls else "NORMAL"
            patients_col.update_one({"id": patient_id}, {"$set": {"status": new_patient_status}})

            logs_col.insert_one({
                "patient_id": patient_id,
                "staff_name": staff_name,
                "staff_role": staff_role,
                "comment": f"{req_call_type} call resolved and cleared by {staff_name} [{staff_role}].",
                "action_type": "CALL_RESOLVED",
                "timestamp": now_str
            })

            patient = patients_col.find_one({"id": patient_id})
            patient.pop("_id", None)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()

            if "GENERAL" in req_call_type or "HELP" in req_call_type:
                cursor.execute('''
                    UPDATE general_help_calls 
                    SET status = 'RESOLVED', resolved_at = ?
                    WHERE patient_id = ? AND status != 'RESOLVED'
                ''', (now_str, patient_id))
            else:
                cursor.execute('''
                    UPDATE nurse_calls 
                    SET status = 'RESOLVED', resolved_at = ?
                    WHERE patient_id = ? AND call_type = ? AND status != 'RESOLVED'
                ''', (now_str, patient_id, req_call_type))

            # Re-evaluate remaining active calls for patient
            rem_calls = fetch_active_calls_for_patients([patient_id], conn=conn).get(patient_id, [])
            new_patient_status = rem_calls[0]["call_type"] if rem_calls else "NORMAL"

            cursor.execute("UPDATE patients SET status = ? WHERE id = ?", (new_patient_status, patient_id))

            cursor.execute('''
                INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                VALUES (?, ?, ?, ?, 'CALL_RESOLVED', ?)
            ''', (patient_id, staff_name, staff_role, f"{req_call_type} call resolved and cleared by {staff_name} [{staff_role}].", now_str))

            conn.commit()
            cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
            patient = dict(cursor.fetchone())
            conn.close()

        if patient and new_patient_status == "NORMAL":
            key = f"{patient.get('room_no')}_{patient.get('bed_no')}"
            if key in BEDSIDE_PRESS_HISTORY:
                BEDSIDE_PRESS_HISTORY[key] = []
            broadcast_led_state(patient.get("room_no"), patient.get("bed_no"), "OFF", "NORMAL")

        socketio.emit("call_updated", {"patient_id": patient_id, "call_type": req_call_type, "status": "RESOLVED"})
        socketio.emit("patient_updated", patient)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/call/serve", methods=["POST"])
def api_call_serve():
    try:
        data = request.get_json(force=True)
        patient_id = data.get("patient_id")
        room_no = data.get("room_no")
        bed_no = data.get("bed_no")
        user = session.get("user")
        staff_name = (user.get("full_name") if user else None) or data.get("staff_name", "Staff")
        staff_role = (user.get("role") if user else None) or data.get("staff_role", "Nurse")
        notes = data.get("notes") or data.get("comment", "Patient attended and served at bedside.")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not patient_id and (not room_no or not bed_no):
            return jsonify({"status": "error", "message": "patient_id or room_no/bed_no required"}), 400

        if USE_MONGO:
            patients_col = mongo_db["patients"]
            calls_col = mongo_db["nurse_calls"]
            help_col = mongo_db["general_help_calls"]
            logs_col = mongo_db["action_logs"]

            if patient_id:
                patient = patients_col.find_one({"id": int(patient_id)})
            else:
                patient = patients_col.find_one({"room_no": room_no, "bed_no": bed_no, "status": {"$nin": ["DISCHARGED", "DECEASED"]}})

            if not patient:
                return jsonify({"status": "error", "message": "Patient not found"}), 404

            p_id = patient["id"]
            r_no = patient["room_no"]
            b_no = patient["bed_no"]

            calls_col.update_many({"patient_id": p_id, "status": {"$ne": "RESOLVED"}}, {"$set": {"status": "RESOLVED", "resolved_at": now_str}})
            help_col.update_many({"patient_id": p_id, "status": {"$ne": "RESOLVED"}}, {"$set": {"status": "RESOLVED", "resolved_at": now_str, "notes": notes}})
            patients_col.update_one({"id": p_id}, {"$set": {"status": "NORMAL"}})

            logs_col.insert_one({
                "patient_id": p_id,
                "staff_name": staff_name,
                "staff_role": staff_role,
                "comment": f"ATTENDANCE SERVED: {notes}",
                "action_type": "CALL_SERVED",
                "timestamp": now_str
            })

            updated_patient = patients_col.find_one({"id": p_id})
            updated_patient.pop("_id", None)

        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()

            if patient_id:
                cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
            else:
                cursor.execute("SELECT * FROM patients WHERE room_no = ? AND bed_no = ? AND status NOT IN ('DISCHARGED', 'DECEASED')", (room_no, bed_no))

            p_row = cursor.fetchone()
            if not p_row:
                conn.close()
                return jsonify({"status": "error", "message": "Patient not found"}), 404

            patient = dict(p_row)
            p_id = patient["id"]
            r_no = patient["room_no"]
            b_no = patient["bed_no"]

            cursor.execute("UPDATE nurse_calls SET status = 'RESOLVED', resolved_at = ? WHERE patient_id = ? AND status != 'RESOLVED'", (now_str, p_id))
            cursor.execute("UPDATE general_help_calls SET status = 'RESOLVED', resolved_at = ?, notes = COALESCE(notes || ' | Served: ' || ?, ?) WHERE patient_id = ? AND status != 'RESOLVED'", (now_str, notes, notes, p_id))
            cursor.execute("UPDATE patients SET status = 'NORMAL' WHERE id = ?", (p_id,))

            cursor.execute('''
                INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                VALUES (?, ?, ?, ?, 'CALL_SERVED', ?)
            ''', (p_id, staff_name, staff_role, f"ATTENDANCE SERVED: {notes}", now_str))

            conn.commit()
            cursor.execute("SELECT * FROM patients WHERE id = ?", (p_id,))
            updated_patient = dict(cursor.fetchone())
            conn.close()

        key = f"{r_no}_{b_no}"
        if key in BEDSIDE_PRESS_HISTORY:
            BEDSIDE_PRESS_HISTORY[key] = []

        broadcast_led_state(r_no, b_no, "OFF", "NORMAL")
        socketio.emit("call_updated", {"patient_id": p_id, "status": "SERVED"})
        socketio.emit("patient_updated", updated_patient)
        socketio.emit("general_help_updated", {"patient_id": p_id, "status": "RESOLVED"})

        return jsonify({"status": "success", "message": "Call served and attendance logged.", "patient": updated_patient}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/bedside/reset", methods=["POST"])
def api_bedside_reset():
    try:
        data = request.get_json(force=True)
        room_no = data.get("room_no", "").strip()
        bed_no = data.get("bed_no", "").strip()

        if not room_no or not bed_no:
            return jsonify({"status": "error", "message": "room_no and bed_no required"}), 400

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if USE_MONGO:
            patients_col = mongo_db["patients"]
            calls_col = mongo_db["nurse_calls"]
            help_col = mongo_db["general_help_calls"]
            logs_col = mongo_db["action_logs"]

            patient = patients_col.find_one({"room_no": room_no, "bed_no": bed_no, "status": {"$nin": ["DISCHARGED", "DECEASED"]}})
            if patient:
                p_id = patient["id"]
                calls_col.update_many({"patient_id": p_id, "status": {"$ne": "RESOLVED"}}, {"$set": {"status": "RESOLVED", "resolved_at": now_str}})
                help_col.update_many({"patient_id": p_id, "status": {"$ne": "RESOLVED"}}, {"$set": {"status": "RESOLVED", "resolved_at": now_str, "notes": "Reset from Bedside Unit"}})
                patients_col.update_one({"id": p_id}, {"$set": {"status": "NORMAL"}})
                logs_col.insert_one({
                    "patient_id": p_id,
                    "staff_name": "Bedside Unit",
                    "staff_role": "Patient / Bedside Reset",
                    "comment": "Call reset directly from Bedside Console.",
                    "action_type": "BEDSIDE_RESET",
                    "timestamp": now_str
                })
                updated_patient = patients_col.find_one({"id": p_id})
                updated_patient.pop("_id", None)
            else:
                updated_patient = {"room_no": room_no, "bed_no": bed_no, "status": "NORMAL"}
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM patients WHERE room_no = ? AND bed_no = ? AND status NOT IN ('DISCHARGED', 'DECEASED')", (room_no, bed_no))
            p_row = cursor.fetchone()
            if p_row:
                p_id = p_row["id"]
                cursor.execute("UPDATE nurse_calls SET status = 'RESOLVED', resolved_at = ? WHERE patient_id = ? AND status != 'RESOLVED'", (now_str, p_id))
                cursor.execute("UPDATE general_help_calls SET status = 'RESOLVED', resolved_at = ?, notes = COALESCE(notes || ' | Reset from Bedside', 'Reset from Bedside') WHERE patient_id = ? AND status != 'RESOLVED'", (now_str, p_id))
                cursor.execute("UPDATE patients SET status = 'NORMAL' WHERE id = ?", (p_id,))
                cursor.execute('''
                    INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                    VALUES (?, 'Bedside Unit', 'Patient / Bedside Reset', 'Call reset directly from Bedside Console.', 'BEDSIDE_RESET', ?)
                ''', (p_id, now_str))
                conn.commit()
                cursor.execute("SELECT * FROM patients WHERE id = ?", (p_id,))
                updated_patient = dict(cursor.fetchone())
            else:
                updated_patient = {"room_no": room_no, "bed_no": bed_no, "status": "NORMAL"}
            conn.close()

        key = f"{room_no}_{bed_no}"
        if key in BEDSIDE_PRESS_HISTORY:
            BEDSIDE_PRESS_HISTORY[key] = []

        broadcast_led_state(room_no, bed_no, "OFF", "NORMAL")
        socketio.emit("call_updated", {"room_no": room_no, "bed_no": bed_no, "status": "RESET"})
        socketio.emit("patient_updated", updated_patient)

        return jsonify({"status": "success", "message": "Bedside call reset successfully.", "patient": updated_patient}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/action_log/<int:patient_id>", methods=["GET"])
def api_get_record_book(patient_id):
    if USE_MONGO:
        patients_col = mongo_db["patients"]
        logs_col = mongo_db["action_logs"]
        patient = patients_col.find_one({"id": patient_id})
        if not patient:
            return jsonify({"status": "error", "message": "Patient not found"}), 404

        patient.pop("_id", None)
        logs = list(logs_col.find({"patient_id": patient_id}).sort("timestamp", -1))
        for l in logs:
            l.pop("_id", None)
        return jsonify({"patient": patient, "record_book": logs})
    else:
        conn = get_sqlite_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
        patient = cursor.fetchone()
        if not patient:
            conn.close()
            return jsonify({"status": "error", "message": "Patient not found"}), 404

        cursor.execute("SELECT * FROM action_logs WHERE patient_id = ? ORDER BY id DESC", (patient_id,))
        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify({"patient": dict(patient), "record_book": logs})

@app.route("/api/action_log/add", methods=["POST"])
def api_add_record_comment():
    try:
        data = request.get_json(force=True)
        patient_id = int(data.get("patient_id"))
        staff_name = data.get("staff_name", "Anonymous Staff")
        staff_role = data.get("staff_role", "Nurse")
        comment = data.get("comment")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not patient_id or not comment:
            return jsonify({"status": "error", "message": "Patient ID and comment are required"}), 400

        if USE_MONGO:
            logs_col = mongo_db["action_logs"]
            new_log = {
                "patient_id": patient_id,
                "staff_name": staff_name,
                "staff_role": staff_role,
                "comment": comment,
                "action_type": "NOTE",
                "timestamp": now_str
            }
            logs_col.insert_one(new_log)
            new_log.pop("_id", None)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                VALUES (?, ?, ?, ?, 'NOTE', ?)
            ''', (patient_id, staff_name, staff_role, comment, now_str))
            log_id = cursor.lastrowid
            conn.commit()

            cursor.execute("SELECT * FROM action_logs WHERE id = ?", (log_id,))
            new_log = dict(cursor.fetchone())
            conn.close()

        socketio.emit("new_action_log", {"patient_id": patient_id, "log": new_log})
        return jsonify({"status": "success", "log": new_log}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Data Anonymization / Privacy Masking Helper
def mask_name(name):
    if not name or name in ["N/A", "System", "Bedside Unit", "Anonymous Staff", "Unassigned"]:
        return name
    parts = name.strip().split()
    masked_parts = []
    for part in parts:
        if part in ["Dr.", "Nurse", "HOD", "Mr.", "Mrs.", "Ms."]:
            masked_parts.append(part)
        elif len(part) <= 2:
            masked_parts.append(part[0] + "*")
        else:
            masked_parts.append(part[0] + "*" * (len(part) - 2) + part[-1])
    return " ".join(masked_parts)

def query_report_logs(args):
    start_date = args.get("start_date", "").strip()
    end_date = args.get("end_date", "").strip()
    ward = args.get("ward", "ALL").strip()
    patient_id = args.get("patient_id", "ALL").strip()
    staff_role = args.get("role", "ALL").strip()
    action_type = args.get("action_type", "ALL").strip()
    group_by = args.get("group_by", "DETAILED").strip()
    chronology = args.get("chronology", "DESC").upper()
    mask_privacy = args.get("mask_privacy", "false").lower() == "true"

    order_sql = "ASC" if chronology == "ASC" else "DESC"

    if USE_MONGO:
        logs_col = mongo_db["action_logs"]
        patients_col = mongo_db["patients"]
        patients_map = {p["id"]: p for p in patients_col.find()}
        
        query = {}
        if staff_role and staff_role != "ALL":
            query["staff_role"] = staff_role
        if action_type and action_type != "ALL":
            query["action_type"] = action_type
        if patient_id and patient_id != "ALL":
            query["patient_id"] = int(patient_id)
        if start_date:
            query["timestamp"] = {"$gte": f"{start_date} 00:00:00"}
        if end_date:
            if "timestamp" in query:
                query["timestamp"]["$lte"] = f"{end_date} 23:59:59"
            else:
                query["timestamp"] = {"$lte": f"{end_date} 23:59:59"}

        mongo_sort = 1 if chronology == "ASC" else -1
        logs = list(logs_col.find(query).sort("timestamp", mongo_sort))

        raw_rows = []
        for l in logs:
            p = patients_map.get(l.get("patient_id"), {})
            if ward and ward != "ALL" and (p.get("ward") or "").lower() != ward.lower():
                continue

            p_name = p.get("patient_name", "N/A")
            s_name = l.get("staff_name", "Staff")

            if mask_privacy:
                p_name = mask_name(p_name)
                s_name = mask_name(s_name)

            raw_rows.append({
                "id": str(l.get("_id")),
                "timestamp": l.get("timestamp", ""),
                "patient_id": l.get("patient_id"),
                "patient_name": p_name,
                "ward": p.get("ward", "N/A"),
                "room_no": p.get("room_no", "N/A"),
                "bed_no": p.get("bed_no", "N/A"),
                "staff_name": s_name,
                "staff_role": l.get("staff_role", "Staff"),
                "action_type": l.get("action_type", "NOTE"),
                "comment": l.get("comment", "")
            })
    else:
        conn = get_sqlite_db()
        cursor = conn.cursor()
        
        where_conditions = []
        params = []

        if start_date:
            where_conditions.append("l.timestamp >= ?")
            params.append(f"{start_date} 00:00:00")
        if end_date:
            where_conditions.append("l.timestamp <= ?")
            params.append(f"{end_date} 23:59:59")
        if ward and ward != "ALL":
            where_conditions.append("LOWER(p.ward) = LOWER(?)")
            params.append(ward)
        if patient_id and patient_id != "ALL":
            where_conditions.append("l.patient_id = ?")
            params.append(int(patient_id))
        if staff_role and staff_role != "ALL":
            where_conditions.append("l.staff_role = ?")
            params.append(staff_role)
        if action_type and action_type != "ALL":
            where_conditions.append("l.action_type = ?")
            params.append(action_type)

        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

        cursor.execute(f'''
            SELECT l.*, p.patient_name, p.ward, p.room_no, p.bed_no
            FROM action_logs l
            LEFT JOIN patients p ON l.patient_id = p.id
            {where_clause}
            ORDER BY l.timestamp {order_sql}
        ''', params)

        rows = cursor.fetchall()
        raw_rows = []
        for r in rows:
            p_name = r["patient_name"] or "N/A"
            s_name = r["staff_name"] or "Staff"
            if mask_privacy:
                p_name = mask_name(p_name)
                s_name = mask_name(s_name)

            raw_rows.append({
                "id": r["id"],
                "timestamp": r["timestamp"],
                "patient_id": r["patient_id"],
                "patient_name": p_name,
                "ward": r["ward"] or "N/A",
                "room_no": r["room_no"] or "N/A",
                "bed_no": r["bed_no"] or "N/A",
                "staff_name": s_name,
                "staff_role": r["staff_role"],
                "action_type": r["action_type"],
                "comment": r["comment"]
            })
        conn.close()

    # Calculate Analytics Summary
    summary = {
        "total_events": len(raw_rows),
        "call_acks": sum(1 for r in raw_rows if r["action_type"] in ["CALL_ACKNOWLEDGED", "CALL_RESOLVED"]),
        "prescriptions": sum(1 for r in raw_rows if "PRESCRIPTION" in r["comment"].upper() or r["action_type"] == "PRESCRIPTION"),
        "transfers": sum(1 for r in raw_rows if r["action_type"] in ["PATIENT_TRANSFERRED", "STATUS_CHANGE"])
    }

    # Grouping / Segregation Modes
    if group_by == "BY_DATE":
        grouped_dict = {}
        for r in raw_rows:
            date_key = (r["timestamp"] or "").split(" ")[0] or "Unknown Date"
            if date_key not in grouped_dict:
                grouped_dict[date_key] = {"group_key": date_key, "total_events": 0, "calls": 0, "prescriptions": 0, "transfers": 0}
            grouped_dict[date_key]["total_events"] += 1
            if r["action_type"] in ["CALL_ACKNOWLEDGED", "CALL_RESOLVED"]: grouped_dict[date_key]["calls"] += 1
            if "PRESCRIPTION" in r["comment"].upper(): grouped_dict[date_key]["prescriptions"] += 1
            if r["action_type"] in ["PATIENT_TRANSFERRED", "STATUS_CHANGE"]: grouped_dict[date_key]["transfers"] += 1
        processed_rows = list(grouped_dict.values())

    elif group_by == "BY_PATIENT":
        grouped_dict = {}
        for r in raw_rows:
            p_key = f"{r['patient_name']} (Rm {r['room_no']}-{r['bed_no']})"
            if p_key not in grouped_dict:
                grouped_dict[p_key] = {"group_key": p_key, "ward": r["ward"], "total_events": 0, "calls": 0, "prescriptions": 0}
            grouped_dict[p_key]["total_events"] += 1
            if r["action_type"] in ["CALL_ACKNOWLEDGED", "CALL_RESOLVED"]: grouped_dict[p_key]["calls"] += 1
            if "PRESCRIPTION" in r["comment"].upper(): grouped_dict[p_key]["prescriptions"] += 1
        processed_rows = list(grouped_dict.values())

    elif group_by == "BY_WARD":
        grouped_dict = {}
        for r in raw_rows:
            w_key = r["ward"] or "General Ward"
            if w_key not in grouped_dict:
                grouped_dict[w_key] = {"group_key": w_key, "total_events": 0, "calls": 0, "prescriptions": 0, "transfers": 0}
            grouped_dict[w_key]["total_events"] += 1
            if r["action_type"] in ["CALL_ACKNOWLEDGED", "CALL_RESOLVED"]: grouped_dict[w_key]["calls"] += 1
            if "PRESCRIPTION" in r["comment"].upper(): grouped_dict[w_key]["prescriptions"] += 1
            if r["action_type"] in ["PATIENT_TRANSFERRED", "STATUS_CHANGE"]: grouped_dict[w_key]["transfers"] += 1
        processed_rows = list(grouped_dict.values())

    elif group_by == "BY_STAFF":
        grouped_dict = {}
        for r in raw_rows:
            s_key = f"{r['staff_name']} [{r['staff_role']}]"
            if s_key not in grouped_dict:
                grouped_dict[s_key] = {"group_key": s_key, "staff_name": r["staff_name"], "staff_role": r["staff_role"], "total_events": 0, "calls": 0, "prescriptions": 0}
            grouped_dict[s_key]["total_events"] += 1
            if r["action_type"] in ["CALL_ACKNOWLEDGED", "CALL_RESOLVED"]: grouped_dict[s_key]["calls"] += 1
            if "PRESCRIPTION" in r["comment"].upper(): grouped_dict[s_key]["prescriptions"] += 1
        processed_rows = list(grouped_dict.values())

    else:
        processed_rows = raw_rows

    return {"summary": summary, "rows": processed_rows, "group_by": group_by, "raw_rows": raw_rows}

@app.route("/api/reports/query", methods=["GET"])
def api_query_report():
    try:
        report_data = query_report_logs(request.args)
        return jsonify({"status": "success", "data": report_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/reports/download", methods=["GET"])
def api_download_report():
    report_data = query_report_logs(request.args)
    group_by = report_data["group_by"]
    rows = report_data["rows"]

    output = io.StringIO()
    writer = csv.writer(output)

    if group_by == "BY_DATE":
        writer.writerow(["Date", "Total Service Events", "Calls Acknowledged", "Prescriptions Issued", "Transfers & Discharges"])
        for r in rows:
            writer.writerow([r["group_key"], r["total_events"], r["calls"], r["prescriptions"], r["transfers"]])

    elif group_by == "BY_PATIENT":
        writer.writerow(["Patient Identifier", "Ward / Dept", "Total Service Events", "Calls Cleared", "Prescriptions Issued"])
        for r in rows:
            writer.writerow([r["group_key"], r["ward"], r["total_events"], r["calls"], r["prescriptions"]])

    elif group_by == "BY_WARD":
        writer.writerow(["Ward / Department", "Total Service Events", "Calls Cleared", "Prescriptions Issued", "Transfers"])
        for r in rows:
            writer.writerow([r["group_key"], r["total_events"], r["calls"], r["prescriptions"], r["transfers"]])

    elif group_by == "BY_STAFF":
        writer.writerow(["Staff Member & Role", "Staff Name", "Staff Role", "Total Service Actions", "Calls Cleared", "Prescriptions Issued"])
        for r in rows:
            writer.writerow([r["group_key"], r["staff_name"], r["staff_role"], r["total_events"], r["calls"], r["prescriptions"]])

    else:
        writer.writerow(["Log ID", "Timestamp", "Patient ID", "Patient Name", "Ward", "Room", "Bed", "Staff Name", "Staff Role", "Action Type", "Comment / Note"])
        for r in rows:
            writer.writerow([r["id"], r["timestamp"], r["patient_id"], r["patient_name"], r["ward"], r["room_no"], r["bed_no"], r["staff_name"], r["staff_role"], r["action_type"], r["comment"]])

    output.seek(0)
    filename = f"Hospital_Service_Report_{group_by}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

# Soft Bedside Unit MAC Allocation & Patient Details API
@app.route("/api/bedside/patient_info", methods=["GET"])
def api_bedside_patient_info():
    mac = request.args.get("mac", "").strip()
    room_no = request.args.get("room_no", "").strip()
    bed_no = request.args.get("bed_no", "").strip()
    patient_id = request.args.get("patient_id", "").strip()

    if USE_MONGO:
        patients_col = mongo_db["patients"]
        query = {}
        if patient_id:
            query["id"] = int(patient_id)
        elif room_no and bed_no:
            query["room_no"] = room_no
            query["bed_no"] = bed_no
            query["status"] = {"$nin": ["DISCHARGED", "DECEASED"]}
        elif mac:
            query["esp_mac"] = mac
        
        patient = patients_col.find_one(query) if query else None
        if patient:
            patient.pop("_id", None)
            return jsonify({"status": "success", "patient": patient})
    else:
        conn = get_sqlite_db()
        cursor = conn.cursor()
        row = None
        if patient_id:
            cursor.execute("SELECT *, COALESCE(id_card_type, 'Aadhar Card') as id_card_type, COALESCE(id_card_no, aadhar_no, 'N/A') as id_card_no, COALESCE(aadhar_no, 'N/A') as aadhar_no, COALESCE(mobile_no, 'N/A') as mobile_no, COALESCE(alt_mobile_no, 'N/A') as alt_mobile_no, COALESCE(emergency_contact_name, 'N/A') as emergency_contact_name, COALESCE(cause_of_admission, 'General Checkup') as cause_of_admission, COALESCE(admitted_by, 'Reception Desk') as admitted_by, COALESCE(referred_by, 'Self / Walk-in') as referred_by, COALESCE(admission_notes, 'N/A') as admission_notes FROM patients WHERE id = ?", (patient_id,))
            row = cursor.fetchone()
        elif room_no and bed_no:
            cursor.execute("SELECT *, COALESCE(id_card_type, 'Aadhar Card') as id_card_type, COALESCE(id_card_no, aadhar_no, 'N/A') as id_card_no, COALESCE(aadhar_no, 'N/A') as aadhar_no, COALESCE(mobile_no, 'N/A') as mobile_no, COALESCE(alt_mobile_no, 'N/A') as alt_mobile_no, COALESCE(emergency_contact_name, 'N/A') as emergency_contact_name, COALESCE(cause_of_admission, 'General Checkup') as cause_of_admission, COALESCE(admitted_by, 'Reception Desk') as admitted_by, COALESCE(referred_by, 'Self / Walk-in') as referred_by, COALESCE(admission_notes, 'N/A') as admission_notes FROM patients WHERE room_no = ? AND bed_no = ? AND status NOT IN ('DISCHARGED', 'DECEASED')", (room_no, bed_no))
            row = cursor.fetchone()
            if not row:
                cursor.execute("SELECT *, COALESCE(id_card_type, 'Aadhar Card') as id_card_type, COALESCE(id_card_no, aadhar_no, 'N/A') as id_card_no, COALESCE(aadhar_no, 'N/A') as aadhar_no, COALESCE(mobile_no, 'N/A') as mobile_no, COALESCE(alt_mobile_no, 'N/A') as alt_mobile_no, COALESCE(emergency_contact_name, 'N/A') as emergency_contact_name, COALESCE(cause_of_admission, 'General Checkup') as cause_of_admission, COALESCE(admitted_by, 'Reception Desk') as admitted_by, COALESCE(referred_by, 'Self / Walk-in') as referred_by, COALESCE(admission_notes, 'N/A') as admission_notes FROM patients WHERE room_no = ? AND bed_no = ? ORDER BY id DESC LIMIT 1", (room_no, bed_no))
                row = cursor.fetchone()
        elif mac:
            cursor.execute("SELECT *, COALESCE(id_card_type, 'Aadhar Card') as id_card_type, COALESCE(id_card_no, aadhar_no, 'N/A') as id_card_no, COALESCE(aadhar_no, 'N/A') as aadhar_no, COALESCE(mobile_no, 'N/A') as mobile_no, COALESCE(alt_mobile_no, 'N/A') as alt_mobile_no, COALESCE(emergency_contact_name, 'N/A') as emergency_contact_name, COALESCE(cause_of_admission, 'General Checkup') as cause_of_admission, COALESCE(admitted_by, 'Reception Desk') as admitted_by, COALESCE(referred_by, 'Self / Walk-in') as referred_by, COALESCE(admission_notes, 'N/A') as admission_notes FROM patients WHERE esp_mac = ?", (mac,))
            row = cursor.fetchone()
        else:
            cursor.execute("SELECT *, COALESCE(id_card_type, 'Aadhar Card') as id_card_type, COALESCE(id_card_no, aadhar_no, 'N/A') as id_card_no, COALESCE(aadhar_no, 'N/A') as aadhar_no, COALESCE(mobile_no, 'N/A') as mobile_no, COALESCE(alt_mobile_no, 'N/A') as alt_mobile_no, COALESCE(emergency_contact_name, 'N/A') as emergency_contact_name, COALESCE(cause_of_admission, 'General Checkup') as cause_of_admission, COALESCE(admitted_by, 'Reception Desk') as admitted_by, COALESCE(referred_by, 'Self / Walk-in') as referred_by, COALESCE(admission_notes, 'N/A') as admission_notes FROM patients LIMIT 1")
            row = cursor.fetchone()
        
        if 'row' not in locals() or not row:
            row = cursor.fetchone()
        conn.close()
        if row:
            patient = dict(row)
            return jsonify({"status": "success", "patient": patient})

    return jsonify({"status": "error", "message": "Patient not found for unit"}), 404


@app.route("/api/bedside/allocate_mac", methods=["POST"])
def api_bedside_allocate_mac():
    try:
        data = request.get_json(force=True)
        password = data.get("password", "").strip()
        mac = data.get("mac_address", "").strip()
        room_no = data.get("room_no", "").strip()
        bed_no = data.get("bed_no", "").strip()
        patient_id = data.get("patient_id")

        if not password:
            return jsonify({"status": "error", "message": "Staff password required to allocate MAC ID"}), 401
        
        if not mac or (not patient_id and (not room_no or not bed_no)):
            return jsonify({"status": "error", "message": "MAC address and Room/Bed or Patient ID required"}), 400

        # Password authentication
        auth_success = False
        staff_name = "Authorized Staff"
        staff_role = "Nurse"

        if password in ["admin123", "nurse123", "doc123", "1234"]:
            auth_success = True
            staff_name = "Admin / Nurse"
        else:
            if USE_MONGO:
                user = mongo_db["users"].find_one({"password": password})
                if user:
                    auth_success = True
                    staff_name = user.get("full_name", "Staff")
                    staff_role = user.get("role", "Nurse")
            else:
                conn = get_sqlite_db()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE password = ?", (password,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    auth_success = True
                    staff_name = row["full_name"]
                    staff_role = row["role"]

        if not auth_success:
            return jsonify({"status": "error", "message": "Access Denied: Invalid Staff Password"}), 401

        dev_id = f"ESP_MAC_{mac.replace(':', '')}"
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if USE_MONGO:
            patients_col = mongo_db["patients"]
            logs_col = mongo_db["action_logs"]

            if patient_id:
                patient = patients_col.find_one({"id": int(patient_id)})
            else:
                patient = patients_col.find_one({"room_no": room_no, "bed_no": bed_no, "status": {"$nin": ["DISCHARGED", "DECEASED"]}})

            if not patient:
                return jsonify({"status": "error", "message": "Specified patient/bed not found"}), 404

            patients_col.update_one({"id": patient["id"]}, {"$set": {"esp_mac": mac, "esp_device_id": dev_id}})
            
            logs_col.insert_one({
                "patient_id": patient["id"],
                "staff_name": staff_name,
                "staff_role": staff_role,
                "comment": f"MAC ID '{mac}' allocated to Bedside Unit ({patient['patient_name']}, Room {patient['room_no']}, Bed {patient['bed_no']}) by {staff_name}.",
                "action_type": "NOTE",
                "timestamp": now_str
            })

            updated_patient = patients_col.find_one({"id": patient["id"]})
            updated_patient.pop("_id", None)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            if patient_id:
                cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
            else:
                cursor.execute("SELECT * FROM patients WHERE room_no = ? AND bed_no = ? AND status NOT IN ('DISCHARGED', 'DECEASED')", (room_no, bed_no))
            
            p_row = cursor.fetchone()
            if not p_row:
                conn.close()
                return jsonify({"status": "error", "message": "Specified patient/bed not found"}), 404

            patient = dict(p_row)
            cursor.execute("UPDATE patients SET esp_mac = ?, esp_device_id = ? WHERE id = ?", (mac, dev_id, patient["id"]))
            cursor.execute('''
                INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                VALUES (?, ?, ?, ?, 'NOTE', ?)
            ''', (patient["id"], staff_name, staff_role, f"MAC ID '{mac}' allocated to Bedside Unit ({patient['patient_name']}, Room {patient['room_no']}, Bed {patient['bed_no']}) by {staff_name}.", now_str))

            conn.commit()
            cursor.execute("SELECT * FROM patients WHERE id = ?", (patient["id"],))
            updated_patient = dict(cursor.fetchone())
            conn.close()

        socketio.emit("patient_updated", updated_patient)
        return jsonify({"status": "success", "message": f"MAC ID {mac} successfully allocated!", "patient": updated_patient})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/helper")
def helper_view():
    return render_template("helper.html")

# General Helper / Attendee Call APIs
@app.route("/api/helper/dispatch", methods=["POST"])
def api_helper_dispatch():
    try:
        data = request.get_json(force=True)
        user = session.get("user")
        patient_id = data.get("patient_id")
        room_no = data.get("room_no")
        bed_no = data.get("bed_no")
        notes = data.get("instructions") or data.get("notes", "General assistance requested.")
        assigned_by = (user.get("full_name") if user else None) or data.get("assigned_by", "Doctor / Nurse")
        assigned_role = (user.get("role") if user else None) or data.get("assigned_role", "Doctor")

        if not patient_id and (not room_no or not bed_no):
            return jsonify({"status": "error", "message": "Patient ID or Room/Bed required"}), 400

        help_doc = trigger_general_help_call(
            room_no=room_no,
            bed_no=bed_no,
            call_type="STAFF_DISPATCH",
            notes=notes,
            assigned_by=assigned_by,
            assigned_role=assigned_role,
            patient_id=patient_id
        )
        return jsonify({"status": "success", "call": help_doc}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/helper/calls", methods=["GET"])
def api_get_helper_calls():
    include_resolved = request.args.get("include_resolved", "false").lower() == "true"
    
    if USE_MONGO:
        help_col = mongo_db["general_help_calls"]
        query = {} if include_resolved else {"status": {"$ne": "RESOLVED"}}
        calls = list(help_col.find(query).sort("called_at", -1))
        for c in calls:
            c["_id"] = str(c["_id"])
        return jsonify(calls)
    else:
        conn = get_sqlite_db()
        cursor = conn.cursor()
        where_clause = "" if include_resolved else "WHERE g.status != 'RESOLVED'"
        cursor.execute(f'''
            SELECT g.*, COALESCE(p.patient_name, 'Patient (Room ' || g.room_no || '-' || g.bed_no || ')') as patient_name
            FROM general_help_calls g
            LEFT JOIN patients p ON g.patient_id = p.id
            {where_clause}
            ORDER BY g.id DESC
        ''')
        calls = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(calls)

@app.route("/api/helper/call/acknowledge", methods=["POST"])
def api_acknowledge_helper_call():
    try:
        data = request.get_json(force=True)
        call_id = int(data.get("call_id"))
        user = session.get("user")
        staff_name = (user.get("full_name") if user else None) or data.get("staff_name", "Helper Mark")
        staff_role = (user.get("role") if user else None) or data.get("staff_role", "General Helper")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if USE_MONGO:
            help_col = mongo_db["general_help_calls"]
            help_col.update_one({"id": call_id}, {"$set": {"status": "ACKNOWLEDGED", "acknowledged_at": now_str, "acknowledged_by": f"{staff_name} ({staff_role})"}} )
            call = help_col.find_one({"id": call_id})
            if call:
                call["_id"] = str(call["_id"])
                if call.get("patient_id"):
                    mongo_db["action_logs"].insert_one({
                        "patient_id": call["patient_id"],
                        "staff_name": staff_name,
                        "staff_role": staff_role,
                        "comment": f"General Help task acknowledged by {staff_name} [{staff_role}].",
                        "action_type": "CALL_ACKNOWLEDGED",
                        "timestamp": now_str
                    })
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE general_help_calls SET status = 'ACKNOWLEDGED', acknowledged_at = ?, acknowledged_by = ? WHERE id = ?", (now_str, f"{staff_name} ({staff_role})", call_id))
            cursor.execute("SELECT g.*, COALESCE(p.patient_name, 'Patient (Room ' || g.room_no || '-' || g.bed_no || ')') as patient_name FROM general_help_calls g LEFT JOIN patients p ON g.patient_id = p.id WHERE g.id = ?", (call_id,))
            row = cursor.fetchone()
            call = dict(row) if row else None
            if call and call.get("patient_id"):
                cursor.execute("INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp) VALUES (?, ?, ?, ?, 'CALL_ACKNOWLEDGED', ?)", (call["patient_id"], staff_name, staff_role, f"General Help task acknowledged by {staff_name} [{staff_role}].", now_str))
            conn.commit()
            conn.close()

        if call:
            broadcast_led_state(call.get("room_no"), call.get("bed_no"), "BLINKING", "IN_PROGRESS")
        socketio.emit("general_help_updated", call)
        return jsonify({"status": "success", "call": call}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/helper/call/resolve", methods=["POST"])
def api_resolve_helper_call():
    try:
        data = request.get_json(force=True)
        call_id = int(data.get("call_id"))
        notes = data.get("resolution_notes") or data.get("notes", "Task completed cleanly.")
        user = session.get("user")
        staff_name = (user.get("full_name") if user else None) or data.get("staff_name", "Helper Mark")
        staff_role = (user.get("role") if user else None) or data.get("staff_role", "General Helper")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if USE_MONGO:
            help_col = mongo_db["general_help_calls"]
            calls_col = mongo_db["nurse_calls"]
            patients_col = mongo_db["patients"]
            logs_col = mongo_db["action_logs"]
            req_col = mongo_db["service_requests"]

            call = help_col.find_one({"id": call_id})
            if not call:
                return jsonify({"status": "error", "message": "Call not found"}), 404

            help_col.update_one(
                {"id": call_id},
                {"$set": {"status": "RESOLVED", "resolved_at": now_str, "resolved_by": f"{staff_name} ({staff_role})", "notes": notes}}
            )

            p_id = call.get("patient_id")
            called_at = str(call.get("called_at", now_str))
            elapsed_str = format_elapsed_time(called_at, now_str)
            task_desc = call.get("notes") or "General Help Call"

            if p_id:
                logs_col.insert_one({
                    "patient_id": p_id,
                    "staff_name": staff_name,
                    "staff_role": staff_role,
                    "comment": f"SLA TASK SOLVED: '{task_desc}' | Called: {called_at} -> Solved: {now_str} (Duration: {elapsed_str}) by {staff_name} [{staff_role}]. Action Taken: {notes}",
                    "action_type": "CALL_RESOLVED",
                    "timestamp": now_str
                })

                # Sync matching pending service requests
                req_col.update_many(
                    {"patient_id": p_id, "status": "PENDING"},
                    {"$set": {"status": "SERVED", "served_at": now_str, "served_by": f"{staff_name} [{staff_role}]", "served_notes": notes}}
                )

                # Re-evaluate patient status
                rem_calls = fetch_active_calls_for_patients([p_id]).get(p_id, [])
                new_p_status = rem_calls[0]["call_type"] if rem_calls else "NORMAL"
                patients_col.update_one({"id": p_id}, {"$set": {"status": new_p_status}})

            call = help_col.find_one({"id": call_id})
            call["_id"] = str(call["_id"])

        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()

            cursor.execute("SELECT g.*, COALESCE(p.patient_name, 'Patient (Room ' || g.room_no || '-' || g.bed_no || ')') as patient_name FROM general_help_calls g LEFT JOIN patients p ON g.patient_id = p.id WHERE g.id = ?", (call_id,))
            c_row = cursor.fetchone()
            if not c_row:
                conn.close()
                return jsonify({"status": "error", "message": "Call not found"}), 404

            call_dict = dict(c_row)
            p_id = call_dict.get("patient_id")
            called_at = str(call_dict.get("called_at") or now_str)
            elapsed_str = format_elapsed_time(called_at, now_str)
            task_desc = call_dict.get("notes") or "General Help Call"

            cursor.execute("UPDATE general_help_calls SET status = 'RESOLVED', resolved_at = ?, resolved_by = ?, notes = COALESCE(notes || ' | Action: ' || ?, ?) WHERE id = ?", (now_str, f"{staff_name} ({staff_role})", notes, notes, call_id))

            if p_id:
                cursor.execute("INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp) VALUES (?, ?, ?, ?, 'CALL_RESOLVED', ?)", (p_id, staff_name, staff_role, f"SLA TASK SOLVED: '{task_desc}' | Called: {called_at} -> Solved: {now_str} (Duration: {elapsed_str}) by {staff_name} [{staff_role}]. Action Taken: {notes}", now_str))

                # Sync matching pending service requests
                cursor.execute("UPDATE service_requests SET status = 'SERVED', served_at = ?, served_by = ?, served_notes = ? WHERE patient_id = ? AND status IN ('PENDING', 'IN_PROCESS')", (now_str, f"{staff_name} [{staff_role}]", notes, p_id))

                # Re-evaluate remaining active calls for patient
                rem_calls = fetch_active_calls_for_patients([p_id], conn=conn).get(p_id, [])
                new_p_status = rem_calls[0]["call_type"] if rem_calls else "NORMAL"
                cursor.execute("UPDATE patients SET status = ? WHERE id = ?", (new_p_status, p_id))

            conn.commit()
            cursor.execute("SELECT g.*, COALESCE(p.patient_name, 'Patient (Room ' || g.room_no || '-' || g.bed_no || ')') as patient_name FROM general_help_calls g LEFT JOIN patients p ON g.patient_id = p.id WHERE g.id = ?", (call_id,))
            call = dict(cursor.fetchone())
            conn.close()

        if call:
            broadcast_led_state(call.get("room_no"), call.get("bed_no"), "OFF", "NORMAL")
        socketio.emit("general_help_updated", call)
        if p_id:
            socketio.emit("call_updated", {"patient_id": p_id, "status": "RESOLVED"})
        return jsonify({"status": "success", "call": call}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def query_helper_report(args):
    start_date = args.get("start_date", "").strip()
    end_date = args.get("end_date", "").strip()
    ward = args.get("ward", "ALL").strip()
    status_filter = args.get("status", "ALL").strip()
    chronology = args.get("chronology", "DESC").upper()
    order_sql = "ASC" if chronology == "ASC" else "DESC"

    if USE_MONGO:
        help_col = mongo_db["general_help_calls"]
        query = {}
        if status_filter != "ALL": query["status"] = status_filter
        if ward != "ALL": query["ward"] = ward
        if start_date: query["called_at"] = {"$gte": f"{start_date} 00:00:00"}
        if end_date:
            if "called_at" in query: query["called_at"]["$lte"] = f"{end_date} 23:59:59"
            else: query["called_at"] = {"$lte": f"{end_date} 23:59:59"}

        mongo_sort = 1 if chronology == "ASC" else -1
        logs = list(help_col.find(query).sort("called_at", mongo_sort))
        for l in logs: l["_id"] = str(l["_id"])
        rows = logs
    else:
        conn = get_sqlite_db()
        cursor = conn.cursor()
        where_conds = []
        params = []
        if start_date:
            where_conds.append("g.called_at >= ?")
            params.append(f"{start_date} 00:00:00")
        if end_date:
            where_conds.append("g.called_at <= ?")
            params.append(f"{end_date} 23:59:59")
        if ward != "ALL":
            where_conds.append("LOWER(g.ward) = LOWER(?)")
            params.append(ward)
        if status_filter != "ALL":
            where_conds.append("g.status = ?")
            params.append(status_filter)

        where_clause = "WHERE " + " AND ".join(where_conds) if where_conds else ""
        cursor.execute(f'''
            SELECT g.*, COALESCE(p.patient_name, 'Patient (Room ' || g.room_no || '-' || g.bed_no || ')') as patient_name
            FROM general_help_calls g
            LEFT JOIN patients p ON g.patient_id = p.id
            {where_clause}
            ORDER BY g.id {order_sql}
        ''', params)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

    summary = {
        "total_calls": len(rows),
        "bedside_calls": sum(1 for r in rows if r.get("call_type") == "BEDSIDE_CALL"),
        "staff_dispatches": sum(1 for r in rows if r.get("call_type") == "STAFF_DISPATCH"),
        "resolved_calls": sum(1 for r in rows if r.get("status") == "RESOLVED")
    }

    return {"summary": summary, "rows": rows}

@app.route("/api/helper/reports/query", methods=["GET"])
def api_query_helper_report():
    try:
        data = query_helper_report(request.args)
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/helper/reports/download", methods=["GET"])
def api_download_helper_report():
    report_data = query_helper_report(request.args)
    rows = report_data["rows"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Call ID", "Called At", "Patient Name", "Ward", "Room", "Bed", "Call Origin / Type", "Assigned By", "Staff Role", "Call Status", "Attended By", "Resolution / Instructions"])

    for r in rows:
        writer.writerow([
            r.get("id"),
            r.get("called_at"),
            r.get("patient_name"),
            r.get("ward"),
            r.get("room_no"),
            r.get("bed_no"),
            "Bedside Call" if r.get("call_type") == "BEDSIDE_CALL" else "Staff Dispatch",
            r.get("assigned_by"),
            r.get("assigned_role"),
            r.get("status"),
            r.get("acknowledged_by") or "N/A",
            r.get("notes") or "N/A"
        ])

    output.seek(0)
    filename = f"General_Helper_Report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

# Health Condition & Multi-Recipient Service Request APIs
@app.route("/api/patient/health", methods=["POST"])
def api_update_patient_health():
    try:
        data = request.get_json(force=True)
        user = session.get("user")
        
        # Enforce role authorization: Only Doctor, Nurse, or Admin can edit health status
        staff_role = (user.get("role") if user else None) or data.get("staff_role", "")
        if not ("Doctor" in staff_role or "Nurse" in staff_role or staff_role == "Admin"):
            return jsonify({"status": "error", "message": "Access denied: Only Doctors and Nurses are authorized to edit Patient Health Status."}), 403

        patient_id = int(data.get("patient_id"))
        health_condition = int(data.get("health_condition", 100))
        health_condition = max(0, min(100, health_condition))

        staff_name = (user.get("full_name") if user else None) or data.get("staff_name", "Doctor / Nurse")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        comment = f"HEALTH CONDITION UPDATED: Set to {health_condition}% by {staff_name} [{staff_role}]."

        if USE_MONGO:
            patients_col = mongo_db["patients"]
            logs_col = mongo_db["action_logs"]
            patients_col.update_one({"id": patient_id}, {"$set": {"health_condition": health_condition}})
            logs_col.insert_one({
                "patient_id": patient_id,
                "staff_name": staff_name,
                "staff_role": staff_role,
                "comment": comment,
                "action_type": "HEALTH_UPDATE",
                "timestamp": now_str
            })
            updated_patient = patients_col.find_one({"id": patient_id})
            updated_patient.pop("_id", None)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE patients SET health_condition = ? WHERE id = ?", (health_condition, patient_id))
            cursor.execute('''
                INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                VALUES (?, ?, ?, ?, 'HEALTH_UPDATE', ?)
            ''', (patient_id, staff_name, staff_role, comment, now_str))
            conn.commit()
            cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
            updated_patient = dict(cursor.fetchone())
            conn.close()

        socketio.emit("patient_health_updated", {"patient_id": patient_id, "health_condition": health_condition})
        socketio.emit("patient_updated", updated_patient)
        return jsonify({"status": "success", "patient_id": patient_id, "health_condition": health_condition, "patient": updated_patient}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/service_request/create", methods=["POST"])
def api_create_service_request():
    try:
        data = request.get_json(force=True)
        patient_id = data.get("patient_id")
        room_no = data.get("room_no")
        bed_no = data.get("bed_no")
        ward = data.get("ward")

        if patient_id:
            patient_id = int(patient_id)
            if not room_no or not bed_no:
                if USE_MONGO:
                    p_doc = mongo_db["patients"].find_one({"id": patient_id})
                    if p_doc:
                        room_no = room_no or p_doc.get("room_no")
                        bed_no = bed_no or p_doc.get("bed_no")
                        ward = ward or p_doc.get("ward", "General Ward")
                else:
                    conn = get_sqlite_db()
                    cursor = conn.cursor()
                    cursor.execute("SELECT room_no, bed_no, ward FROM patients WHERE id = ?", (patient_id,))
                    p_row = cursor.fetchone()
                    if p_row:
                        room_no = room_no or p_row["room_no"]
                        bed_no = bed_no or p_row["bed_no"]
                        ward = ward or (p_row["ward"] if "ward" in p_row.keys() else "General Ward")
                    conn.close()

        ward = ward or "General Ward"
        target_roles = data.get("target_roles", [])
        instructions = data.get("instructions") or data.get("comments", "Service request created")
        target_minutes = int(data.get("target_minutes", 15))

        user = session.get("user")
        requested_by = (user.get("full_name") if user else None) or data.get("requested_by", "Doctor / Nurse")
        requested_role = (user.get("role") if user else None) or data.get("requested_role", "Doctor")

        if not target_roles or not isinstance(target_roles, list):
            return jsonify({"status": "error", "message": "At least one target role must be selected"}), 400

        now_dt = datetime.datetime.now()
        due_by_dt = now_dt + datetime.timedelta(minutes=target_minutes)
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        due_by_str = due_by_dt.strftime("%Y-%m-%d %H:%M:%S")
        target_roles_json = json.dumps(target_roles)

        if USE_MONGO:
            req_col = mongo_db["service_requests"]
            logs_col = mongo_db["action_logs"]
            req_id = req_col.count_documents({}) + 1
            req_doc = {
                "id": req_id,
                "patient_id": patient_id,
                "room_no": room_no,
                "bed_no": bed_no,
                "ward": ward,
                "requested_by": requested_by,
                "requested_role": requested_role,
                "target_roles": target_roles,
                "instructions": instructions,
                "target_minutes": target_minutes,
                "due_by_time": due_by_str,
                "status": "PENDING",
                "created_at": now_str,
                "served_at": None,
                "served_by": None,
                "served_notes": None
            }
            req_col.insert_one(req_doc)
            req_doc.pop("_id", None)
            if patient_id:
                logs_col.insert_one({
                    "patient_id": patient_id,
                    "staff_name": requested_by,
                    "staff_role": requested_role,
                    "comment": f"SERVICE REQUEST DISPATCHED to [{', '.join(target_roles)}] (SLA: {target_minutes}m): {instructions}",
                    "action_type": "SERVICE_REQUEST",
                    "timestamp": now_str
                })
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO service_requests (patient_id, room_no, bed_no, ward, requested_by, requested_role, target_roles, instructions, target_minutes, due_by_time, status, created_at, sla_tracking_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
            ''', (patient_id, room_no, bed_no, ward, requested_by, requested_role, target_roles_json, instructions, target_minutes, due_by_str, now_str))
            req_id = cursor.lastrowid

            if patient_id:
                cursor.execute('''
                    INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp)
                    VALUES (?, ?, ?, ?, 'SERVICE_REQUEST', ?)
                ''', (patient_id, requested_by, requested_role, f"SERVICE REQUEST DISPATCHED to [{', '.join(target_roles)}] (SLA: {target_minutes}m): {instructions}", now_str))

            conn.commit()
            cursor.execute("SELECT * FROM service_requests WHERE id = ?", (req_id,))
            req_row = cursor.fetchone()
            req_doc = dict(req_row)
            req_doc["target_roles"] = json.loads(req_doc["target_roles"])
            conn.close()

        if "General Helper" in target_roles:
            trigger_general_help_call(room_no=room_no, bed_no=bed_no, call_type="STAFF_DISPATCH", notes=f"[SLA: {target_minutes}m] {instructions}", patient_id=patient_id, assigned_by=requested_by, assigned_role=requested_role)

        socketio.emit("service_request_created", req_doc)
        return jsonify({"status": "success", "service_request": req_doc}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/service_requests", methods=["GET"])
def api_get_service_requests():
    try:
        patient_id = request.args.get("patient_id")
        room_no = request.args.get("room_no")
        bed_no = request.args.get("bed_no")
        role = request.args.get("role")
        status = request.args.get("status", "PENDING")

        now_dt = datetime.datetime.now()

        if USE_MONGO:
            req_col = mongo_db["service_requests"]
            query = {}
            if status != "ALL":
                query["status"] = status
            if patient_id:
                query["patient_id"] = int(patient_id)
            if room_no:
                query["room_no"] = room_no
            if bed_no:
                query["bed_no"] = bed_no
            if role:
                query["target_roles"] = role
            items = list(req_col.find(query).sort("id", -1))
            for item in items:
                item.pop("_id", None)
                if item.get("due_by_time"):
                    try:
                        due_dt = datetime.datetime.strptime(item["due_by_time"], "%Y-%m-%d %H:%M:%S")
                        item["remaining_seconds"] = int((due_dt - now_dt).total_seconds())
                    except Exception:
                        item["remaining_seconds"] = 0
                else:
                    item["remaining_seconds"] = 0
            return jsonify(items)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            conditions = []
            params = []
            if status != "ALL":
                conditions.append("status = ?")
                params.append(status)
            if patient_id:
                conditions.append("patient_id = ?")
                params.append(patient_id)
            if room_no:
                conditions.append("room_no = ?")
                params.append(room_no)
            if bed_no:
                conditions.append("bed_no = ?")
                params.append(bed_no)

            where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            cursor.execute(f"SELECT * FROM service_requests {where_sql} ORDER BY id DESC", params)
            rows = cursor.fetchall()
            items = []
            for row in rows:
                item = dict(row)
                try:
                    item["target_roles"] = json.loads(item["target_roles"])
                except Exception:
                    item["target_roles"] = [item["target_roles"]]

                if role and role not in item["target_roles"]:
                    continue

                if item.get("due_by_time"):
                    try:
                        due_dt = datetime.datetime.strptime(item["due_by_time"], "%Y-%m-%d %H:%M:%S")
                        item["remaining_seconds"] = int((due_dt - now_dt).total_seconds())
                    except Exception:
                        item["remaining_seconds"] = 0
                else:
                    item["remaining_seconds"] = 0
                items.append(item)
            conn.close()
            return jsonify(items)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/service_request/serve", methods=["POST"])
def api_serve_service_request():
    try:
        data = request.get_json(force=True)
        request_id = data.get("request_id")
        user = session.get("user")
        staff_role = (user.get("role") if user else None) or data.get("staff_role", "Staff")
        served_by = (user.get("full_name") if user else None) or data.get("served_by", "Staff")
        served_notes = data.get("served_notes") or data.get("notes", "Served and completed.")
        
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if USE_MONGO:
            req_doc = mongo_db["service_requests"].find_one({"id": request_id})
        else:
            conn = get_sqlite_db()
            cur_chk = conn.cursor()
            cur_chk.execute("SELECT * FROM service_requests WHERE id = ?", (request_id,))
            r_chk = cur_chk.fetchone()
            if r_chk: req_doc = dict(r_chk)
            else: req_doc = None
            
        if not req_doc:
            return jsonify({"status": "error", "message": "Service request not found"}), 404
            
        target_roles = req_doc.get("target_roles", [])
        if isinstance(target_roles, str) and target_roles.startswith("["):
            import json
            target_roles = json.loads(target_roles)
        elif isinstance(target_roles, str):
            target_roles = [target_roles]
            
        solved_by_roles = req_doc.get("solved_by_roles", [])
        if isinstance(solved_by_roles, str):
            import json
            try:
                solved_by_roles = json.loads(solved_by_roles)
            except:
                solved_by_roles = []
                
        is_doc = "Doctor" in staff_role
        is_nurse = "Nurse" in staff_role
        is_helper = "Helper" in staff_role
        
        can_serve = False
        matched_role = None
        for tr in target_roles:
            tr_lower = str(tr).lower()
            if "doctor" in tr_lower and is_doc: 
                can_serve = True
                matched_role = tr
            if "nurse" in tr_lower and is_nurse: 
                can_serve = True
                matched_role = tr
            if "helper" in tr_lower and is_helper: 
                can_serve = True
                matched_role = tr
                
        is_admin = (staff_role == "Admin")
        is_creator = (served_by == req_doc.get("requested_by"))
        
        if is_admin or is_creator:
            can_serve = True

        if not can_serve:
            return jsonify({"status": "error", "message": f"Action restricted: Your role ({staff_role}) is not assigned to this service request"}), 403
            
        if matched_role and matched_role not in solved_by_roles:
            solved_by_roles.append(matched_role)
            
        pending_roles = [r for r in target_roles if r not in solved_by_roles]
        is_fully_solved = len(pending_roles) == 0
        
        # Override if admin or creator is forcefully resolving it
        if is_admin or is_creator:
            is_fully_solved = True
            solved_by_roles = list(target_roles) # Mark all required roles as solved
            pending_roles = []
            
        new_status = "SERVED" if is_fully_solved else "IN_PROCESS"
        
        created_at = str(req_doc.get("created_at") or now_str)
        target_minutes = int(req_doc.get("target_minutes") or 15)
        elapsed_str = format_elapsed_time(created_at, now_str)
        
        sla_tag = ""
        try:
            c_dt = datetime.datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
            n_dt = datetime.datetime.strptime(now_str, "%Y-%m-%d %H:%M:%S")
            if (n_dt - c_dt).total_seconds() > target_minutes * 60:
                sla_tag = "[SLA BREACHED]"
            else:
                sla_tag = "[SLA MET]"
        except:
            pass
            
        instructions = req_doc.get("instructions", "")
        p_id = req_doc.get("patient_id")
        
        sla_id_str = req_doc.get("sla_tracking_id", "UNKNOWN")
        if is_fully_solved:
            comment_msg = f"SLA TASK FULLY SOLVED {sla_tag} [{sla_id_str}]: '{instructions}' (Target SLA: {target_minutes}m) | Solved in {elapsed_str} at {now_str} by {served_by} [{staff_role}]. Action Taken: {served_notes}"
        else:
            comment_msg = f"SLA TASK PARTIALLY SOLVED {sla_tag} [{sla_id_str}]: '{instructions}' | {matched_role} completed their part. Pending from: {', '.join(pending_roles)}. Action: {served_notes}"
            
        solved_roles_str = json.dumps(solved_by_roles) if not USE_MONGO else solved_by_roles
        
        if USE_MONGO:
            req_col = mongo_db["service_requests"]
            logs_col = mongo_db["action_logs"]
            
            req_col.update_one(
                {"id": request_id},
                {"$set": {"status": new_status, "served_at": now_str, "served_by": f"{served_by} ({staff_role})", "served_notes": served_notes, "solved_by_roles": solved_by_roles}}
            )
            
            if p_id:
                logs_col.insert_one({
                    "patient_id": p_id,
                    "staff_name": served_by,
                    "staff_role": staff_role,
                    "comment": comment_msg,
                    "action_type": "SERVICE_RESOLVED",
                    "timestamp": now_str
                })
                
                if is_fully_solved:
                    mongo_db["general_help_calls"].update_many(
                        {"patient_id": p_id, "status": {"$ne": "RESOLVED"}, "notes": {"$regex": "SLA"}},
                        {"$set": {"status": "RESOLVED", "resolved_at": now_str, "resolved_by": f"{served_by} ({staff_role})", "notes": served_notes}}
                    )
                    
            req_doc = req_col.find_one({"id": request_id})
            if req_doc: req_doc.pop("_id", None)
        else:
            cursor = conn.cursor()
            cursor.execute("UPDATE service_requests SET status = ?, served_at = ?, served_by = ?, served_notes = ?, solved_by_roles = ? WHERE id = ?", 
                          (new_status, now_str, f"{served_by} ({staff_role})", served_notes, solved_roles_str, request_id))
            
            if p_id:
                cursor.execute("INSERT INTO action_logs (patient_id, staff_name, staff_role, comment, action_type, timestamp) VALUES (?, ?, ?, ?, 'SERVICE_RESOLVED', ?)", 
                              (p_id, served_by, staff_role, comment_msg, now_str))
                              
                if is_fully_solved:
                    cursor.execute("UPDATE general_help_calls SET status = 'RESOLVED', resolved_at = ?, resolved_by = ?, notes = COALESCE(notes || ' | Done: ' || ?, ?) WHERE patient_id = ? AND status != 'RESOLVED'", 
                                  (now_str, f"{served_by} ({staff_role})", served_notes, served_notes, p_id))
                                  
            cursor.execute("SELECT * FROM service_requests WHERE id = ?", (request_id,))
            req_doc = dict(cursor.fetchone())
            conn.commit()
            conn.close()
            
        socketio.emit("service_request_served", req_doc)
        if p_id:
            socketio.emit("patient_updated", {"message": "Service request served/updated"})
            
        return jsonify({"status": "success", "service_request": req_doc}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/bedside/search_beds", methods=["GET"])
def api_search_beds():
    try:
        if USE_MONGO:
            patients_col = mongo_db["patients"]
            patients = list(patients_col.find({"status": {"$nin": ["DISCHARGED", "DECEASED"]}}).sort([("room_no", 1), ("bed_no", 1)]))
            result = []
            for p in patients:
                result.append({
                    "patient_id": p.get("id"),
                    "patient_name": p.get("patient_name"),
                    "ward": p.get("ward"),
                    "room_no": p.get("room_no"),
                    "bed_no": p.get("bed_no"),
                    "health_condition": p.get("health_condition", 100),
                    "status": p.get("status")
                })
            return jsonify(result)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id as patient_id, patient_name, ward, room_no, bed_no, COALESCE(health_condition, 100) as health_condition, status
                FROM patients
                WHERE status NOT IN ('DISCHARGED', 'DECEASED')
                ORDER BY room_no ASC, bed_no ASC
            ''')
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return jsonify(rows)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Notice Board & Staff Chat Box APIs
@app.route("/api/chat/send", methods=["POST"])
def api_send_chat_message():
    try:
        data = request.get_json(force=True)
        user = session.get("user")
        sender_name = (user.get("full_name") if user else None) or data.get("sender_name", "Staff")
        sender_role = (user.get("role") if user else None) or data.get("sender_role", "Doctor")

        message = data.get("message", "").strip()
        target_department = data.get("target_department", "ALL")
        target_recipient = data.get("target_recipient", "ALL")
        priority = data.get("priority", "NORMAL")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not message:
            return jsonify({"status": "error", "message": "Message text cannot be empty"}), 400

        target_type = "ALL"
        if target_recipient != "ALL":
            target_type = "USER"
        elif target_department != "ALL":
            target_type = "DEPARTMENT"

        if USE_MONGO:
            msg_col = mongo_db["notice_board_messages"]
            msg_id = msg_col.count_documents({}) + 1
            msg_doc = {
                "id": msg_id,
                "sender_name": sender_name,
                "sender_role": sender_role,
                "target_type": target_type,
                "target_department": target_department,
                "target_recipient": target_recipient,
                "message": message,
                "priority": priority,
                "created_at": now_str
            }
            msg_col.insert_one(msg_doc)
            msg_doc.pop("_id", None)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO notice_board_messages (sender_name, sender_role, target_type, target_department, target_recipient, message, priority, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (sender_name, sender_role, target_type, target_department, target_recipient, message, priority, now_str))
            msg_id = cursor.lastrowid
            conn.commit()
            cursor.execute("SELECT * FROM notice_board_messages WHERE id = ?", (msg_id,))
            msg_doc = dict(cursor.fetchone())
            conn.close()

        socketio.emit("new_chat_message", msg_doc)
        return jsonify({"status": "success", "message": msg_doc}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/chat/messages", methods=["GET"])
def api_get_chat_messages():
    try:
        department = request.args.get("department")
        recipient = request.args.get("recipient")
        limit = int(request.args.get("limit", 50))

        if USE_MONGO:
            msg_col = mongo_db["notice_board_messages"]
            query = {}
            if department and department != "ALL":
                query["$or"] = [{"target_department": "ALL"}, {"target_department": department}]
            messages = list(msg_col.find(query).sort("id", -1).limit(limit))
            for m in messages:
                m.pop("_id", None)
            return jsonify(messages)
        else:
            conn = get_sqlite_db()
            cursor = conn.cursor()
            where_sql = ""
            params = []
            if department and department != "ALL":
                where_sql = "WHERE target_department = 'ALL' OR target_department = ?"
                params.append(department)

            cursor.execute(f"SELECT * FROM notice_board_messages {where_sql} ORDER BY id DESC LIMIT ?", params + [limit])
            messages = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return jsonify(messages)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# WebSocket Event Handlers
@socketio.on("connect")
def handle_connect():
    print("[WS] Client connected to Hospital Dashboard")

@socketio.on("trigger_call")
def handle_ws_trigger_call(data):
    if isinstance(data, dict):
        room = data.get("room_no") or data.get("room")
        bed = data.get("bed_no") or data.get("bed")
        call_type = data.get("call_type", "NURSE_CALL")
        if room and bed:
            trigger_bedside_call(room, bed, call_type)

if __name__ == "__main__":
    local_ips = get_local_ips()
    print("=" * 65)
    print("[SERVER] HOSPITAL PATIENT MANAGEMENT & NURSE CALL SYSTEM RUNNING")
    print(f"[DATABASE MODE] {'MongoDB (hospital_db)' if USE_MONGO else 'SQLite (hospital.db)'}")
    print("=" * 65)
    print("Accessible across your WiFi network at:")
    for ip in local_ips:
        print(f"  --> Staff Dashboard  : http://{ip}:5000")
        print(f"  --> Soft Bedside Unit: http://{ip}:5000/bedside")
    print("=" * 65)

    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)
