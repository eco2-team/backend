"""Chat Worker Configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Chat Worker 설정."""

    # Environment
    environment: str = "local"  # local, dev, staging, production

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_queue: str = "chat.process"

    # Redis (이벤트 스트림, 단기 캐시)
    redis_url: str = "redis://localhost:6379/0"

    # PostgreSQL (체크포인팅, 멀티턴 대화 히스토리)
    # Cursor 스타일 장기 세션 유지를 위한 영구 저장소
    # None이면 Redis 폴백 (TTL 24시간)
    postgres_url: str | None = None

    # LLM Provider
    default_provider: Literal["openai", "gemini"] = "openai"

    # OpenAI
    openai_api_key: str | None = None
    openai_default_model: str = "gpt-5.2"

    # Gemini
    google_api_key: str | None = None
    gemini_default_model: str = "gemini-3-flash-preview"

    # Assets
    assets_path: str | None = None

    # Web Search (Subagent용)
    # Tavily API 키 (LLM 최적화 검색, 선택적)
    # 없으면 DuckDuckGo 사용 (무료, API 키 불필요)
    tavily_api_key: str | None = None

    # gRPC Clients (Subagent용)
    # Character gRPC: 캐릭터 정보 조회 (별도 Pod)
    character_grpc_host: str = "character-grpc.character.svc.cluster.local"
    character_grpc_port: int = 50051

    # Location gRPC: 주변 센터 검색 (별도 Pod)
    location_grpc_host: str = "location-grpc.location.svc.cluster.local"
    location_grpc_port: int = 50051

    # Logging
    log_level: str = "INFO"

    class Config:
        env_prefix = "CHAT_WORKER_"
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤."""
    return Settings()
