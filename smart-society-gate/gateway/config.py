"""Gateway settings, read from environment / .env (Section 3.2)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    def __init__(self) -> None:
        self.AI_URL = os.getenv("AI_URL", "http://127.0.0.1:8001").rstrip("/")
        self.AI_API_KEY = os.getenv("AI_API_KEY", "")
        self.MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
        self.DB_NAME = os.getenv("DB_NAME", "smart_gate")
        self.CONF_MIN = float(os.getenv("CONF_MIN", "0.50"))
        self.MIN_PLATE_LEN = int(os.getenv("MIN_PLATE_LEN", "6"))
        self.STRICT_FORMAT = _bool("STRICT_FORMAT", "true")
        self.AI_TIMEOUT_S = float(os.getenv("AI_TIMEOUT_S", "10"))
        self.MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", "2000000"))
        self.ALLOWED_IMAGE_FORMATS = [
            f.strip().lower()
            for f in os.getenv("ALLOWED_IMAGE_FORMATS", "image/jpeg").split(",")
            if f.strip()
        ]
        self.COOLDOWN_S = float(os.getenv("COOLDOWN_S", "10"))
        self.MAX_CONCURRENT_AI = int(os.getenv("MAX_CONCURRENT_AI", "2"))
        self.TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")


settings = Settings()
