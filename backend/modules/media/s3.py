"""S3 multipart upload / presign / delete helpers (plan §3.8 / §5.13 /
Appendix A.5 / §C.2).

Owns: S3 multipart upload, presigned URL generation, raw/processed key
conventions, download.

Key naming convention (must be followed exactly, per Appendix C.2):
    raw videos:       teams/{team_number}/video/raw.{ext}
    processed videos:  teams/{team_number}/video/processed.webm

May import from: `backend.core` (settings for S3 credentials). `boto3`/
`aioboto3` only.
"""
from __future__ import annotations

import logging
import os

import aioboto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from backend.core.exceptions import ProcessingError
from backend.core.settings import settings

logger = logging.getLogger(__name__)

# Multipart uploads use 8 MiB parts by default (S3's minimum part size,
# except for the final part, is 5 MiB). Per Appendix A.5 every upload must
# go through multipart — never a single PUT, regardless of file size (there
# is no size threshold to gate on: `upload_multipart` always uses the
# create/upload_part/complete multipart API).
_MULTIPART_CHUNK_SIZE = 8 * 1024 * 1024

_session = aioboto3.Session()


def raw_video_key(team_number: str, ext: str) -> str:
    """Return the canonical S3 key for a team's raw uploaded video."""
    ext = ext.lstrip(".").lower()
    return f"teams/{team_number}/video/raw.{ext}"


def processed_video_key(team_number: str) -> str:
    """Return the canonical S3 key for a team's processed (chroma-keyed) video."""
    return f"teams/{team_number}/video/processed.webm"


def _require_s3_settings() -> None:
    if not settings.S3_BUCKET:
        raise ProcessingError(
            "S3 is not configured (S3_BUCKET is unset) — set S3 credentials via "
            "env vars or the Settings page before uploading media."
        )


def _client_ctx():
    _require_s3_settings()
    return _session.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        # path-style addressing is required for MinIO and most self-hosted
        # S3-compatible endpoints (virtual-hosted-style buckets don't resolve).
        config=BotoConfig(s3={"addressing_style": "path"}, signature_version="s3v4"),
    )


async def upload_multipart(local_path: str, s3_key: str) -> None:
    """Upload `local_path` to `s3_key` using S3's multipart upload API.

    Always uses multipart (create/upload_part/complete), never a single PUT,
    per Appendix A.5 — regardless of file size. Aborts the multipart upload
    on any failure so no orphaned parts are left billing storage.
    """
    _require_s3_settings()
    file_size = os.path.getsize(local_path)

    async with _client_ctx() as s3:
        create_resp = await s3.create_multipart_upload(Bucket=settings.S3_BUCKET, Key=s3_key)
        upload_id = create_resp["UploadId"]
        parts: list[dict] = []
        try:
            with open(local_path, "rb") as fh:
                part_number = 1
                while True:
                    chunk = fh.read(_MULTIPART_CHUNK_SIZE)
                    if not chunk:
                        break
                    part_resp = await s3.upload_part(
                        Bucket=settings.S3_BUCKET,
                        Key=s3_key,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=chunk,
                    )
                    parts.append({"PartNumber": part_number, "ETag": part_resp["ETag"]})
                    part_number += 1

            if not parts:
                # Zero-byte file: S3 requires at least one part.
                part_resp = await s3.upload_part(
                    Bucket=settings.S3_BUCKET,
                    Key=s3_key,
                    PartNumber=1,
                    UploadId=upload_id,
                    Body=b"",
                )
                parts.append({"PartNumber": 1, "ETag": part_resp["ETag"]})

            await s3.complete_multipart_upload(
                Bucket=settings.S3_BUCKET,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except Exception as exc:
            try:
                await s3.abort_multipart_upload(
                    Bucket=settings.S3_BUCKET, Key=s3_key, UploadId=upload_id
                )
            except Exception:
                logger.exception("Failed to abort multipart upload %s for key %s", upload_id, s3_key)
            raise ProcessingError(
                f"Multipart upload of {local_path!r} to {s3_key!r} failed: {exc}"
            ) from exc

    logger.info("Uploaded %s (%d bytes) to s3://%s/%s", local_path, file_size, settings.S3_BUCKET, s3_key)


async def generate_presigned_url(s3_key: str, expires_in: int = 900) -> str:
    """Generate a pre-signed GET URL for `s3_key`, valid for `expires_in`
    seconds (default 15 minutes, per plan §3.8)."""
    _require_s3_settings()
    async with _client_ctx() as s3:
        return await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": s3_key},
            ExpiresIn=expires_in,
        )


async def delete_object(s3_key: str) -> None:
    """Delete `s3_key` from the configured bucket. Idempotent — deleting a
    key that doesn't exist is not an error (matches S3 semantics)."""
    _require_s3_settings()
    async with _client_ctx() as s3:
        await s3.delete_object(Bucket=settings.S3_BUCKET, Key=s3_key)


async def object_exists(s3_key: str) -> bool:
    """Return True if `s3_key` exists in the configured bucket."""
    _require_s3_settings()
    async with _client_ctx() as s3:
        try:
            await s3.head_object(Bucket=settings.S3_BUCKET, Key=s3_key)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
