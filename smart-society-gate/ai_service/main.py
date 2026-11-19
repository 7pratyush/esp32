"""AI service: POST /v1/read-plate/raw (private, port 8001).

Run:  uvicorn ai_service.main:app --host 127.0.0.1 --port 8001
"""
import hmac
from contextlib import asynccontextmanager
import os
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("AI_API_KEY", "")
WEIGHTS = os.getenv("YOLO_WEIGHTS", "ai_service/models/best.pt")
if not os.path.isabs(WEIGHTS):
    WEIGHTS = str(ROOT / WEIGHTS)
DET_CONF_MIN = float(os.getenv("DET_CONF_MIN", "0.25"))
USE_GPU = os.getenv("USE_GPU", "false").lower() in ("1", "true", "yes")
MAX_BYTES = 5_000_000

reader = None


@asynccontextmanager
async def lifespan(_app):
    global reader
    from ai_service.plate_reader import PlateReader

    reader = PlateReader(WEIGHTS, DET_CONF_MIN, USE_GPU)
    print("[ai] warming up model ...")
    reader.warm_up()  # FR-AI-5
    print(f"[ai] ready (mode: {reader.mode})")
    yield


app = FastAPI(title="Smart Society Gate - AI service", version="2.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok" if reader else "loading", "mode": reader.mode if reader else None}


@app.post("/v1/read-plate/raw")
async def read_plate_raw(request: Request, x_api_key: str = Header(default="")):
    if not API_KEY or not hmac.compare_digest(x_api_key, API_KEY):  # FR-AI-3
        raise HTTPException(401, "invalid API key")
    if reader is None:
        raise HTTPException(503, "model not loaded")
    body = await request.body()
    if not body or len(body) > MAX_BYTES:
        raise HTTPException(400, "empty or too large image")
    img = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "image could not be decoded")
    return await run_in_threadpool(reader.read, img)
