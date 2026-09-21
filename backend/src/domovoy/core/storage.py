"""Хранилище фото в S3-совместимом MinIO."""

import io
import uuid
from functools import lru_cache

import structlog
from fastapi import HTTPException, UploadFile
from miniopy_async.api import Minio
from PIL import Image, ImageOps

from domovoy.core.config import get_settings

log = structlog.get_logger(__name__)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
MAX_SIDE = 1600


@lru_cache
def get_minio() -> Minio:
    s = get_settings()
    return Minio(
        s.s3_endpoint,
        access_key=s.s3_access_key,
        secret_key=s.s3_secret_key.get_secret_value(),
        secure=s.s3_secure,
    )


async def ensure_bucket() -> None:
    client, bucket = get_minio(), get_settings().s3_bucket
    if not await client.bucket_exists(bucket):
        await client.make_bucket(bucket)


def _normalize_image(raw: bytes) -> bytes:
    """Поворачивает по EXIF, уменьшает до 1600 px и убирает метаданные (включая геотеги)."""
    with Image.open(io.BytesIO(raw)) as src:
        img = ImageOps.exif_transpose(src).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=82, optimize=True)
    return out.getvalue()


async def save_bytes(prefix: str, raw: bytes) -> str:
    try:
        data = _normalize_image(raw)
    except Exception as exc:
        raise HTTPException(422, "Не удалось прочитать изображение, попробуйте другое фото") from exc
    key = f"{prefix}/{uuid.uuid4().hex}.jpg"
    await get_minio().put_object(get_settings().s3_bucket, key, io.BytesIO(data), len(data), content_type="image/jpeg")
    return key


async def save_uploads(prefix: str, files: list[UploadFile]) -> list[str]:
    s = get_settings()
    files = [f for f in files if f.filename]
    if len(files) > s.upload_max_files:
        raise HTTPException(422, f"Можно приложить не больше {s.upload_max_files} фото")
    keys: list[str] = []
    for f in files:
        if f.content_type not in ALLOWED_TYPES:
            raise HTTPException(422, "Поддерживаются только фото: JPEG, PNG, WEBP, HEIC")
        raw = await f.read(s.upload_max_bytes + 1)
        if len(raw) > s.upload_max_bytes:
            raise HTTPException(422, "Фото больше 10 МБ, выберите файл поменьше")
        keys.append(await save_bytes(prefix, raw))
    return keys


async def read_object(key: str) -> bytes:
    response = await get_minio().get_object(get_settings().s3_bucket, key)
    try:
        return await response.read()
    finally:
        response.close()


def media_url(key: str) -> str:
    return f"/api/v1/media/{key}"
