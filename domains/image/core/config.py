from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Image API"
    aws_region: str = Field(
        "ap-northeast-2",
        validation_alias=AliasChoices("IMAGE_AWS_REGION", "AWS_REGION"),
    )
    s3_bucket: str = Field(
        "dev-sesacthon-dev-images",
        validation_alias=AliasChoices("IMAGE_S3_BUCKET"),
    )
    cdn_domain: HttpUrl = Field(
        "https://images.dev.growbin.app",
        validation_alias=AliasChoices("IMAGE_CDN_DOMAIN"),
    )
    presign_expires_seconds: int = Field(
        900,
        ge=60,
        le=7 * 24 * 60 * 60,
        validation_alias=AliasChoices("IMAGE_PRESIGN_EXPIRES"),
    )
    allowed_targets: tuple[Literal["chat", "scan", "my"], ...] = ("chat", "scan", "my")

    model_config = SettingsConfigDict(
        env_prefix="IMAGE_",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
