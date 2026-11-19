"""Device-key hashing (NFR-SEC-2). Keys are stored as PBKDF2-SHA256 hashes."""
import hashlib
import hmac
import secrets

ITERATIONS = 200_000


def hash_key(key: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", key.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest.hex()}"


def verify_key(key: str, stored: str) -> bool:
    try:
        algo, iterations, salt, expected = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", key.encode(), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), expected)  # constant-time
    except (ValueError, AttributeError):
        return False
