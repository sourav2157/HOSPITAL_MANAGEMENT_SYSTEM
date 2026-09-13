/*
 * =====================================================================
 * ESP8266 BEDSIDE CALL UNIT FIRMWARE (NURSE CALL & DOCTOR EMERGENCY)
 * =====================================================================
 * Hardware Setup:
 *   - Button 1 (Call Nurse)  : Pin D1 (GPIO 5) -> GND (Internal Pullup)
 *   - Button 2 (Call Doctor) : Pin D2 (GPIO 4) -> GND (Internal Pullup)
 *   - Status LED             : Builtin LED (D4 / GPIO 2)
 *
 * Board: NodeMCU v1.0 or ESP8266 D1 Mini (Arduino IDE)
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>

// Configuration
const char* WIFI_SSID = "YOUR_HOSPITAL_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* SERVER_IP = "192.168.1.50"; // Replace with your Flask Server Local IP
const int   SERVER_PORT = 5000;

const char* ROOM_NO = "101";
const char* BED_NO  = "A1";

// Pin Definitions
const int BUTTON_NURSE_PIN  = 5; // D1
const int BUTTON_DOCTOR_PIN = 4; // D2
const int LED_STATUS_PIN    = 2; // D4 Builtin LED

unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 300; // ms

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_NURSE_PIN, INPUT_PULLUP);
  pinMode(BUTTON_DOCTOR_PIN, INPUT_PULLUP);
  pinMode(LED_STATUS_PIN, OUTPUT);
  digitalWrite(LED_STATUS_PIN, HIGH); // Off for active low

  Serial.println("\n[ESP8266 BEDSIDE UNIT] Initializing...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    digitalWrite(LED_STATUS_PIN, !digitalRead(LED_STATUS_PIN)); // Flash LED connecting
  }

  digitalWrite(LED_STATUS_PIN, HIGH);
  Serial.println("\n[WiFi] Connected!");
  Serial.print("[WiFi] IP Address: ");
  Serial.println(WiFi.localIP());
  Serial.print("[WiFi] MAC Address: ");
  Serial.println(WiFi.macAddress());
}

void sendBedsideCall(const char* callType) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ERROR] WiFi not connected!");
    return;
  }

  WiFiClient client;
  HTTPClient http;

  String url = "http://" + String(SERVER_IP) + ":" + String(SERVER_PORT) + "/api/bedside/call";
  Serial.print("[HTTP] Sending call to: ");
  Serial.println(url);

  http.begin(client, url);
  http.addHeader("Content-Type", "application/json");

  String deviceId = "ESP_ROOM" + String(ROOM_NO) + "_" + String(BED_NO);
  String macAddr  = WiFi.macAddress();

  String jsonPayload = "{";
  jsonPayload += "\"room_no\":\"" + String(ROOM_NO) + "\",";
  jsonPayload += "\"bed_no\":\"" + String(BED_NO) + "\",";
  jsonPayload += "\"call_type\":\"" + String(callType) + "\",";
  jsonPayload += "\"device_id\":\"" + deviceId + "\",";
  jsonPayload += "\"esp_mac\":\"" + macAddr + "\"";
  jsonPayload += "}";

  // Visual feedback: Blink LED fast
  digitalWrite(LED_STATUS_PIN, LOW);
  int httpCode = http.POST(jsonPayload);
  digitalWrite(LED_STATUS_PIN, HIGH);

  if (httpCode > 0) {
    Serial.printf("[HTTP] Success, Response Code: %d\n", httpCode);
    String payload = http.getString();
    Serial.println("[HTTP] Server Response: " + payload);
  } else {
    Serial.printf("[HTTP] Failed, Error: %s\n", http.errorToString(httpCode).c_str());
  }

  http.end();
}

void loop() {
  if (millis() - lastDebounceTime > debounceDelay) {
    // Read active LOW buttons
    if (digitalRead(BUTTON_NURSE_PIN) == LOW) {
      Serial.println("\n[BUTTON] Nurse Call Pressed!");
      sendBedsideCall("NURSE_CALL");
      lastDebounceTime = millis();
    } 
    else if (digitalRead(BUTTON_DOCTOR_PIN) == LOW) {
      Serial.println("\n[BUTTON] Doctor Emergency Call Pressed!");
      sendBedsideCall("DOCTOR_CALL");
      lastDebounceTime = millis();
    }
  }

  delay(10);
}
