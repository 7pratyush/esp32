# Smart Society Gate – Number Plate Recognition (SRS v2.0)

ESP32-CAM → **Gateway** (port 8000) → **AI service** (YOLO + EasyOCR, port 8001) → **MongoDB**

The Gateway returns one decision code per scan:

| Code | Meaning | ESP32 LEDs |
|---|---|---|
| 0 | No plate detected | 1 short yellow blink |
| 1 | Plate unreadable / low confidence | 3 yellow blinks (auto-retries up to 3 times) |
| **2** | **ALLOWED** (the only code that grants access) | Green for 3 s |
| 3 | Denied – not registered | Red for 3 s |
| 4 | Denied – blocked or expired | 3 slow red blinks |
| 5 | System error (gate stays closed) | Fast red blinking |

---

## 1. Install these once (Windows)

1. **Python 3.11.** Download it from python.org. In the installer, tick **"Add python.exe to PATH"**.
2. **MongoDB Community Server.** Download it from mongodb.com/try/download/community and choose the default options, including **"Install MongoD as a Service"**. MongoDB then starts automatically with Windows.
3. **Arduino IDE 2** (only needed for the ESP32 step).

## 2. Set up the project

1. Unzip the project to a folder, for example `C:\smart-society-gate`.
2. Double-click **`setup.bat`**. It creates a virtual environment and installs all the packages, which takes 5–15 minutes because PyTorch is large. It also creates a `.env` file.
3. *(Recommended)* Open `.env` in Notepad and change `AI_API_KEY` and `SEED_DEVICE_KEY` to your own secret values.
4. Copy your trained YOLO weights to **`ai_service\models\best.pt`**.
   *If you don't have `best.pt` yet, the AI service still runs in "OCR-only" mode, which reads close-up plate photos. Use it for testing only.*
5. Double-click **`seed_db.bat`**. It loads the vehicles from `data\vehicles.csv` and creates the device `gate-01`. Edit the CSV to add your own vehicles, then run it again; running it more than once is safe.

## 3. Run it

Open two windows by double-clicking each of these:

1. **`start_ai.bat`**. Wait until it prints `ready`. The first start downloads the EasyOCR models (about 100 MB).
2. **`start_gateway.bat`**

Check that everything is running by opening **http://127.0.0.1:8000/health** in your browser. It should show:
`{"gateway":"ok","ai":"ok","db":"ok"}`

## 4. Test without the ESP32

Put a car photo (JPEG) in `test_images\`. Then, in the project folder, open a Command Prompt and run:

```
.venv\Scripts\python tools\send_test_image.py test_images\car1.jpg
```

The output looks like this:

```
HTTP 200
{ "code": 2, "decision": "ALLOWED", "plate": "UP70AB1234", "owner": "R. Sharma", "flat": "A-101", ... }
```

Every scan is saved in MongoDB in `smart_gate` → `access_logs`. You can view the logs with MongoDB Compass, which is installed together with MongoDB.

**Automated tests** for SRS cases T1–T15 don't need MongoDB or the model. Double-click **`run_tests.bat`**.

## 5. ESP32-CAM

1. In Arduino IDE, go to **Boards Manager** and install **"esp32 by Espressif"**. Then go to **Library Manager** and install **"ArduinoJson"**.
2. Open `esp32\SmartGateCam\SmartGateCam.ino`.
3. In the same folder, copy `secrets_example.h` to **`secrets.h`** and fill in:
   - your Wi-Fi name and password
   - `GATEWAY_URL`: your laptop's IP address. Run `ipconfig` and use the "IPv4 Address", e.g. `http://192.168.1.20:8000/api/v1/gate/scan`
   - `DEVICE_ID` and `DEVICE_KEY`: the same values as `SEED_DEVICE_ID` and `SEED_DEVICE_KEY` in `.env`
4. Select the board **"AI Thinker ESP32-CAM"**, then upload. Open the Serial Monitor at **115200** baud to see the results.
5. Wire the LEDs, each through a 220 Ω resistor to GND: **Green → GPIO 14**, **Yellow → GPIO 2**, **Red → GPIO 15**.
   By default, the ESP32 takes a photo every 8 seconds. To use an IR sensor instead, connect it to **GPIO 13** and set `USE_PRESENCE_SENSOR` to `true`.

> **The ESP32 can't connect?** Laptop and ESP32 must be on the **same Wi-Fi**. The first time you run `start_gateway.bat`, Windows asks for firewall access: click **Allow**, and tick Private networks.

## 6. Measure accuracy (Section 10)

1. Put labeled ESP32 photos in a folder such as `benchmark\`.
2. Add a `benchmark\labels.csv` file with the columns `filename,plate`.
3. Start the AI service, then run:

```
.venv\Scripts\python tools\evaluate.py benchmark
```

It prints the exact-match accuracy, character error rate, "confident but wrong" count (the false-accept risk) and p50/p95 latency, and saves `results\evaluation_results.csv`. Use the results to tune `CONF_MIN` in `.env`.

---

## Project layout

```
gateway/          ESP32-facing API: auth, image checks, AI call, decision, logging
  decision.py     decision rules (Section 8), Indian plate format check
  image_input.py  format adapters - JPEG now, add RGB565/YUV later here
ai_service/       YOLO + EasyOCR service (private, 127.0.0.1 only)
tools/            seed_db.py, send_test_image.py, evaluate.py
data/vehicles.csv sample registered vehicles
esp32/            Arduino firmware
tests/            automated tests (T1-T15)
```

## Settings (`.env`)

| Setting | Default | What it does |
|---|---|---|
| `CONF_MIN` | 0.50 | Minimum OCR confidence needed to trust a plate read. Calibrate this on real ESP32 photos. |
| `STRICT_FORMAT` | true | Plate text must match the Indian format (e.g. `UP70AB1234`, or `22BH1234AA` for BH series). |
| `AI_TIMEOUT_S` | 10 | How long the Gateway waits for the AI service. The ESP32 waits 15 s. |
| `MAX_IMAGE_BYTES` | 2000000 | Maximum upload size (2 MB). |
| `COOLDOWN_S` | 10 | The same plate from the same gate within this time is marked `"duplicate": true`. |

## Security notes
- Device keys are stored as PBKDF2 hashes, never as plain text. The AI service needs its own API key and only listens on 127.0.0.1.
- Only exact plate matches can grant access, with no fuzzy matching. Any error or timeout keeps the gate closed.
- Plain HTTP is fine for a classroom demo on a trusted Wi-Fi. A real deployment needs HTTPS.
- Raw images are not stored. Phone numbers are never sent to the ESP32.

## Not included in this version (per the SRS)
- No admin dashboard or admin API.
- No physical boom-barrier control.
- No RGB565/YUV input yet. The adapter is ready to add them.
- The optional "two consistent reads" rule (FR-GW-13, default off) and an OLED display are not included.
