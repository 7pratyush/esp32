"""Act like the ESP32: send a JPEG to the Gateway and print the decision.

Usage:
    python tools/send_test_image.py test_images/car1.jpg
    python tools/send_test_image.py car1.jpg --url http://192.168.1.20:8000 --key wrong-key
"""
import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--device", default=os.getenv("SEED_DEVICE_ID", "gate-01"))
    ap.add_argument("--key", default=os.getenv("SEED_DEVICE_KEY", ""))
    args = ap.parse_args()

    data = Path(args.image).read_bytes()
    try:
        r = httpx.post(
            f"{args.url.rstrip('/')}/api/v1/gate/scan",
            content=data,
            headers={"Content-Type": "image/jpeg", "X-Device-Id": args.device,
                     "X-Device-Key": args.key},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        sys.exit(f"Could not reach gateway: {exc}")
    print("HTTP", r.status_code)
    try:
        print(json.dumps(r.json(), indent=2))
    except ValueError:
        print(r.text)


if __name__ == "__main__":
    main()
