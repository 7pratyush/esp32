"""Load registered vehicles + the ESP32 device credential into MongoDB (FR-DB-4).

Usage:
    python tools/seed_db.py                      # uses data/vehicles.csv and .env values
    python tools/seed_db.py --csv my_vehicles.csv
    python tools/seed_db.py --device gate-02 --key another-secret --gate "Back Gate"

Running it again is safe: vehicles are updated by plate number.
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gateway.config import settings  # noqa: E402  (also loads .env)
from gateway.db import ensure_indexes, get_db  # noqa: E402
from gateway.decision import normalize_plate  # noqa: E402
from gateway.security import hash_key  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "data" / "vehicles.csv"))
    ap.add_argument("--device", default=os.getenv("SEED_DEVICE_ID", "gate-01"))
    ap.add_argument("--key", default=os.getenv("SEED_DEVICE_KEY", ""))
    ap.add_argument("--gate", default=os.getenv("SEED_GATE_NAME", "Main Gate"))
    args = ap.parse_args()

    db = get_db(settings)
    db.client.admin.command("ping")
    ensure_indexes(db)

    count = 0
    with open(args.csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            plate = normalize_plate(row["plate_number"])
            if not plate:
                continue
            doc = {
                "plate_number": plate,
                "vehicle_type": row.get("vehicle_type") or None,
                "owner_name": row.get("owner_name") or None,
                "flat_no": row.get("flat_no") or None,
                "status": (row.get("status") or "active").strip().lower(),
                "valid_from": row.get("valid_from") or None,
                "valid_to": row.get("valid_to") or None,
            }
            db.vehicles.update_one(
                {"plate_number": plate},
                {"$set": doc, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
            count += 1
    print(f"Vehicles loaded/updated: {count}")

    if args.key:
        db.devices.update_one(
            {"device_id": args.device},
            {"$set": {"device_id": args.device, "key_hash": hash_key(args.key),
                      "gate_name": args.gate, "enabled": True}},
            upsert=True,
        )
        print(f"Device '{args.device}' saved (key stored as a hash).")
    else:
        print("No device key given (SEED_DEVICE_KEY empty) - device not created.")


if __name__ == "__main__":
    main()
