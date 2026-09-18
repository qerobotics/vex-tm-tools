"""Real-MinIO tests for backend.modules.media.s3 (plan §14 test_media.py).

Per the task's verification requirement, this round-trips against the actual
compose MinIO instance (not moto) — multipart upload, presign, fetch,
delete, and object_exists reflecting reality throughout. Skipped if MinIO
isn't reachable at S3_ENDPOINT_URL.
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest

from backend.core.settings import settings
from backend.modules.media import s3

pytestmark = pytest.mark.asyncio


async def _minio_reachable() -> bool:
    if not settings.S3_ENDPOINT_URL:
        return False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(settings.S3_ENDPOINT_URL + "/minio/health/live")
            return resp.status_code < 500
    except Exception:
        return False


@pytest.fixture(autouse=True)
async def _skip_if_minio_unreachable():
    if not await _minio_reachable():
        pytest.skip("Real MinIO not reachable at S3_ENDPOINT_URL; skipping S3 tests")


@pytest.fixture(autouse=True)
async def _ensure_bucket():
    import aioboto3
    from botocore.config import Config as BotoConfig

    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=BotoConfig(s3={"addressing_style": "path"}),
    ) as client:
        try:
            await client.create_bucket(Bucket=settings.S3_BUCKET)
        except Exception:
            pass  # bucket already exists


def test_key_naming_conventions():
    assert s3.raw_video_key("1234A", "mp4") == "teams/1234A/video/raw.mp4"
    assert s3.raw_video_key("1234A", ".MOV") == "teams/1234A/video/raw.mov"
    assert s3.processed_video_key("1234A") == "teams/1234A/video/processed.webm"


async def test_multipart_upload_presign_fetch_delete_roundtrip(tmp_path):
    local_path = tmp_path / "test_video.bin"
    # 20 MiB — large enough to force multiple parts at the module's 8 MiB
    # chunk size, genuinely exercising the multipart code path.
    content = os.urandom(20 * 1024 * 1024)
    local_path.write_bytes(content)

    key = f"tests/{uuid.uuid4().hex}/raw.bin"

    assert await s3.object_exists(key) is False

    await s3.upload_multipart(str(local_path), key)
    assert await s3.object_exists(key) is True

    url = await s3.generate_presigned_url(key, expires_in=60)
    assert key.split("/")[-1] in url or "X-Amz-Signature" in url

    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        fetched = resp.content

    assert fetched == content

    await s3.delete_object(key)
    assert await s3.object_exists(key) is False


async def test_upload_multipart_zero_byte_file(tmp_path):
    local_path = tmp_path / "empty.bin"
    local_path.write_bytes(b"")
    key = f"tests/{uuid.uuid4().hex}/empty.bin"

    await s3.upload_multipart(str(local_path), key)
    assert await s3.object_exists(key) is True

    await s3.delete_object(key)


async def test_object_exists_false_for_missing_key():
    assert await s3.object_exists(f"tests/nonexistent/{uuid.uuid4().hex}") is False


async def test_delete_object_is_idempotent():
    # Deleting a key that never existed must not raise (matches S3 semantics).
    await s3.delete_object(f"tests/never-existed/{uuid.uuid4().hex}")
