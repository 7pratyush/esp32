/*
  Smart Society Gate - ESP32-CAM firmware (AI-Thinker board)

  Captures a JPEG, POSTs it to the Gateway with device credentials,
  reads the decision code (0-5) and shows it on 3 LEDs + Serial Monitor.
  Fails closed: only code 2 means ALLOWED (Section 4).

  Board:    "AI Thinker ESP32-CAM"   (ESP32 boards package by Espressif)
  Library:  ArduinoJson (by Benoit Blanchon) v7 - install from Library Manager

  Wiring (each LED through a 220 ohm resistor to GND):
    GPIO 14 -> GREEN LED   (allowed)
    GPIO  2 -> YELLOW LED  (no plate / unreadable)
    GPIO 15 -> RED LED     (denied / error)
    GPIO 13 <- IR / ultrasonic presence sensor output (active LOW)
  Set USE_PRESENCE_SENSOR to false to capture on a timer instead (testing).
*/
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "esp_camera.h"
#include "secrets.h"

// ---------------- Settings ----------------
#define USE_PRESENCE_SENSOR false
const unsigned long TIMER_INTERVAL_MS = 8000;    // timer mode capture interval
const unsigned long HTTP_TIMEOUT_MS   = 15000;   // > gateway AI_TIMEOUT_S + overhead
const unsigned long COOLDOWN_MS       = 5000;    // after each completed scan
const int MAX_UNREADABLE_RETRIES      = 3;       // FR-ESP-11

const int PIN_GREEN = 14, PIN_YELLOW = 2, PIN_RED = 15, PIN_SENSOR = 13;

// ---------------- AI-Thinker camera pins ----------------
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

const int RESULT_AUTH_ERROR = -2;  // HTTP 401
const int RESULT_INPUT_ERROR = -3; // HTTP 400/413/429
const int RESULT_SYSTEM = 5;

unsigned long lastScan = 0;

// ---------------- LEDs ----------------
void ledsOff() {
  digitalWrite(PIN_GREEN, LOW); digitalWrite(PIN_YELLOW, LOW); digitalWrite(PIN_RED, LOW);
}
void blink(int pin, int times, int onMs, int offMs) {
  for (int i = 0; i < times; i++) {
    digitalWrite(pin, HIGH); delay(onMs); digitalWrite(pin, LOW); delay(offMs);
  }
}
void indicate(int code) {
  ledsOff();
  switch (code) {
    case 0: Serial.println("-> 0 NO PLATE");          blink(PIN_YELLOW, 1, 150, 150); break;
    case 1: Serial.println("-> 1 UNREADABLE");        blink(PIN_YELLOW, 3, 200, 200); break;
    case 2: Serial.println("-> 2 ALLOWED");           digitalWrite(PIN_GREEN, HIGH); delay(3000); break;
    case 3: Serial.println("-> 3 DENIED (not registered)"); digitalWrite(PIN_RED, HIGH); delay(3000); break;
    case 4: Serial.println("-> 4 DENIED (blocked/expired)"); blink(PIN_RED, 3, 500, 300); break;
    case RESULT_AUTH_ERROR:
      Serial.println("-> AUTH ERROR: check DEVICE_ID / DEVICE_KEY");
      for (int i = 0; i < 5; i++) { digitalWrite(PIN_RED, HIGH); delay(200); digitalWrite(PIN_RED, LOW);
                                    digitalWrite(PIN_YELLOW, HIGH); delay(200); digitalWrite(PIN_YELLOW, LOW); }
      break;
    case RESULT_INPUT_ERROR: Serial.println("-> INPUT ERROR (bad/oversized image or busy)"); blink(PIN_YELLOW, 2, 80, 80); blink(PIN_RED, 1, 300, 100); break;
    default: Serial.println("-> 5 SYSTEM ERROR - gate stays closed"); blink(PIN_RED, 10, 80, 80); break;
  }
  ledsOff();
}

