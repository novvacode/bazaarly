"""Image upload validation and normalisation (SPEC §16).

Images are validated by decoding (never by extension), EXIF is dropped, the long side is
capped at 1200 px, and the result is re-encoded as WebP (quality 82).
"""

from __future__ import annotations

import asyncio
import io
import uuid
import warnings

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core import errors
from app.core.errors import AppError
from app.integrations.storage import Storage

MAX_BYTES = 2 * 1024 * 1024
MAX_SIDE = 1200
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard


async def read_upload(upload: UploadFile) -> bytes:
    data = await upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise AppError(errors.UPLOAD_TOO_LARGE, "Image must be 2 MB or smaller", 413)
    if not data:
        raise AppError(errors.UPLOAD_INVALID, "Empty file", 422)
    return data


def normalize_image(data: bytes) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                fmt = probe.format
                probe.verify()
            if fmt not in ALLOWED_FORMATS:
                raise AppError(errors.UPLOAD_INVALID, "Use a JPEG, PNG or WebP image", 422)
            with Image.open(io.BytesIO(data)) as source:
                source.load()
                img: Image.Image = ImageOps.exif_transpose(source)
                img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                out = io.BytesIO()
                # Re-encoding without passing `exif=` strips all metadata.
                img.save(out, format="WEBP", quality=82, method=4)
                return out.getvalue()
    except AppError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise AppError(errors.UPLOAD_INVALID, "That file isn't a valid image", 422) from None


async def store_image(
    storage: Storage, upload: UploadFile, *, tenant_id: uuid.UUID, kind: str
) -> str:
    data = await read_upload(upload)
    webp = await asyncio.to_thread(normalize_image, data)
    key = f"tenants/{tenant_id}/{kind}/{uuid.uuid4()}.webp"
    return await storage.put(key, webp, "image/webp")
