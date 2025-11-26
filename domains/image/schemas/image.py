from enum import Enum
from pathlib import PurePosixPath

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

    @field_validator("filename")
    @classmethod
    def _deny_path_traversal(cls, value: str) -> str:
        normalized = PurePosixPath(value).name
        if not normalized:
            raise ValueError("filename must not be empty")
        return normalized


class ImageUploadResponse(BaseModel):
    key: str
    upload_url: HttpUrl
    cdn_url: HttpUrl
    expires_in: int = Field(..., description="Presigned URL TTL (seconds)")
    required_headers: dict[str, str]
