// Copy this file to "secrets.h" (same folder) and fill in your values.
// secrets.h is git-ignored so the device key is not shared (FR-ESP-4).
#pragma once

#define WIFI_SSID     "YourWiFiName"
#define WIFI_PASSWORD "YourWiFiPassword"

// Laptop IP running the gateway (find it with "ipconfig" on Windows)
#define GATEWAY_URL   "http://192.168.1.20:8000/api/v1/gate/scan"

// Must match SEED_DEVICE_ID / SEED_DEVICE_KEY in the project's .env
#define DEVICE_ID     "gate-01"
#define DEVICE_KEY    "change-me-device-secret-456"
