"""S3-compatible object storage (Cloudflare R2 in prod, MinIO locally), SPEC §16."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any, Protocol

from app.config import get_settings


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str:
        """Store `data` at `key` and return its public URL."""
        ...


class S3Storage:
    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        s = get_settings()
        self._bucket = s.s3_bucket
        self._public_base = s.s3_public_base_url.rstrip("/")
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url or None,
            aws_access_key_id=s.s3_access_key_id,
            aws_secret_access_key=s.s3_secret_access_key,
            region_name=s.s3_region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )
        return f"{self._public_base}/{key}"


class MemoryStorage:
    """In-process storage for tests."""

    def __init__(self, base_url: str = "http://storage.test") -> None:
        self.base_url = base_url
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        self.objects[key] = (data, content_type)
        return f"{self.base_url}/{key}"


@lru_cache(maxsize=1)
def _s3() -> S3Storage:
    return S3Storage()


def get_storage() -> Storage:
    """FastAPI dependency; tests override it with MemoryStorage."""
    return _s3()
