from enum import Enum
from pathlib import PurePosixPath

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class ImageChannel(str, Enum):
    chat = "chat"
    scan = "scan"
    my = "my"


class ImageUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(
        default="application/octet-stream",
        min_length=1,
        max_length=255,
    )
    uploader_id: Optional[str] = Field(
        default=None,
        description="Optional user identifier (validated against login session)",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("filename")
    @classmethod
    def _deny_path_traversal(cls, value: str) -> str:
        normalized = PurePosixPath(value).name
        if not normalized:
            raise ValueError("filename must not be empty")
        return normalized

    @field_validator("uploader_id")
    @classmethod
    def _normalize_uploader(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("uploader_id must not be empty")
        return trimmed


class ImageUploadResponse(BaseModel):
    key: str
    upload_url: HttpUrl
    cdn_url: HttpUrl
    expires_in: int = Field(..., description="Presigned URL TTL (seconds)")
    required_headers: dict[str, str]


class ImageUploadCallbackRequest(BaseModel):
    key: str = Field(..., min_length=3, max_length=512)
    etag: str = Field(..., min_length=1, max_length=128)
    content_length: Optional[int] = Field(default=None, ge=0)
    checksum: Optional[str] = Field(
        default=None,
        description="Client-reported checksum (e.g. SHA256)",
        max_length=128,
    )


class ImageUploadFinalizeResponse(BaseModel):
    key: str
    channel: ImageChannel
    cdn_url: HttpUrl
    uploader_id: str
    metadata: Dict[str, Any]
    etag: str
    content_type: str
