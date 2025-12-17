from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional
from uuid import uuid4

import boto3
from botocore.client import BaseClient
from pydantic import HttpUrl
from redis.asyncio import Redis

from domains.image.core import Settings, get_settings
from domains.image.core.redis import get_upload_redis
from domains.image.schemas.image import (
    ImageChannel,
    ImageUploadCallbackRequest,
    ImageUploadFinalizeResponse,
    ImageUploadRequest,
    ImageUploadResponse,
)

logger = logging.getLogger(__name__)


class PendingUpload:
    def __init__(
        self,
        *,
        channel: ImageChannel,
        uploader_id: str,
        metadata: Dict[str, Any],
        content_type: str,
        cdn_url: HttpUrl,
    ) -> None:
        self.channel = channel
        self.uploader_id = uploader_id
        self.metadata = metadata
        self.content_type = content_type
        self.cdn_url = str(cdn_url)

    def to_json(self) -> str:
        return json.dumps(
            {
                "channel": self.channel.value,
                "uploader_id": self.uploader_id,
                "metadata": self.metadata,
                "content_type": self.content_type,
                "cdn_url": self.cdn_url,
            }
        )

    @classmethod
    def from_json(cls, payload: str) -> "PendingUpload":
        data = json.loads(payload)
        return cls(
            channel=ImageChannel(data["channel"]),
            uploader_id=data["uploader_id"],
            metadata=data.get("metadata") or {},
            content_type=data["content_type"],
            cdn_url=data["cdn_url"],
        )


class PendingUploadNotFoundError(Exception):
    """Raised when the upload session does not exist or expired."""


class PendingUploadChannelMismatchError(Exception):
    """Raised when the callback channel and stored channel differ."""


class PendingUploadPermissionDeniedError(Exception):
    """Raised when the upload session belongs to another user."""


class ImageService:
    def __init__(
        self,
        settings: Settings | None = None,
        s3_client: BaseClient | None = None,
        redis_client: Redis | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._s3_client = s3_client or boto3.client(
            "s3",
            region_name=self.settings.aws_region,
        )
        self._redis: Redis = redis_client or get_upload_redis()

    async def create_upload_url(
        self,
        channel: ImageChannel,
        request: ImageUploadRequest,
        *,
        uploader_id: str,
    ) -> ImageUploadResponse:
        logger.info(
            "Upload URL requested",
            extra={
                "channel": channel.value,
                "content_type": request.content_type,
                "uploader_id": uploader_id,
            },
        )
        key = self._build_object_key(channel.value, request.filename)
        params = {
            "Bucket": self.settings.s3_bucket,
            "Key": key,
            "ContentType": request.content_type,
        }
        upload_url = self._s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params=params,
            ExpiresIn=self.settings.presign_expires_seconds,
            HttpMethod="PUT",
        )

        cdn_url = self._compose_cdn_url(key)
        pending = PendingUpload(
            channel=channel,
            uploader_id=uploader_id,
            metadata=request.metadata,
            content_type=request.content_type,
            cdn_url=cdn_url,
        )
        await self._save_pending_upload(key, pending)

        return ImageUploadResponse(
            key=key,
            upload_url=upload_url,
            cdn_url=cdn_url,
            expires_in=self.settings.presign_expires_seconds,
            required_headers={"Content-Type": request.content_type},
        )

    async def finalize_upload(
        self,
        channel: ImageChannel,
        request: ImageUploadCallbackRequest,
        *,
        uploader_id: str,
    ) -> ImageUploadFinalizeResponse:
        pending = await self._load_pending_upload(request.key)
        if pending is None:
            logger.warning("Upload finalize failed: not found", extra={"key": request.key})
            raise PendingUploadNotFoundError
        if pending.channel != channel:
            logger.warning("Upload finalize failed: channel mismatch", extra={"key": request.key})
            raise PendingUploadChannelMismatchError
        if pending.uploader_id != uploader_id:
            logger.warning("Upload finalize failed: permission denied", extra={"key": request.key})
            raise PendingUploadPermissionDeniedError

        await self._delete_pending_upload(request.key)
        logger.info(
            "Upload finalized",
            extra={"channel": channel.value, "key": request.key, "uploader_id": uploader_id},
        )

        return ImageUploadFinalizeResponse(
            key=request.key,
            channel=channel,
            cdn_url=pending.cdn_url,
            uploader_id=pending.uploader_id,
            metadata=pending.metadata,
            etag=request.etag,
            content_type=pending.content_type,
        )

    def _build_object_key(self, prefix: str, filename: str) -> str:
        base, ext = os.path.splitext(filename)
        sanitized_ext = ext.lower() or ".bin"
        identifier = uuid4().hex
        safe_prefix = prefix.strip("/")
        return f"{safe_prefix}/{identifier}{sanitized_ext}"

    def _compose_cdn_url(self, key: str) -> str:
        cdn = str(self.settings.cdn_domain).rstrip("/")
        return f"{cdn}/{key}"

    def _pending_key(self, object_key: str) -> str:
        return f"image:pending:{object_key}"

    async def _save_pending_upload(self, object_key: str, pending: PendingUpload) -> None:
        await self._redis.setex(
            self._pending_key(object_key),
            self.settings.upload_state_ttl,
            pending.to_json(),
        )

    async def _load_pending_upload(self, object_key: str) -> Optional[PendingUpload]:
        payload = await self._redis.get(self._pending_key(object_key))
        if not payload:
            return None
        return PendingUpload.from_json(payload)

    async def _delete_pending_upload(self, object_key: str) -> None:
        await self._redis.delete(self._pending_key(object_key))

    async def metrics(self) -> dict:
        return {
            "bucket": self.settings.s3_bucket,
            "cdn_domain": str(self.settings.cdn_domain),
            "presign_expires_seconds": self.settings.presign_expires_seconds,
            "allowed_channels": list(self.settings.allowed_targets),
            "auth_required": not self.settings.auth_disabled,
        }
