"""Image input adapters (FR-GW-4, FR-GW-5, NFR-PORT-1).

Each supported format has one decoder that validates the payload and returns
JPEG bytes for the AI service. Decision logic never sees format details.

To add a new format later (e.g. RGB565), write a decoder function, add it to
DECODERS, add tests, then add its content type to ALLOWED_IMAGE_FORMATS.
"""
import io

from PIL import Image, UnidentifiedImageError

MIN_W, MIN_H = 160, 120
MAX_W, MAX_H = 4000, 4000


class ImageError(Exception):
    """Raised for invalid / unsupported images -> HTTP 400."""


def decode_jpeg(body: bytes, headers: dict) -> tuple[bytes, int, int]:
    if not body.startswith(b"\xff\xd8\xff"):
        raise ImageError("payload is not a JPEG (bad signature)")
    try:
        with Image.open(io.BytesIO(body)) as img:
            if img.format != "JPEG":
                raise ImageError("payload is not a JPEG")
            img.load()  # fully decode -> catches truncated/corrupted data
            w, h = img.size
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ImageError(f"JPEG could not be decoded: {exc}") from exc
    if not (MIN_W <= w <= MAX_W and MIN_H <= h <= MAX_H):
        raise ImageError(f"image size {w}x{h} outside allowed range")
    return body, w, h  # AI service accepts JPEG directly


# content-type -> decoder.  Future: "image/x-rgb565": decode_rgb565, ...
DECODERS = {
    "image/jpeg": decode_jpeg,
}


def to_ai_jpeg(content_type: str, body: bytes, headers: dict, allowed: list[str]):
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype not in allowed or ctype not in DECODERS:
        raise ImageError(f"unsupported Content-Type '{ctype or 'missing'}'")
    return DECODERS[ctype](body, headers)
