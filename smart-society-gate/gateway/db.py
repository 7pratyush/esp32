"""MongoDB access (Section 7)."""
from pymongo import ASCENDING, MongoClient

_client = None


def get_db(settings):
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=2000)
    return _client[settings.DB_NAME]


def set_db_client(client):
    """Used by tests to inject a fake (mongomock) client."""
    global _client
    _client = client


def ensure_indexes(db):
    db.vehicles.create_index([("plate_number", ASCENDING)], unique=True)
    db.devices.create_index([("device_id", ASCENDING)], unique=True)
    db.access_logs.create_index([("timestamp", ASCENDING)])
    db.access_logs.create_index([("plate_text", ASCENDING)])
