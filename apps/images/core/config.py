"""
Runtime Settings (FastAPI Official Pattern)

환경변수 기반 동적 설정 - 배포 환경별로 변경됨
Reference: https://fastapi.tiangolo.com/advanced/settings/
"""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Image service."""

    app_name: str = "Image API"

    auth_disabled: bool = Field(
        False,
        validation_alias=AliasChoices("IMAGE_AUTH_DISABLED"),
    )
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
    redis_url: str = Field(
        "redis://localhost:6379/6",
        validation_alias=AliasChoices("IMAGE_REDIS_URL"),
    )
    upload_state_ttl: int = Field(
        900,
        ge=60,
        le=24 * 60 * 60,
        validation_alias=AliasChoices("IMAGE_UPLOAD_STATE_TTL"),
    )
    allowed_targets: tuple[Literal["chat", "scan", "my"], ...] = ("chat", "scan", "my")

    # Redis connection settings
    redis_health_check_interval: int = Field(
        30,
        ge=5,
        le=300,
        description="Redis health check interval in seconds",
        validation_alias=AliasChoices("IMAGE_REDIS_HEALTH_CHECK_INTERVAL"),
    )
    redis_retry_attempts: int = Field(
        3,
        ge=1,
        le=10,
        description="Max retry attempts for Redis operations",
        validation_alias=AliasChoices("IMAGE_REDIS_RETRY_ATTEMPTS"),
    )
    redis_retry_base_delay: float = Field(
        0.1,
        ge=0.01,
        le=5.0,
        description="Base delay for exponential backoff in seconds",
        validation_alias=AliasChoices("IMAGE_REDIS_RETRY_BASE_DELAY"),
    )
    redis_socket_timeout: int = Field(
        5,
        ge=1,
        le=30,
        description="Redis socket timeout in seconds",
        validation_alias=AliasChoices("IMAGE_REDIS_SOCKET_TIMEOUT"),
    )
    redis_socket_connect_timeout: int = Field(
        5,
        ge=1,
        le=30,
        description="Redis socket connect timeout in seconds",
        validation_alias=AliasChoices("IMAGE_REDIS_SOCKET_CONNECT_TIMEOUT"),
    )

    model_config = SettingsConfigDict(
        env_prefix="IMAGE_",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance (FastAPI pattern)."""
    return Settings()