// ---------------- Camera ----------------
bool initCamera() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0; c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM; c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM; c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM; c.pin_vsync = VSYNC_GPIO_NUM;
  c.pin_href = HREF_GPIO_NUM; c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;     // JPEG is the required initial format
  c.frame_size = FRAMESIZE_SVGA;       // 800x600 (FR-ESP-2)
  c.jpeg_quality = 12;                 // 10-15: lower = better quality, bigger file
  c.fb_count = psramFound() ? 2 : 1;
  c.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;
  return esp_camera_init(&c) == ESP_OK;
}

// ---------------- Wi-Fi ----------------
void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.print("Connecting to Wi-Fi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500); Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? " connected, IP " + WiFi.localIP().toString()
                                               : " FAILED");
}

// ---------------- One scan ----------------
int scanOnce() {
  ensureWiFi();
  if (WiFi.status() != WL_CONNECTED) return RESULT_SYSTEM;

  camera_fb_t *fb = esp_camera_fb_get();   // discard one stale frame
  if (fb) esp_camera_fb_return(fb);
  fb = esp_camera_fb_get();
  if (!fb) { Serial.println("Camera capture failed"); return RESULT_SYSTEM; }
  Serial.printf("Captured %u bytes, uploading...\n", fb->len);

  HTTPClient http;
  http.begin(GATEWAY_URL);
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.setConnectTimeout(5000);
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Device-Id", DEVICE_ID);
  http.addHeader("X-Device-Key", DEVICE_KEY);
  int status = http.POST(fb->buf, fb->len);
  esp_camera_fb_return(fb);

  if (status <= 0) { Serial.printf("HTTP failed: %s\n", http.errorToString(status).c_str()); http.end(); return RESULT_SYSTEM; }
  String body = http.getString();
  http.end();
  Serial.printf("HTTP %d: %s\n", status, body.c_str());

  if (status == 401) return RESULT_AUTH_ERROR;
  if (status == 400 || status == 413 || status == 429) return RESULT_INPUT_ERROR;
  if (status != 200) return RESULT_SYSTEM;           // 5xx etc. -> fail closed

  JsonDocument doc;
  if (deserializeJson(doc, body)) return RESULT_SYSTEM;   // malformed JSON
  if (!doc["code"].is<int>()) return RESULT_SYSTEM;
  int code = doc["code"].as<int>();
  if (code < 0 || code > 5) return RESULT_SYSTEM;         // unknown code
  if (code == 2) {
    Serial.printf("Plate %s | Owner %s | Flat %s\n", doc["plate"] | "-", doc["owner"] | "-", doc["flat"] | "-");
  } else if (!doc["plate"].isNull()) {
    Serial.printf("Plate read: %s\n", doc["plate"].as<const char *>());
  }
  return code;
}

void runScanCycle() {
  int code = RESULT_SYSTEM;
  for (int attempt = 1; attempt <= MAX_UNREADABLE_RETRIES; attempt++) {
    code = scanOnce();
    indicate(code);
    if (code != 1) break;
    Serial.printf("Unreadable, retry %d/%d\n", attempt, MAX_UNREADABLE_RETRIES);
  }
  if (code == 1) {
    Serial.println("Still unreadable -> MANUAL HANDLING needed");
    digitalWrite(PIN_YELLOW, HIGH); digitalWrite(PIN_RED, HIGH); delay(3000); ledsOff();
  }
  if (code == RESULT_AUTH_ERROR) delay(60000);  // don't hammer the server with bad creds
  lastScan = millis();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_GREEN, OUTPUT); pinMode(PIN_YELLOW, OUTPUT); pinMode(PIN_RED, OUTPUT);
  pinMode(PIN_SENSOR, INPUT_PULLUP);
  ledsOff();
  if (!initCamera()) {
    Serial.println("Camera init FAILED - check board selection / camera ribbon");
    while (true) blink(PIN_RED, 1, 100, 100);
  }
  ensureWiFi();
  Serial.println("Smart Gate ready.");
}

void loop() {
  if (millis() - lastScan < COOLDOWN_MS) { delay(50); return; }   // FR-ESP-10
  bool trigger = USE_PRESENCE_SENSOR ? (digitalRead(PIN_SENSOR) == LOW)
                                     : (millis() - lastScan >= TIMER_INTERVAL_MS);
  if (trigger) runScanCycle();   // one request at a time (FR-ESP-5)
  delay(50);
}
