"""Gateway tests for SRS test cases T1-T15 (no MongoDB or AI model needed).

Run:  python -m pytest -q
"""
import io

import mongomock
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import gateway.main as gw
from gateway import db as dbmod
from gateway.config import settings
from gateway.security import hash_key

DEVICE, KEY = "gate-01", "test-key"


def jpeg(w=640, h=480) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 200, 200)).save(buf, "JPEG")
    return buf.getvalue()


def ai_reply(plate="UP70AB1234", ocr=0.91, found=True):
    return {"plate_found": found, "plate_text": plate if found else "",
            "detection_confidence": 0.94 if found else None,
            "ocr_confidence": ocr if found else None,
            "valid_format": True, "detections": [], "processing_ms": 100}


@pytest.fixture
def env(monkeypatch):
    client = mongomock.MongoClient()
    dbmod.set_db_client(client)
    db = client[settings.DB_NAME]
    db.devices.insert_one({"device_id": DEVICE, "key_hash": hash_key(KEY), "enabled": True})
    db.devices.insert_one({"device_id": "gate-off", "key_hash": hash_key(KEY), "enabled": False})
    db.vehicles.insert_many([
        {"plate_number": "UP70AB1234", "owner_name": "R. Sharma", "flat_no": "A-101",
         "status": "active", "valid_from": "2020-01-01", "valid_to": "2099-12-31"},
        {"plate_number": "MH12XY9876", "owner_name": "A. Patil", "flat_no": "C-303",
         "status": "blocked", "valid_from": "2020-01-01", "valid_to": "2099-12-31"},
        {"plate_number": "KA05MN1111", "owner_name": "K. Rao", "flat_no": "B-07",
         "status": "active", "valid_from": "2020-01-01", "valid_to": "2021-12-31"},
    ])
    monkeypatch.setattr(settings, "COOLDOWN_S", 0)
    state = {"reply": ai_reply()}

    def fake_ai(_jpeg):
        if isinstance(state["reply"], Exception):
            raise state["reply"]
        return state["reply"]

    monkeypatch.setattr(gw, "call_ai", fake_ai)
    yield TestClient(gw.app), db, state
    dbmod.set_db_client(None)


def scan(client, body=None, key=KEY, device=DEVICE, ctype="image/jpeg"):
    return client.post("/api/v1/gate/scan", content=jpeg() if body is None else body,
                       headers={"Content-Type": ctype, "X-Device-Id": device,
                                "X-Device-Key": key})


def test_t1_allowed_and_logged(env):
    client, db, _ = env
    r = scan(client)
    assert r.status_code == 200
    j = r.json()
    assert j["code"] == 2 and j["decision"] == "ALLOWED"
    assert j["owner"] == "R. Sharma" and j["flat"] == "A-101"
    assert db.access_logs.count_documents({"request_id": j["request_id"], "code": 2}) == 1


def test_t1_plate_with_spaces_normalized(env):
    client, _, state = env
    state["reply"] = ai_reply(plate="up 70 ab-1234")
    assert scan(client).json()["code"] == 2


def test_t2_blocked(env):
    client, _, state = env
    state["reply"] = ai_reply("MH12XY9876")
    j = scan(client).json()
    assert j["code"] == 4 and j["owner"] is None


def test_t3_not_registered(env):
    client, _, state = env
    state["reply"] = ai_reply("UP32ZZ0001")
    assert scan(client).json()["code"] == 3


def test_t4_no_plate(env):
    client, _, state = env
    state["reply"] = ai_reply(found=False)
    assert scan(client).json()["code"] == 0


@pytest.mark.parametrize("plate,ocr", [("UP70AB1234", 0.2), ("", 0.9), ("UP7", 0.9),
                                        ("HELLOWORLD", 0.95)])
def test_t5_unreadable(env, plate, ocr):
    client, _, state = env
    state["reply"] = ai_reply(plate, ocr)
    assert scan(client).json()["code"] == 1


def test_t6_ai_down(env):
    client, _, state = env
    state["reply"] = TimeoutError("AI timed out")
    j = scan(client).json()
    assert j["code"] == 5


def test_t7_db_down_during_lookup(env, monkeypatch):
    client, db, _ = env

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(db.vehicles, "find_one", boom)
    monkeypatch.setattr(dbmod, "get_db", lambda s: db)
    assert scan(client).json()["code"] == 5


@pytest.mark.parametrize("device,key", [(DEVICE, "wrong"), (DEVICE, ""), ("", KEY),
                                         ("gate-off", KEY), ("unknown", KEY)])
def test_t8_auth(env, device, key):
    client, _, _ = env
    assert scan(client, key=key, device=device).status_code == 401


def test_t9_empty_body(env):
    client, _, _ = env
    assert scan(client, body=b"").status_code == 400


def test_t10_too_large(env):
    client, _, _ = env
    assert scan(client, body=b"\xff\xd8\xff" + b"0" * (settings.MAX_IMAGE_BYTES + 10)).status_code == 413


@pytest.mark.parametrize("body,ctype", [
    (b"not an image at all", "image/jpeg"),
    (None, "image/png"),          # unsupported type
    (b"\xff\xd8\xff\xe0garbage", "image/jpeg"),  # corrupted JPEG
])
def test_t11_bad_image(env, body, ctype):
    client, db, _ = env
    r = scan(client, body=body, ctype=ctype)
    assert r.status_code == 400
    assert db.access_logs.count_documents({}) == 0  # no AI call, no decision


def test_t11_truncated_jpeg(env):
    client, _, _ = env
    assert scan(client, body=jpeg()[:500]).status_code == 400


def test_t12_cooldown_marks_duplicate(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setattr(settings, "COOLDOWN_S", 30)
    gw._recent.clear()
    assert scan(client).json()["duplicate"] is False
    assert scan(client).json()["duplicate"] is True


def test_t14_expired(env):
    client, _, state = env
    state["reply"] = ai_reply("KA05MN1111")
    assert scan(client).json()["code"] == 4


@pytest.mark.parametrize("reply", [
    {"plate_text": "UP70AB1234"},                                   # no plate_found
    "not json object",
    {"plate_found": True, "plate_text": "UP70AB1234"},              # missing ocr conf
    {"plate_found": True, "plate_text": "UP70AB1234", "ocr_confidence": "high"},
])
def test_t15_malformed_ai(env, reply):
    client, _, state = env
    state["reply"] = reply
    assert scan(client).json()["code"] == 5


def test_bh_series_plate(env):
    client, db, state = env
    db.vehicles.insert_one({"plate_number": "22BH1234AA", "status": "active"})
    state["reply"] = ai_reply("22BH1234AA")
    assert scan(client).json()["code"] == 2


def test_health_shape(env):
    client, _, _ = env
    j = client.get("/health").json()
    assert j["gateway"] == "ok" and "ai" in j and "db" in j
