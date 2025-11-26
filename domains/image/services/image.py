from __future__ import annotations

import os
from uuid import uuid4

import boto3
from botocore.client import BaseClient

from domains.image.core import Settings, get_settings
from domains.image.schemas.image import (
    ImageChannel,
    ImageUploadRequest,
    ImageUploadResponse,
)


class ImageService:
    def __init__(
        self,
        settings: Settings | None = None,
        s3_client: BaseClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._s3_client = s3_client or boto3.client(
            "s3",
            region_name=self.settings.aws_region,
        )

    async def create_upload_url(
        self,
        channel: ImageChannel,
        request: ImageUploadRequest,
    ) -> ImageUploadResponse:
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
        return ImageUploadResponse(
            key=key,
            upload_url=upload_url,
            cdn_url=cdn_url,
            expires_in=self.settings.presign_expires_seconds,
            required_headers={"Content-Type": request.content_type},
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

    async def metrics(self) -> dict:
        return {
            "bucket": self.settings.s3_bucket,
            "cdn_domain": str(self.settings.cdn_domain),
            "presign_expires_seconds": self.settings.presign_expires_seconds,
            "allowed_channels": list(self.settings.allowed_targets),
        }
